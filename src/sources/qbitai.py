from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from .base import Item, Source

log = logging.getLogger(__name__)


_POST_ID_RE = re.compile(r"[?&]p=(\d+)")


class QbitaiSource(Source):
    """量子位 (qbitai.com) — Chinese AI news, via WordPress RSS."""
    name = "qbitai"

    def fetch(self) -> list[Item]:
        max_results = int(self.config.get("max_results", 20))
        days = int(self.config.get("days", 2))
        feed_url = self.config.get("feed_url", "https://www.qbitai.com/feed")
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            r = requests.get(feed_url, timeout=20, headers={"User-Agent": "explorer-agent"})
            r.raise_for_status()
        except Exception as e:
            log.warning("qbitai fetch failed (%s): %s", feed_url, e)
            return []
        feed = feedparser.parse(r.content)
        items: list[Item] = []
        for e in feed.entries[:max_results]:
            pub = None
            if getattr(e, "published_parsed", None):
                pub = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
            if pub and pub < cutoff:
                continue

            guid = getattr(e, "id", "") or getattr(e, "guid", "") or e.link
            m = _POST_ID_RE.search(guid)
            post_id = m.group(1) if m else guid

            tags = [t.term for t in getattr(e, "tags", []) if getattr(t, "term", None)]
            author = getattr(e, "author", "")
            summary = re.sub(r"<[^>]+>", "", getattr(e, "summary", "") or "").strip()

            items.append(Item(
                source=self.name,
                source_label="量子位",
                id=f"qbitai:{post_id}",
                title=e.title.replace("\n", " ").strip(),
                url=e.link,
                summary=summary[:500],
                published=pub,
                extra={"author": author, "tags": tags},
            ))
        return items
