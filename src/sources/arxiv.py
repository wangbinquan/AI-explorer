from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from .base import Item, Source

log = logging.getLogger(__name__)


class ArxivSource(Source):
    name = "arxiv"

    def _fetch_with_retry(self, url: str, timeout: int = 60, retries: int = 3) -> requests.Response | None:
        backoff = 2
        for attempt in range(1, retries + 1):
            try:
                r = requests.get(url, timeout=timeout, headers={"User-Agent": "explorer-agent"})
                r.raise_for_status()
                return r
            except Exception as e:
                if attempt == retries:
                    log.warning("arxiv fetch failed after %d attempts for %s: %s", retries, url, e)
                    return None
                log.info("arxiv fetch attempt %d/%d failed (%s); retrying in %ds", attempt, retries, e, backoff)
                time.sleep(backoff)
                backoff *= 2
        return None

    def fetch(self) -> list[Item]:
        cats = self.config.get("categories", ["cs.AI"])
        max_per = int(self.config.get("max_per_category", 30))
        days = int(self.config.get("days", 2))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        items: list[Item] = []
        for cat in cats:
            url = (
                "https://export.arxiv.org/api/query"
                f"?search_query=cat:{cat}&sortBy=submittedDate&sortOrder=descending"
                f"&max_results={max_per}"
            )
            r = self._fetch_with_retry(url)
            if r is None:
                continue
            feed = feedparser.parse(r.content)
            for e in feed.entries:
                pub = None
                if getattr(e, "published_parsed", None):
                    pub = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
                if pub and pub < cutoff:
                    continue
                arxiv_id = e.id.rsplit("/", 1)[-1]
                authors = ", ".join(a.name for a in getattr(e, "authors", [])[:5])
                items.append(Item(
                    source=self.name,
                    source_label=f"arXiv {cat}",
                    id=f"arxiv:{arxiv_id}",
                    title=e.title.replace("\n", " ").strip(),
                    url=e.link,
                    summary=e.summary.replace("\n", " ").strip(),
                    published=pub,
                    extra={"category": cat, "authors": authors},
                ))
        return items
