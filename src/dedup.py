from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .sources.base import Item


class Dedup:
    def __init__(self, db_path: str, retention_days: int = 30):
        self.db_path = db_path
        self.retention_days = retention_days
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            "fingerprint TEXT PRIMARY KEY, source TEXT, title TEXT, url TEXT, sent_at TEXT)"
        )
        self.conn.commit()
        self._purge()

    def _purge(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        self.conn.execute("DELETE FROM seen WHERE sent_at < ?", (cutoff,))
        self.conn.commit()

    def filter_new(self, items: Iterable[Item]) -> list[Item]:
        cur = self.conn.cursor()
        out: list[Item] = []
        for it in items:
            cur.execute("SELECT 1 FROM seen WHERE fingerprint=?", (it.fingerprint,))
            if cur.fetchone() is None:
                out.append(it)
        return out

    def mark_sent(self, items: Iterable[Item]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        rows = [(it.fingerprint, it.source, it.title, it.url, now) for it in items]
        self.conn.executemany(
            "INSERT OR IGNORE INTO seen(fingerprint, source, title, url, sent_at) VALUES(?,?,?,?,?)",
            rows,
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
