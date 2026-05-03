from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

from .base import Item, Source

log = logging.getLogger(__name__)


_SECTION_LABEL = {
    "news": "Anthropic News",
    "research": "Anthropic Research",
    "engineering": "Anthropic Engineering",
}


class AnthropicSource(Source):
    """Anthropic news/research/engineering posts. No RSS — discovers via sitemap.xml."""
    name = "anthropic"

    def fetch(self) -> list[Item]:
        sections = self.config.get("sections", ["news", "research", "engineering"])
        days = int(self.config.get("days", 7))
        max_results = int(self.config.get("max_results", 15))
        sitemap_url = self.config.get("sitemap_url", "https://www.anthropic.com/sitemap.xml")
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        headers = {"User-Agent": "explorer-agent"}

        try:
            r = requests.get(sitemap_url, timeout=20, headers=headers)
            r.raise_for_status()
        except Exception as e:
            log.warning("anthropic sitemap fetch failed (%s): %s", sitemap_url, e)
            return []

        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError as e:
            log.warning("anthropic sitemap parse failed: %s", e)
            return []

        candidates: list[tuple[datetime, str, str, str]] = []  # (lastmod, section, slug, url)
        for url_el in root.findall(f"{ns}url"):
            loc_el = url_el.find(f"{ns}loc")
            lm_el = url_el.find(f"{ns}lastmod")
            if loc_el is None or lm_el is None:
                continue
            url = (loc_el.text or "").strip()
            m = re.match(r"https://www\.anthropic\.com/([^/]+)/(.+)$", url)
            if not m:
                continue
            section, slug = m.group(1), m.group(2)
            if section not in sections or "/" in slug:
                continue
            try:
                lastmod = datetime.fromisoformat((lm_el.text or "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if lastmod < cutoff:
                continue
            candidates.append((lastmod, section, slug, url))

        candidates.sort(key=lambda c: c[0], reverse=True)
        candidates = candidates[:max_results]

        items: list[Item] = []
        for lastmod, section, slug, url in candidates:
            title, summary = _fetch_meta(url, headers)
            if not title:
                title = slug.replace("-", " ").strip().capitalize()
            items.append(Item(
                source=self.name,
                source_label=_SECTION_LABEL.get(section, f"Anthropic {section}"),
                id=f"anthropic:{section}:{slug}",
                title=title,
                url=url,
                summary=summary,
                published=lastmod,
                extra={"section": section, "slug": slug},
            ))
        return items


def _fetch_meta(url: str, headers: dict) -> tuple[str, str]:
    try:
        r = requests.get(url, timeout=15, headers=headers)
        r.raise_for_status()
    except Exception as e:
        log.info("anthropic meta fetch failed (%s): %s — falling back to slug", url, e)
        return "", ""
    soup = BeautifulSoup(r.text, "html.parser")
    def meta(prop_key: str, prop_val: str) -> str:
        tag = soup.find("meta", attrs={prop_key: prop_val})
        return (tag.get("content") if tag else "") or ""
    title = meta("property", "og:title") or meta("name", "twitter:title")
    if not title:
        t = soup.find("title")
        title = t.get_text(strip=True) if t else ""
        title = re.sub(r"\s*\\?\s*Anthropic\s*$", "", title)
    desc = meta("property", "og:description") or meta("name", "description")
    desc = desc.strip()
    if desc.startswith("Anthropic is an AI safety and research company"):
        desc = ""
    return title.strip(), desc[:500]
