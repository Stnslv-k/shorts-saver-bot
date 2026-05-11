from __future__ import annotations

import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from bot import processor
from bot.models import ExtractionResult


class ProcessorHelpersTest(unittest.TestCase):
    def test_extract_video_id_from_shorts_url(self) -> None:
        self.assertEqual(
            processor._extract_video_id("https://www.youtube.com/shorts/abcDEF12345"),
            "abcDEF12345",
        )

    def test_extract_video_id_from_youtu_be_url(self) -> None:
        self.assertEqual(
            processor._extract_video_id("https://youtu.be/abcDEF12345?si=test"),
            "abcDEF12345",
        )

    def test_extract_transcript_section_prefers_audio_marker(self) -> None:
        combined = "[VISUAL CONTENT]\nshown text\n\n[AUDIO TRANSCRIPT]\nspoken text"
        self.assertEqual(processor._extract_transcript_section(combined), "spoken text")

    def test_yt_dlp_error_is_retryable_for_unavailable_format(self) -> None:
        self.assertTrue(
            processor._is_retryable_yt_dlp_error(
                RuntimeError("Requested format is not available")
            )
        )

    def test_find_downloaded_media_returns_existing_audio_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/video.m4a"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("x")
            self.assertEqual(processor._find_downloaded_media(tmpdir), path)


class ProcessorFailureTest(unittest.IsolatedAsyncioTestCase):
    async def test_process_url_rejects_empty_content_before_llm(self) -> None:
        llm = AsyncMock()
        storage = AsyncMock()

        with patch.object(processor, "_build_llm_input", AsyncMock(return_value="")):
            with self.assertRaises(processor.NoTranscriptError):
                await processor.process_url("https://youtu.be/abcDEF12345", llm, storage)

        llm.extract.assert_not_called()
        storage.save.assert_not_called()

    async def test_process_url_returns_model_name_from_llm(self) -> None:
        result = ExtractionResult(
            title="A useful Short",
            category="tool",
            summary="Summary",
            tools=[{"name": "Example", "url": None}],
            tags=["example"],
        )
        llm = AsyncMock()
        llm.extract.return_value = (result, "test-model")
        storage = AsyncMock()
        storage.save.return_value = ("saved", "storage-ref")

        with patch.object(processor, "_build_llm_input", AsyncMock(return_value="Transcript")):
            entry, confirmation, storage_ref, model_name = await processor.process_url(
                "https://youtu.be/abcDEF12345", llm, storage
            )

        self.assertEqual(entry.title, "A useful Short")
        self.assertEqual(confirmation, "saved")
        self.assertEqual(storage_ref, "storage-ref")
        self.assertEqual(model_name, "test-model")


if __name__ == "__main__":
    unittest.main()
