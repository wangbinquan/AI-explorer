from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import OpenAI

from .sources.base import Item

log = logging.getLogger(__name__)


class LLM:
    def __init__(self, cfg: dict[str, Any], topics: list[dict[str, Any]]):
        self.cfg = cfg
        self.topics = topics
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY not set")
        self.client = OpenAI(api_key=api_key, base_url=cfg.get("base_url", "https://api.deepseek.com"))
        self.model = cfg.get("model", "deepseek-chat")

    # ---- relevance scoring ----

    def _score_prompt(self, items: list[Item]) -> str:
        topic_lines = "\n".join(
            f"- {t['name']}: {', '.join(t.get('keywords', []))}" for t in self.topics
        )
        item_lines = []
        for i, it in enumerate(items):
            blurb = (it.summary or "")[:300].replace("\n", " ")
            item_lines.append(f"[{i}] {it.title} :: {blurb}")
        return (
            "你是一个订阅信息过滤助手。请为下面每条信息判断与用户订阅话题的相关性。\n"
            "用户订阅话题（name: keywords）：\n"
            f"{topic_lines}\n\n"
            "信息条目（[index] 标题 :: 描述）：\n"
            + "\n".join(item_lines)
            + "\n\n"
            "请输出严格的 JSON（不要 markdown 代码块），形如：\n"
            '{"results":[{"i":0,"score":0-10的整数,"topics":["匹配到的话题name"]}, ...]}\n'
            "评分标准：10=高度相关且新颖；7-9=明确相关；4-6=略相关；0-3=无关。\n"
            "只对实质相关的条目列出 topics；无关条目 topics 留空数组。"
        )

    def score(self, items: list[Item]) -> list[Item]:
        if not items:
            return items
        # batch in chunks to keep prompt small
        BATCH = 30
        for start in range(0, len(items), BATCH):
            chunk = items[start:start + BATCH]
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": self._score_prompt(chunk)}],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                data = json.loads(resp.choices[0].message.content)
                for r in data.get("results", []):
                    idx = int(r.get("i", -1))
                    if 0 <= idx < len(chunk):
                        chunk[idx].score = float(r.get("score", 0))
                        chunk[idx].matched_topics = list(r.get("topics", []))
            except Exception as e:
                log.warning("score batch failed: %s", e)
        return items

    # ---- summarization ----

    def _summary_prompt(self, it: Item) -> str:
        blurb = (it.summary or "")[:1500]
        return (
            "用一句简洁的中文（30-60字）概括下面这条信息的核心价值，"
            "突出它做了什么、为什么值得关注。不要复述标题，不要加任何前缀。\n\n"
            f"标题：{it.title}\n"
            f"来源：{it.source_label}\n"
            f"内容：{blurb}\n"
        )

    def summarize(self, items: list[Item]) -> list[Item]:
        for it in items:
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": self._summary_prompt(it)}],
                    temperature=0.3,
                    max_tokens=200,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                it.zh_summary = resp.choices[0].message.content.strip()
            except Exception as e:
                log.warning("summarize failed for %s: %s", it.title[:50], e)
                it.zh_summary = it.summary[:120]
        return items
