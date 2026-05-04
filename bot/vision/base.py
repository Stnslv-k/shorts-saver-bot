from __future__ import annotations

import asyncio
import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

VISION_PROMPT = """\
Analyze these keyframes from a YouTube Short video. Describe everything that is visible, focusing on:

- Any text overlays, captions, or titles shown on screen
- Code snippets or terminal output displayed
- GitHub repository names or URLs (written or shown on screen)
- App names, website URLs, or tool interfaces visible
- What is being demonstrated or shown
- Any product names, brand names, or social media handles

Be specific and thorough — this description will be combined with an audio transcript to extract structured knowledge from the video. List each distinct visual element you can identify.
"""


class VisionBackend(ABC):
    @abstractmethod
    async def analyze_frames(self, frame_paths: list[str]) -> str:
        """Analyze a list of image file paths and return a text description."""
        ...


async def extract_keyframes(video_path: str, output_dir: str) -> list[str]:
    """
    Extract 5 keyframes at 0%, 25%, 50%, 75%, 100% of the video duration.
    Returns a list of absolute paths to the saved JPEG files.
    Returns an empty list if the file has no video stream (e.g. audio-only m4a).
    """
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "quiet",
        "-select_streams", "v",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        video_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if not stdout.strip():
        logger.debug("No video stream in %s, skipping frame extraction", video_path)
        return []

    duration = await _probe_duration(video_path)
    if duration <= 0:
        raise ValueError(f"Could not determine duration of {video_path}")

    # Sample positions: beginning, 25%, 50%, 75%, end (clamped to avoid black final frame)
    positions = [
        0.0,
        duration * 0.25,
        duration * 0.50,
        duration * 0.75,
        max(0.0, duration - 0.5),
    ]

    frame_paths: list[str] = []
    tasks = [
        _extract_frame(video_path, output_dir, pos, idx)
        for idx, pos in enumerate(positions)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("Failed to extract frame %d: %s", idx, result)
        else:
            frame_paths.append(result)  # type: ignore[arg-type]

    if not frame_paths:
        raise RuntimeError("No frames could be extracted from the video")

    logger.info("Extracted %d keyframes from %s", len(frame_paths), video_path)
    return frame_paths


async def _probe_duration(video_path: str) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {stderr.decode().strip()}")
    try:
        return float(stdout.decode().strip())
    except ValueError as e:
        raise RuntimeError(f"ffprobe returned non-numeric duration: {stdout!r}") from e


async def _extract_frame(
    video_path: str, output_dir: str, timestamp: float, idx: int
) -> str:
    out_path = str(Path(output_dir) / f"frame_{idx:02d}.jpg")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-ss", f"{timestamp:.3f}",
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",          # high quality JPEG
        "-vf", "scale=1280:-1",  # normalize width, preserve aspect ratio
        "-y",
        out_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg frame extraction failed at {timestamp:.2f}s: {stderr.decode().strip()}"
        )
    return out_path
