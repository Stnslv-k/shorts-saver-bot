from __future__ import annotations

from urllib.parse import urlparse

BAD_DOMAINS = {
    "zhihu.com", "reddit.com", "quora.com", "stackoverflow.com",
    "stackexchange.com", "wikipedia.org", "youtube.com", "twitter.com",
    "x.com", "facebook.com", "linkedin.com",
    "hackernews.com", "news.ycombinator.com",
    "gr.com",
}

BLOG_DOMAINS = {
    "medium.com", "dev.to", "plainenglish.io", "hackernoon.com",
    "towardsdatascience.com", "substack.com", "wordpress.com", "blogger.com",
    "techcrunch.com", "theverge.com", "wired.com", "zdnet.com",
    "venturebeat.com", "infoq.com", "dzone.com",
}

# Still useful for Google-ecosystem tools — contribute +1 to scoring.
PREFERRED_DOMAINS = {
    "withgoogle.com", "ai.google.dev", "labs.google", "deepmind.google",
}

_GOOD_TLDS = {".io", ".ai", ".dev", ".app", ".tools"}
_NEWS_PATH_SEGMENTS = {"/news/", "/blog/", "/article/", "/post/", "/press/",
                       "/2024/", "/2025/", "/2026/"}
_DOCS_PREFIXES = ("docs.", "developer.", "developers.")


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _is_bad_domain(url: str) -> bool:
    host = _host(url)
    return any(host == d or host.endswith("." + d) for d in BAD_DOMAINS)


def _score(url: str, tool_name: str) -> int:
    score = 0
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().lstrip("www.")
        path = parsed.path.lower()
        name = tool_name.lower().replace(" ", "").replace("-", "").replace("_", "")
        host_clean = host.replace("-", "").replace("_", "").replace(".", "")

        # Blog/news aggregator → big penalty
        if any(host == d or host.endswith("." + d) for d in BLOG_DOMAINS):
            score -= 3

        # News/article-style paths → penalty
        if any(seg in path for seg in _NEWS_PATH_SEGMENTS):
            score -= 2

        # Tool name appears in domain (not just path) → strong signal of official page
        if name and name in host_clean:
            score += 3

        # GitHub repo whose name matches the tool
        if host == "github.com":
            path_parts = path.strip("/").split("/")
            if len(path_parts) >= 2:
                repo = path_parts[1].lower().replace("-", "").replace("_", "")
                if name and name == repo:
                    score += 2

        # Docs/developer subdomain → likely official docs
        if any(host.startswith(p) for p in _DOCS_PREFIXES):
            score += 1

        # Good product/dev TLD
        tld = host.rsplit(".", 1)[-1]
        if "." + tld in _GOOD_TLDS:
            score += 1

        # Google-ecosystem preferred domains
        for d in PREFERRED_DOMAINS:
            if host == d or host.endswith("." + d):
                score += 1
                break

    except Exception:
        pass
    return score


def pick_best_url(urls: list[str], tool_name: str = "") -> str | None:
    """Return the URL with highest relevance score, skipping blocked domains."""
    candidates = [(u, _score(u, tool_name)) for u in urls if not _is_bad_domain(u)]
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[1])[0]


def build_query(tool_name: str, context: str = "", video_context: str = "") -> str:
    parts = [f'"{tool_name}"']
    if video_context:
        parts.append(video_context)
    if context:
        parts.append(context)
    parts.append("official site")
    return " ".join(parts)
