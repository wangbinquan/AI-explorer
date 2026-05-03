from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from .base import Item, Source

log = logging.getLogger(__name__)


def _gh_headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "explorer-agent"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


class GitHubTrending(Source):
    name = "github_trending"

    def fetch(self) -> list[Item]:
        items: list[Item] = []
        since = self.config.get("since", "daily")
        for lang in self.config.get("languages", [""]):
            url = f"https://github.com/trending/{lang}?since={since}" if lang else f"https://github.com/trending?since={since}"
            try:
                r = requests.get(url, timeout=20, headers={"User-Agent": "explorer-agent"})
                r.raise_for_status()
            except Exception as e:
                log.warning("github_trending fetch failed for lang=%r since=%r: %s", lang, since, e)
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for art in soup.select("article.Box-row"):
                a = art.select_one("h2 a")
                if not a:
                    continue
                repo = a.get_text(strip=True).replace(" ", "").replace("\n", "")
                href = "https://github.com" + a["href"]
                desc_el = art.select_one("p")
                desc = desc_el.get_text(strip=True) if desc_el else ""
                stars_today_el = art.select_one("span.d-inline-block.float-sm-right")
                stars_today = stars_today_el.get_text(strip=True) if stars_today_el else ""
                lang_label = lang or "all"
                items.append(Item(
                    source=self.name,
                    source_label=f"GitHub Trending ({lang_label}, {since})",
                    id=f"trending:{repo}:{since}",
                    title=repo,
                    url=href,
                    summary=desc,
                    extra={"stars_period": stars_today, "language": lang_label},
                ))
        return items


class GitHubRising(Source):
    """Repos created in the last N days with rapid star growth."""
    name = "github_rising"

    def fetch(self) -> list[Item]:
        days = int(self.config.get("days", 7))
        min_stars = int(self.config.get("min_stars", 100))
        max_results = int(self.config.get("max_results", 50))
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        q = f"created:>{since} stars:>={min_stars}"
        items: list[Item] = []
        per_page = min(100, max_results)
        try:
            r = requests.get(
                "https://api.github.com/search/repositories",
                params={"q": q, "sort": "stars", "order": "desc", "per_page": per_page},
                headers=_gh_headers(),
                timeout=20,
            )
            r.raise_for_status()
        except Exception as e:
            log.warning("github_rising search failed (q=%r): %s", q, e)
            return items
        for repo in r.json().get("items", [])[:max_results]:
            items.append(Item(
                source=self.name,
                source_label=f"GitHub Rising (last {days}d, ≥{min_stars}★)",
                id=f"rising:{repo['full_name']}",
                title=repo["full_name"],
                url=repo["html_url"],
                summary=repo.get("description") or "",
                extra={
                    "stars": repo.get("stargazers_count"),
                    "language": repo.get("language"),
                    "created_at": repo.get("created_at"),
                },
            ))
        return items
