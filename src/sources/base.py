from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Item:
    source: str            # e.g. "github_trending"
    source_label: str      # human-friendly, e.g. "GitHub Trending (Python, daily)"
    id: str                # stable unique id within source (used for dedup)
    title: str
    url: str
    summary: str = ""      # raw description from source
    extra: dict[str, Any] = field(default_factory=dict)
    published: datetime | None = None

    # filled later by pipeline
    score: float = 0.0
    matched_topics: list[str] = field(default_factory=list)
    zh_summary: str = ""

    @property
    def fingerprint(self) -> str:
        return hashlib.sha1(f"{self.source}|{self.id}".encode()).hexdigest()


class Source:
    name: str = ""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fetch(self) -> list[Item]:
        raise NotImplementedError
