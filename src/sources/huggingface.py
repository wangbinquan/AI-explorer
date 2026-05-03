from __future__ import annotations

import logging
import time

import requests
from bs4 import BeautifulSoup

from .base import Item, Source

log = logging.getLogger(__name__)


class HuggingFacePapers(Source):
    """Scrape the daily papers page on huggingface.co."""
    name = "huggingface_papers"

    def _fetch_with_retry(self, url: str, timeout: int = 20, retries: int = 4) -> requests.Response | None:
        proxy = self.config.get("proxy")
        proxies = {"http": proxy, "https": proxy} if proxy else None
        backoff = 3
        for attempt in range(1, retries + 1):
            try:
                r = requests.get(
                    url,
                    timeout=timeout,
                    proxies=proxies,
                    headers={"User-Agent": "explorer-agent"},
                )
                r.raise_for_status()
                return r
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                retryable = status in (429, 500, 502, 503, 504)
                wait = backoff
                if status == 429 and e.response is not None:
                    ra = e.response.headers.get("Retry-After")
                    if ra and ra.isdigit():
                        wait = max(wait, int(ra))
                if not retryable or attempt == retries:
                    log.warning("huggingface_papers fetch failed after %d attempts for %s: %s", attempt, url, e)
                    return None
                log.info("huggingface_papers attempt %d/%d failed (%s); retrying in %ds", attempt, retries, e, wait)
                time.sleep(wait)
                backoff *= 2
            except Exception as e:
                if attempt == retries:
                    log.warning("huggingface_papers fetch failed after %d attempts for %s: %s", retries, url, e)
                    return None
                log.info("huggingface_papers attempt %d/%d failed (%s); retrying in %ds", attempt, retries, e, backoff)
                time.sleep(backoff)
                backoff *= 2
        return None

    def fetch(self) -> list[Item]:
        max_results = int(self.config.get("max_results", 30))
        base_url = self.config.get("base_url", "https://huggingface.co").rstrip("/")
        r = self._fetch_with_retry(f"{base_url}/papers")
        if r is None:
            log.warning("huggingface_papers giving up (base_url=%s)", base_url)
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        items: list[Item] = []
        seen: set[str] = set()
        for a in soup.select('a[href^="/papers/"]'):
            href = a.get("href", "")
            if not href.startswith("/papers/") or href.count("/") != 2:
                continue
            paper_id = href.rsplit("/", 1)[-1]
            if not paper_id or paper_id in seen:
                continue
            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            seen.add(paper_id)
            items.append(Item(
                source=self.name,
                source_label="HuggingFace Daily Papers",
                id=f"hfpaper:{paper_id}",
                title=title,
                url=f"{base_url}{href}",
                summary="",
                extra={"arxiv_id": paper_id},
            ))
            if len(items) >= max_results:
                break
        return items
