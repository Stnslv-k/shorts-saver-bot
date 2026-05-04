from __future__ import annotations

from abc import ABC, abstractmethod

from bot.models import ExtractionResult

EXTRACTION_PROMPT = """\
You are a knowledge extraction assistant. Analyze the following transcript from a YouTube Short and extract structured information.

Return ONLY a valid JSON object with this exact structure:
{
  "title": "concise title for this content",
  "category": "one of: github, recipe, tool, article, general",
  "summary": "2-3 sentence summary of the main content and key takeaways",
  "github_repos": [
    {"name": "repo-name", "url": "https://github.com/...", "description": "what it does"}
  ],
  "recipe": {
    "name": "recipe name",
    "ingredients": ["ingredient 1", "ingredient 2"],
    "steps": ["step 1", "step 2"]
  },
  "tools": ["tool or app name 1", "tool or app name 2"],
  "tags": ["tag1", "tag2", "tag3"]
}

Category selection rules:
- "github": transcript mentions GitHub repositories, code projects, or programming tools with links
- "recipe": transcript describes food preparation, ingredients, or cooking steps
- "tool": transcript showcases software tools, apps, or utilities (no GitHub repos)
- "article": transcript discusses ideas, news, or informational content
- "general": anything else

GitHub URL extraction:
- Detect both explicit URLs (https://github.com/user/repo) and spoken forms ("github dot com slash user slash repo")
- Normalize spoken forms to proper URLs
- If no repos are mentioned, return an empty array

Recipe extraction:
- Only populate if category is "recipe"
- Otherwise return null for the recipe field

Tools extraction:
- List any software tools, apps, frameworks, or services mentioned
- Return empty array if none

Tags:
- Generate 3-5 relevant tags
- Use lowercase, hyphenated format (e.g. "machine-learning", "python", "productivity")

Transcript:
{transcript}
"""


class LLMBackend(ABC):
    @abstractmethod
    async def extract(self, transcript: str) -> ExtractionResult:
        """Extract structured data from a transcript."""
        ...
