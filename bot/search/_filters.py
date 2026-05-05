from __future__ import annotations

from urllib.parse import urlparse

BAD_DOMAINS = {
    "zhihu.com", "reddit.com", "quora.com", "stackoverflow.com",
    "stackexchange.com", "wikipedia.org", "youtube.com", "twitter.com",
    "x.com", "facebook.com", "linkedin.com", "medium.com", "dev.to",
    "hackernews.com", "news.ycombinator.com",
    "plainenglish.io", "gr.com",
}

# TLD suffixes start with ".", full domains don't.
PREFERRED_DOMAINS = {
    "github.com", ".dev", ".io", ".ai",
    "withgoogle.com", "ai.google.dev", "labs.google", "deepmind.google",
}

GOOGLE_SITE_QUERY = "site:withgoogle.com OR site:ai.google.dev OR site:labs.google OR site:deepmind.google"

_GOOGLE_KEYWORDS = frozenset({"google", "gemini", "deepmind", "vertex", "bard"})


def _is_bad_domain(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        return any(host == d or host.endswith("." + d) for d in BAD_DOMAINS)
    except Exception:
        return False


def _is_preferred_domain(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        for d in PREFERRED_DOMAINS:
            if d.startswith("."):
                if host.endswith(d):
                    return True
            else:
                if host == d or host.endswith("." + d):
                    return True
        return False
    except Exception:
        return False


def is_google_context(video_context: str) -> bool:
    words = video_context.lower().split()
    return any(w in _GOOGLE_KEYWORDS for w in words)


def pick_best_url(urls: list[str]) -> str | None:
    """Return first preferred-domain URL, or first non-blocked URL, or None."""
    candidates = [u for u in urls if not _is_bad_domain(u)]
    for url in candidates:
        if _is_preferred_domain(url):
            return url
    return candidates[0] if candidates else None


def build_query(tool_name: str, context: str = "", video_context: str = "") -> str:
    parts = [f'"{tool_name}"']
    if video_context:
        if is_google_context(video_context):
            parts.append("google")
        parts.append(video_context)
    if context:
        parts.append(context)
    parts.append("official site")
    return " ".join(parts)
