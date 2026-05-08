from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from bot.config import LLMConfig, OpenRouterConfig
from bot.llm import build_llm_backend


class OpenRouterBackendTest(unittest.IsolatedAsyncioTestCase):
    async def test_openrouter_can_build_without_paid_fallback_key(self) -> None:
        backend = build_llm_backend(
            LLMConfig(
                backend="openrouter",
                fallback="openai",
                openrouter=OpenRouterConfig(api_key="sk-or-test"),
            )
        )

        with (
            patch("bot.llm.openrouter._get_models", AsyncMock(return_value=([], "openrouter/free"))),
            patch("bot.llm.openrouter._call_openrouter", AsyncMock(side_effect=RuntimeError("free exhausted"))),
        ):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY is missing"):
                await backend.extract("transcript")


if __name__ == "__main__":
    unittest.main()
