from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

from .base import Item, Source

log = logging.getLogger(__name__)


class HackerNewsSource(Source):
    name = "hackernews"

    def fetch(self) -> list[Item]:
        min_points = int(self.config.get("min_points", 150))
        days = int(self.config.get("days", 2))
        max_results = int(self.config.get("max_results", 60))

        ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        params = {
            "tags": "story",
            "numericFilters": f"points>={min_points},created_at_i>{ts}",
            "hitsPerPage": max_results,
        }
        try:
            r = requests.get("https://hn.algolia.com/api/v1/search", params=params, timeout=20)
            r.raise_for_status()
        except Exception as e:
            log.warning("hackernews fetch failed: %s", e)
            return []

        items: list[Item] = []
        for hit in r.json().get("hits", []):
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
            items.append(Item(
                source=self.name,
                source_label="Hacker News",
                id=f"hn:{hit['objectID']}",
                title=hit.get("title") or "(untitled)",
                url=url,
                summary=(hit.get("story_text") or "")[:500],
                extra={
                    "points": hit.get("points"),
                    "comments": hit.get("num_comments"),
                    "hn_url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
                },
            ))
        return items
