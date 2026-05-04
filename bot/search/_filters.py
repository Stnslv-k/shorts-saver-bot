from __future__ import annotations

from urllib.parse import urlparse

BAD_DOMAINS = {
    "zhihu.com", "reddit.com", "quora.com", "stackoverflow.com",
    "stackexchange.com", "wikipedia.org", "youtube.com", "twitter.com",
    "x.com", "facebook.com", "linkedin.com", "medium.com", "dev.to",
    "hackernews.com", "news.ycombinator.com",
}

PREFERRED_DOMAINS = {"github.com", ".dev", ".io", ".ai"}


def _is_bad_domain(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        return any(host == d or host.endswith("." + d) for d in BAD_DOMAINS)
    except Exception:
        return False


def _is_preferred_domain(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        return any(host == d or host.endswith(d) for d in PREFERRED_DOMAINS)
    except Exception:
        return False


def pick_best_url(urls: list[str]) -> str | None:
    """Return first preferred-domain URL, or first non-blocked URL, or None."""
    candidates = [u for u in urls if not _is_bad_domain(u)]
    for url in candidates:
        if _is_preferred_domain(url):
            return url
    return candidates[0] if candidates else None


def build_query(tool_name: str, context: str) -> str:
    if context:
        return f'"{tool_name}" {context} official site'
    return f'"{tool_name}" developer tool official site'
