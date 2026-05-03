from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

from .base import Item, Source

log = logging.getLogger(__name__)


class GoogleResearchSource(Source):
    """Google Research Blog (formerly Google AI Blog at ai.googleblog.com,
    which now 301s here). RSS at /blog/rss/ is server-rendered and clean."""
    name = "google_research"

    def fetch(self) -> list[Item]:
        url = self.config.get("rss_url", "https://research.google/blog/rss/")
        days = int(self.config.get("days", 14))
        max_results = int(self.config.get("max_results", 15))
        proxy = self.config.get("proxy")
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        proxies = {"http": proxy, "https": proxy} if proxy else None
        try:
            r = requests.get(
                url,
                timeout=20,
                proxies=proxies,
                headers={"User-Agent": "explorer-agent"},
            )
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except (requests.RequestException, ET.ParseError) as e:
            log.warning("google_research feed fetch failed: %s", e)
            return []

        items: list[Item] = []
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            if not title or not link:
                continue
            guid = (it.findtext("guid") or link).strip()

            published: datetime | None = None
            pubdate_str = (it.findtext("pubDate") or "").strip()
            if pubdate_str:
                try:
                    published = parsedate_to_datetime(pubdate_str)
                except (TypeError, ValueError):
                    published = None
            if published is not None and published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published is not None and published < cutoff:
                continue

            cats = [c.text.strip() for c in it.findall("category") if c.text]

            items.append(Item(
                source=self.name,
                source_label="Google Research Blog",
                id=guid,
                title=title,
                url=link,
                summary=", ".join(cats),
                published=published,
                extra={"categories": cats},
            ))

        items.sort(
            key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return items[:max_results]
