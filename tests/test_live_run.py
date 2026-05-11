from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest.mock import patch

from bot.live_run import _apply_runtime_overrides, build_result_payload, validate_url
from bot.models import KnowledgeEntry


class LiveRunHelpersTest(unittest.TestCase):
    def test_validate_url_accepts_shorts_url(self) -> None:
        self.assertEqual(
            validate_url("https://www.youtube.com/shorts/abcDEF12345"),
            "https://www.youtube.com/shorts/abcDEF12345",
        )

    def test_validate_url_rejects_non_shorts_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "YouTube Shorts URL"):
            validate_url("https://www.youtube.com/watch?v=abcDEF12345")

    def test_build_result_payload_contains_core_fields(self) -> None:
        entry = KnowledgeEntry(
            title="Useful Short",
            category="tool",
            summary="A compact summary.",
            source_url="https://youtu.be/abcDEF12345",
            extracted_at=datetime.utcnow(),
            tags=["ai", "video"],
            tools=[{"name": "Tool", "url": None}],
        )

        payload = build_result_payload(
            entry=entry,
            model_name="test-model",
            storage_ref="note.md",
            history_id=42,
        )

        self.assertEqual(payload["title"], "Useful Short")
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["storage_ref"], "note.md")
        self.assertEqual(payload["history_id"], 42)

    def test_apply_runtime_overrides_sets_cookie_env(self) -> None:
        args = type(
            "Args",
            (),
            {"cookies_from_browser": "brave", "cookies": "/tmp/cookies.txt"},
        )()

        with patch.dict(os.environ, {}, clear=True):
            _apply_runtime_overrides(args)
            self.assertEqual(os.environ["YTDLP_COOKIES_FROM_BROWSER"], "brave")
            self.assertEqual(os.environ["YTDLP_COOKIES_FILE"], "/tmp/cookies.txt")


if __name__ == "__main__":
    unittest.main()
