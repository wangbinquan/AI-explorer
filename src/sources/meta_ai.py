from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from .base import Item, Source

log = logging.getLogger(__name__)


_POST_RE = re.compile(r"^https?://ai\.meta\.com/blog/([a-z0-9][a-z0-9-]+)/?$")
_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s*(20\d\d)"
)

# Meta serves an "Sorry, something went wrong." page unless the request looks like
# a real browser navigation (Sec-Fetch-* + locale cookie).
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Cookie": "locale=en_US",
}


class MetaAISource(Source):
    """Meta AI Blog (https://ai.meta.com/blog/, formerly ai.facebook.com/blog).
    No RSS or sitemap — we scrape the list page for (url, date), then fetch each
    post for og:title. Same proxy story as Google: blocked from CN without one."""
    name = "meta_ai"

    def fetch(self) -> list[Item]:
        list_url = self.config.get("list_url", "https://ai.meta.com/blog/")
        days = int(self.config.get("days", 14))
        max_results = int(self.config.get("max_results", 15))
        proxy = self.config.get("proxy")
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        proxies = {"http": proxy, "https": proxy} if proxy else None

        try:
            r = requests.get(list_url, timeout=20, headers=_BROWSER_HEADERS, proxies=proxies)
            r.raise_for_status()
        except requests.RequestException as e:
            log.warning("meta_ai list fetch failed: %s", e)
            return []

        candidates = _parse_list(r.text)
        candidates = [c for c in candidates if c[1] >= cutoff]
        # Same post often appears in both "Featured" and "Latest News" — dedup by url,
        # keep the earlier-found entry (which is the featured one with the cleanest title).
        seen: set[str] = set()
        unique: list[tuple[str, datetime, str, str]] = []
        for url, dt, title, slug in candidates:
            if url in seen:
                continue
            seen.add(url)
            unique.append((url, dt, title, slug))
        unique.sort(key=lambda c: c[1], reverse=True)
        unique = unique[:max_results]

        items: list[Item] = []
        for url, dt, fallback_title, slug in unique:
            title, summary = _fetch_meta(url, proxies)
            if not title:
                title = fallback_title or slug.replace("-", " ").capitalize()
            items.append(Item(
                source=self.name,
                source_label="Meta AI Blog",
                id=f"meta_ai:{slug}",
                title=title,
                url=url,
                summary=summary,
                published=dt,
                extra={"slug": slug},
            ))
        return items


def _parse_list(html: str) -> list[tuple[str, datetime, str, str]]:
    """Return (url, published_utc, fallback_title, slug) for each post tile on the list page."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[str, datetime, str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0].split("#")[0]
        m = _POST_RE.match(href)
        if not m:
            continue
        slug = m.group(1)
        # Walk up to the smallest ancestor that contains exactly this one post link
        # AND a date string. Stop early if a parent contains multiple post links
        # (we've left the card and entered the grid).
        node = a
        text = ""
        for _ in range(8):
            node = node.parent
            if node is None:
                break
            link_count = sum(
                1 for x in node.find_all("a", href=True)
                if _POST_RE.match(x["href"].split("?")[0].split("#")[0])
            )
            if link_count > 1:
                text = ""
                break
            t = " ".join(node.get_text(" ", strip=True).split())
            if _DATE_RE.search(t) and len(t) > 30:
                text = t
                break
        if not text:
            continue
        dm = _DATE_RE.search(text)
        try:
            dt = datetime.strptime(f"{dm.group(1)} {int(dm.group(2))} {dm.group(3)}", "%B %d %Y")
        except ValueError:
            continue
        dt = dt.replace(tzinfo=timezone.utc)
        title = text.replace(dm.group(0), " ")
        title = re.sub(r"\s+(Learn More|FEATURED)\s*$", "", title).strip()
        title = re.sub(r"^FEATURED\s+", "", title).strip()
        title = re.sub(r"\s+", " ", title)
        out.append((href, dt, title[:200], slug))
    return out


def _fetch_meta(url: str, proxies: dict | None) -> tuple[str, str]:
    try:
        r = requests.get(url, timeout=15, headers=_BROWSER_HEADERS, proxies=proxies)
        r.raise_for_status()
    except requests.RequestException as e:
        log.info("meta_ai meta fetch failed (%s): %s — falling back to list title", url, e)
        return "", ""
    soup = BeautifulSoup(r.text, "html.parser")

    def meta(prop_key: str, prop_val: str) -> str:
        tag = soup.find("meta", attrs={prop_key: prop_val})
        return ((tag.get("content") if tag else "") or "").strip()

    title = (
        meta("property", "og:title")
        or meta("name", "og:title")
        or meta("name", "twitter:title")
    )
    desc = (
        meta("property", "og:description")
        or meta("name", "og:description")
        or meta("name", "description")
    )
    return title, desc[:500]
