from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from bot.llm.base import LLMBackend
from bot.models import ExtractionResult, KnowledgeEntry
from bot.storage.base import StorageBackend

if TYPE_CHECKING:
    from bot.search.base import SearchBackend
    from bot.vision.base import VisionBackend

logger = logging.getLogger(__name__)


async def process_url(
    url: str,
    llm: LLMBackend,
    storage: StorageBackend,
    vision: "VisionBackend | None" = None,
    search: "SearchBackend | None" = None,
) -> tuple[KnowledgeEntry, str, str]:
    """
    Full pipeline: URL → transcript (+ optional vision) → LLM extraction → storage.
    Returns (entry, confirmation_message, storage_ref).
    """
    combined_input = await _build_llm_input(url, vision)
    logger.info("LLM input ready (%d chars) for %s", len(combined_input), url)

    result = await llm.extract(combined_input)
    logger.info("Extracted: category=%s title=%r", result.category, result.title)

    if search is not None:
        result = await _enrich_with_urls(result, search)

    # Store only the raw audio transcript in the entry, not the combined prompt
    raw_transcript = _extract_transcript_section(combined_input)
    entry = KnowledgeEntry.from_extraction(result, source_url=url, raw_transcript=raw_transcript)
    confirmation, storage_ref = await storage.save(entry)
    return entry, confirmation, storage_ref


async def _already(value: str | None) -> str | None:
    return value


def _looks_like_product_name(name: str) -> bool:
    """Return True if name looks like a real product name worth searching for."""
    words = name.split()
    if len(words) > 2:
        return False
    # Reject names containing Cyrillic characters
    if any("Ѐ" <= c <= "ӿ" for c in name):
        return False
    return True


async def _enrich_with_urls(result: ExtractionResult, search: "SearchBackend") -> ExtractionResult:
    """Find URLs for tools and GitHub repos that don't have one, concurrently."""
    tool_tasks = []
    for tool in result.tools:
        if tool.get("url"):
            tool_tasks.append(_already(tool["url"]))
        elif _looks_like_product_name(tool["name"]):
            tool_tasks.append(search.find_url(tool["name"], context="developer tool"))
        else:
            tool_tasks.append(_already(None))

    repo_tasks = [
        search.find_url(repo["name"], context="github")
        if not repo.get("url")
        else _already(repo.get("url"))
        for repo in result.github_repos
    ]

    all_results = await asyncio.gather(*tool_tasks, *repo_tasks, return_exceptions=True)

    tool_urls = all_results[: len(result.tools)]
    repo_urls = all_results[len(result.tools):]

    enriched_tools = []
    for tool, url in zip(result.tools, tool_urls):
        enriched_tools.append({
            "name": tool["name"],
            "url": url if isinstance(url, str) else tool.get("url"),
        })

    enriched_repos = []
    for repo, url in zip(result.github_repos, repo_urls):
        enriched_repos.append({
            **repo,
            "url": repo.get("url") or (url if isinstance(url, str) else None),
        })

    return ExtractionResult(
        title=result.title,
        category=result.category,
        summary=result.summary,
        github_repos=enriched_repos,
        recipe=result.recipe,
        tools=enriched_tools,
        tags=result.tags,
    )


async def _build_llm_input(url: str, vision: "VisionBackend | None") -> str:
    captions = await _fetch_captions(url)

    if captions and vision is None:
        # Fast path: captions available, no vision needed
        return captions

    if captions and vision is not None:
        # Have captions but still want visual context — download video for frames only
        visual_description = await _run_vision_on_video(url, vision)
        if visual_description:
            return _merge(visual_description, captions)
        return captions

    # No captions — must download video for both whisper and (optionally) vision
    logger.info("No captions available, downloading video")
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            video_path: str | None = await _download_video(url, tmpdir)
        except Exception as e:
            logger.warning("Video download failed, falling back to transcript-only: %s", e)
            video_path = None

        if video_path is None:
            return ""

        import asyncio
        loop = asyncio.get_event_loop()

        # Run whisper and vision extraction concurrently
        whisper_task = loop.run_in_executor(None, _run_whisper, video_path)

        if vision is not None:
            vision_task = _run_vision_from_file(video_path, tmpdir, vision)
            transcript, visual_description = await asyncio.gather(
                whisper_task, vision_task, return_exceptions=True
            )
            transcript = transcript if isinstance(transcript, str) else ""
            visual_description = visual_description if isinstance(visual_description, str) else ""
        else:
            transcript = await whisper_task
            visual_description = ""

        if visual_description:
            return _merge(visual_description, transcript)
        return transcript


