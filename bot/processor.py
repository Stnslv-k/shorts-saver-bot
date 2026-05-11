from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING

from bot.llm.base import LLMBackend
from bot.models import ExtractionResult, KnowledgeEntry
from bot.storage.base import StorageBackend

if TYPE_CHECKING:
    from bot.search.base import SearchBackend
    from bot.vision.base import VisionBackend

logger = logging.getLogger(__name__)


class NoTranscriptError(RuntimeError):
    """Raised when neither captions nor fallback download/transcription produce input."""


async def process_url(
    url: str,
    llm: LLMBackend,
    storage: StorageBackend,
    vision: "VisionBackend | None" = None,
    search: "SearchBackend | None" = None,
) -> tuple[KnowledgeEntry, str, str, str]:
    """
    Full pipeline: URL → transcript (+ optional vision) → LLM extraction → storage.
    Returns (entry, confirmation_message, storage_ref, model_name).
    """
    combined_input = await _build_llm_input(url, vision)
    if not combined_input.strip():
        raise NoTranscriptError(
            "Could not extract captions, download audio, or analyze visual content for this video."
        )

    logger.info("LLM input ready (%d chars) for %s", len(combined_input), url)

    result, model_name = await llm.extract(combined_input)
    logger.info("Extracted: category=%s title=%r model=%s", result.category, result.title, model_name)

    if search is not None:
        result = await _enrich_with_urls(result, search)

    # Store only the raw audio transcript in the entry, not the combined prompt
    raw_transcript = _extract_transcript_section(combined_input)
    entry = KnowledgeEntry.from_extraction(result, source_url=url, raw_transcript=raw_transcript)
    confirmation, storage_ref = await storage.save(entry)
    return entry, confirmation, storage_ref, model_name


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


def _short_video_context(title: str) -> str:
    """Return up to 6 words from the video title for use as search context."""
    words = title.split()
    return " ".join(words[:6])


async def _enrich_with_urls(result: ExtractionResult, search: "SearchBackend") -> ExtractionResult:
    """Find URLs for tools and GitHub repos that don't have one."""
    from bot.search.brave import BraveSearchBackend
    from bot.search.duckduckgo import DuckDuckGoBackend

    video_context = _short_video_context(result.title) if result.title else ""
    is_ddg = isinstance(search, DuckDuckGoBackend)

    async def _find_tool_url(tool: dict) -> str | None:
        if tool.get("url"):
            return tool["url"]
        if not _looks_like_product_name(tool["name"]):
            return None
        return await search.find_url(tool["name"], context="developer tool", video_context=video_context)

    async def _find_repo_url(repo: dict) -> str | None:
        if repo.get("url"):
            return repo["url"]
        return await search.find_url(repo["name"], context="github", video_context=video_context)

    if is_ddg:
        # DuckDuckGo rate-limits under parallel load — run sequentially with a small delay
        tool_urls: list[str | None] = []
        for tool in result.tools:
            url = await _find_tool_url(tool)
            tool_urls.append(url)
            await asyncio.sleep(0.5)

        repo_urls: list[str | None] = []
        for repo in result.github_repos:
            url = await _find_repo_url(repo)
            repo_urls.append(url)
            await asyncio.sleep(0.5)
    else:
        # Brave handles concurrency fine — gather all at once
        tool_results = await asyncio.gather(
            *[_find_tool_url(tool) for tool in result.tools], return_exceptions=True
        )
        repo_results = await asyncio.gather(
            *[_find_repo_url(repo) for repo in result.github_repos], return_exceptions=True
        )
        tool_urls = [u if isinstance(u, str) else None for u in tool_results]
        repo_urls = [u if isinstance(u, str) else None for u in repo_results]

    enriched_tools = [
        {"name": tool["name"], "url": url or tool.get("url")}
        for tool, url in zip(result.tools, tool_urls)
    ]
    enriched_repos = [
        {**repo, "url": repo.get("url") or url}
        for repo, url in zip(result.github_repos, repo_urls)
    ]

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

    base_opts = {
        # Prefer audio-only to minimise download size; fall back to low-res muxed
        # when only combined streams are available (common on some Shorts).
        "outtmpl": output_template,
        "ignoreerrors": False,
        "no_warnings": False,
    }
    _apply_yt_dlp_auth(base_opts)

    loop = asyncio.get_event_loop()

    def _download() -> str:
        last_error: Exception | None = None
        for candidate in _yt_dlp_format_candidates():
            ydl_opts = deepcopy(base_opts)
            ydl_opts.update(candidate)
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                return _find_downloaded_media(output_dir)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "yt-dlp download attempt failed with format=%s: %s",
                    ydl_opts.get("format"),
                    exc,
                )
                if not _is_retryable_yt_dlp_error(exc):
                    raise
        if last_error is not None:
            raise last_error
        raise FileNotFoundError("Downloaded file not found after yt-dlp download")

    return await loop.run_in_executor(None, _download)


def _yt_dlp_format_candidates() -> list[dict]:
    return [
        {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best[height<=480]/best",
            "format_sort": ["abr", "asr"],
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "mweb", "android", "android_vr"],
                    "player_skip": ["webpage"],
                }
            },
        },
        {
            "format": "140/bestaudio/best",
            "extractor_args": {
                "youtube": {
                    "player_client": ["web", "mweb", "android"],
                }
            },
        },
        {
            "format": "bestaudio/best",
        },
        {
            "format": "best",
        },
    ]


def _find_downloaded_media(output_dir: str) -> str:
    for f in Path(output_dir).iterdir():
        if f.suffix in (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".ogg", ".opus"):
            return str(f)
    raise FileNotFoundError("Downloaded file not found after yt-dlp download")


def _is_retryable_yt_dlp_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "requested format is not available" in message
        or "sign in to confirm you're not a bot" in message
        or "http error 403" in message
    )


def _apply_yt_dlp_auth(ydl_opts: dict) -> None:
    cookies_from_browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    cookies_file = os.getenv("YTDLP_COOKIES_FILE", "").strip()

    if cookies_from_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_from_browser,)
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file


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
