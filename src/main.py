from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from . import mailer
from .dedup import Dedup
from .llm import LLM
from .sources import REGISTRY
from .sources.base import Item

ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("explorer")


_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env(value: Any) -> Any:
    """Recursively expand ${VAR} placeholders against os.environ.
    Unset vars expand to empty string — used for optional values like proxy."""
    if isinstance(value, str):
        return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(x) for x in value]
    return value


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return _expand_env(yaml.safe_load(f))


def fetch_all(cfg: dict) -> list[Item]:
    items: list[Item] = []
    for key, src_cfg in cfg.get("sources", {}).items():
        if not src_cfg.get("enabled", False):
            continue
        cls = REGISTRY.get(key)
        if not cls:
            log.warning("unknown source: %s", key)
            continue
        try:
            got = cls(src_cfg).fetch()
            log.info("fetched %d items from %s", len(got), key)
            items.extend(got)
        except Exception as e:
            log.exception("source %s failed: %s", key, e)
    return items


def trim(items: list[Item], min_score: float, max_per_source: int) -> list[Item]:
    by_src: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        if it.score >= min_score and it.matched_topics:
            by_src[it.source_label].append(it)
    out: list[Item] = []
    for src, lst in by_src.items():
        lst.sort(key=lambda x: x.score, reverse=True)
        out.extend(lst[:max_per_source])
    return out


def run(config_path: Path, dry_run: bool = False) -> int:
    load_dotenv(ROOT / ".env")
    cfg = load_config(config_path)

    items = fetch_all(cfg)
    log.info("total fetched: %d", len(items))
    if not items:
        log.info("nothing fetched, exiting")
        return 0

    storage = cfg.get("storage", {})
    dedup = Dedup(
        db_path=str(ROOT / storage.get("db_path", "data/seen.db")),
        retention_days=int(storage.get("retention_days", 30)),
    )
    new_items = dedup.filter_new(items)
    log.info("after dedup: %d new", len(new_items))
    if not new_items:
        log.info("no new items, exiting")
        return 0

    llm_cfg = cfg.get("llm", {})
    llm = LLM(llm_cfg, cfg.get("topics", []))
    llm.score(new_items)

    kept = trim(
        new_items,
        min_score=float(llm_cfg.get("min_score", 6)),
        max_per_source=int(llm_cfg.get("max_per_source", 8)),
    )
    log.info("after filter: %d kept", len(kept))
    if not kept:
        log.info("nothing relevant, exiting")
        dedup.mark_sent(new_items)  # mark as seen so we don't re-score next run
        return 0

    llm.summarize(kept)

    if dry_run:
        for it in kept:
            print(f"[{it.score:.0f}] {it.source_label} | {it.title}")
            print(f"      {it.url}")
            print(f"      topics: {it.matched_topics}")
            print(f"      {it.zh_summary}\n")
    else:
        mailer.send(kept, cfg.get("email", {}))
        log.info("email sent with %d items", len(kept))

    dedup.mark_sent(new_items)
    dedup.close()
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("-c", "--config", default=str(ROOT / "config.yaml"))
    p.add_argument("--dry-run", action="store_true", help="print to stdout instead of sending email")
    args = p.parse_args()
    sys.exit(run(Path(args.config), dry_run=args.dry_run))


if __name__ == "__main__":
    main()
