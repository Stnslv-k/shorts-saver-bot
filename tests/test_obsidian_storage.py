from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from bot.config import ObsidianConfig
from bot.models import KnowledgeEntry
from bot.storage.obsidian import ObsidianAdapter


class ObsidianAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_save_creates_markdown_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = ObsidianAdapter(ObsidianConfig(vault_path=tmpdir))
            entry = KnowledgeEntry(
                title="Useful Short",
                category="tool",
                summary="Summary",
                source_url="https://youtu.be/abcDEF12345",
                extracted_at=datetime.utcnow(),
            )

            _, ref = await adapter.save(entry)

            path = Path(ref)
            self.assertTrue(path.exists())
            self.assertIn("# Useful Short", path.read_text(encoding="utf-8"))

    async def test_save_fails_if_file_is_missing_after_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = ObsidianAdapter(ObsidianConfig(vault_path=tmpdir))
            entry = KnowledgeEntry(
                title="Useful Short",
                category="tool",
                summary="Summary",
                source_url="https://youtu.be/abcDEF12345",
                extracted_at=datetime.utcnow(),
            )

            with patch("pathlib.Path.exists", return_value=False):
                with self.assertRaisesRegex(FileNotFoundError, "was not created"):
                    await adapter.save(entry)


if __name__ == "__main__":
    unittest.main()