async def _run_vision_on_video(url: str, vision: "VisionBackend") -> str:
    """Download video to a temp dir, extract frames, run vision. Returns empty string on failure."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = await _download_video(url, tmpdir)
            return await _run_vision_from_file(video_path, tmpdir, vision)
    except Exception as e:
        logger.warning("Vision analysis failed (download): %s", e)
        return ""


async def _run_vision_from_file(
    video_path: str, frame_dir: str, vision: "VisionBackend"
) -> str:
    """Extract keyframes from an already-downloaded video and run vision. Returns empty string on failure."""
    try:
        from bot.vision.base import extract_keyframes
        frame_paths = await extract_keyframes(video_path, frame_dir)
        if not frame_paths:
            return ""
        description = await vision.analyze_frames(frame_paths)
        logger.info("Vision analysis complete (%d chars)", len(description))
        return description
    except Exception as e:
        logger.warning("Vision analysis failed: %s", e)
        return ""


def _merge(visual_description: str, transcript: str) -> str:
    return f"[VISUAL CONTENT]\n{visual_description}\n\n[AUDIO TRANSCRIPT]\n{transcript}"


def _extract_transcript_section(combined: str) -> str:
    """Pull out just the audio transcript portion for storage, or return the whole string."""
    marker = "[AUDIO TRANSCRIPT]\n"
    idx = combined.find(marker)
    if idx != -1:
        return combined[idx + len(marker):]
    return combined


async def _fetch_captions(url: str) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

        video_id = _extract_video_id(url)
        if not video_id:
            return ""

        import asyncio
        loop = asyncio.get_event_loop()

        def _fetch() -> str:
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                try:
                    transcript = transcript_list.find_manually_created_transcript(
                        ["en", "en-US", "en-GB"]
                    )
                except Exception:
                    transcript = transcript_list.find_generated_transcript(
                        ["en", "en-US", "en-GB"]
                    )
                segments = transcript.fetch()
                return " ".join(seg["text"] for seg in segments)
            except (TranscriptsDisabled, NoTranscriptFound):
                return ""

        return await loop.run_in_executor(None, _fetch)

    except Exception as e:
        logger.warning("Caption fetch failed: %s", e)
        return ""


async def _download_video(url: str, output_dir: str) -> str:
    """Download audio (or muxed fallback) for the given URL. Returns the local file path."""
    import asyncio
    import yt_dlp  # type: ignore

    output_template = str(Path(output_dir) / "video.%(ext)s")

    ydl_opts = {
        # Prefer audio-only to minimise download size; fall back to low-res muxed
        # when only combined streams are available (common on some Shorts).
        "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best[height<=480]/best",
        "format_sort": ["abr", "asr"],  # prefer higher audio bitrate/sample-rate
        "outtmpl": output_template,
        "ignoreerrors": False,
        "no_warnings": False,
        # Try multiple player clients in order so that if one is rate-limited or
        # blocked (triggering "nsig extraction failed"), the next one takes over.
        "extractor_args": {
            "youtube": {
                "player_client": ["web", "mweb", "android", "android_vr"],
                "player_skip": ["webpage"],
            }
        },
    }

    loop = asyncio.get_event_loop()

    def _download() -> str:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        for f in Path(output_dir).iterdir():
            if f.suffix in (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".ogg", ".opus"):
                return str(f)
        raise FileNotFoundError("Downloaded file not found after yt-dlp download")

    return await loop.run_in_executor(None, _download)


def _run_whisper(video_path: str) -> str:
    from faster_whisper import WhisperModel  # type: ignore

    logger.info("Running whisper on %s", video_path)
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(video_path, beam_size=5)
    return " ".join(seg.text.strip() for seg in segments)


def _extract_video_id(url: str) -> str:
    import re

    m = re.search(r"youtube\.com/shorts/([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    m = re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    return ""
