from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import requests

from .base import Item, Source

log = logging.getLogger(__name__)


_SECTION_LABEL = {
    "engineering": "OpenAI Engineering",
    "research": "OpenAI Research",
    "publication": "OpenAI Research",
    "release": "OpenAI Release",
    "product": "OpenAI Product",
    "safety": "OpenAI Safety",
}

# Article pages live at https://openai.com/index/<slug>/. The sitemaps also
# contain listing pages and a few non-/index/ paths — we ignore those.
_ARTICLE_RE = re.compile(r"^https://openai\.com/index/([^/]+)/?$")


class OpenAISource(Source):
    """OpenAI blog/research posts. Discovered via sitemap index — pages themselves
    are behind a Cloudflare challenge, so titles are derived from the slug."""
    name = "openai"

    def fetch(self) -> list[Item]:
        # Only engineering + research have reliable lastmod (= post publish/update time).
        # release/product/publication periodically re-stamp old posts with today's date,
        # which would let years-old content pass the days cutoff.
        sections = self.config.get("sections", ["engineering", "research"])
        days = int(self.config.get("days", 14))
        max_results = int(self.config.get("max_results", 15))
        sitemap_index_url = self.config.get(
            "sitemap_index_url", "https://openai.com/sitemap.xml"
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        headers = {"User-Agent": "explorer-agent"}

        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

        # Per-section sub-sitemap URLs from the index.
        sub_sitemaps: dict[str, str] = {}
        try:
            r = requests.get(sitemap_index_url, timeout=20, headers=headers)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except (requests.RequestException, ET.ParseError) as e:
            log.warning("openai sitemap index fetch/parse failed: %s", e)
            return []

        for sm in root.findall(f"{ns}sitemap"):
            loc = sm.find(f"{ns}loc")
            if loc is None or not loc.text:
                continue
            m = re.match(r"https://openai\.com/sitemap\.xml/([^/]+)/?$", loc.text.strip())
            if m and m.group(1) in sections:
                sub_sitemaps[m.group(1)] = loc.text.strip()

        # Walk each sub-sitemap, collect article candidates with lastmod.
        # Dedup by slug across sections (an article can appear in multiple sub-sitemaps,
        # e.g. release + product); first-seen section wins.
        seen_slugs: set[str] = set()
        candidates: list[tuple[datetime, str, str, str]] = []  # (lastmod, section, slug, url)
        for section, sm_url in sub_sitemaps.items():
            try:
                r = requests.get(sm_url, timeout=20, headers=headers)
                r.raise_for_status()
                sub_root = ET.fromstring(r.content)
            except (requests.RequestException, ET.ParseError) as e:
                log.warning("openai sub-sitemap fetch/parse failed (%s): %s", sm_url, e)
                continue

            for url_el in sub_root.findall(f"{ns}url"):
                loc_el = url_el.find(f"{ns}loc")
                lm_el = url_el.find(f"{ns}lastmod")
                if loc_el is None or lm_el is None:
                    continue
                url = (loc_el.text or "").strip()
                m = _ARTICLE_RE.match(url)
                if not m:
                    continue
                slug = m.group(1)
                if slug in seen_slugs:
                    continue
                try:
                    lastmod = datetime.fromisoformat((lm_el.text or "").replace("Z", "+00:00"))
                except ValueError:
                    continue
                if lastmod < cutoff:
                    continue
                seen_slugs.add(slug)
                # Normalize to a trailing slash so the URL is stable for dedup.
                if not url.endswith("/"):
                    url += "/"
                candidates.append((lastmod, section, slug, url))

        candidates.sort(key=lambda c: c[0], reverse=True)
        candidates = candidates[:max_results]

        items: list[Item] = []
        for lastmod, section, slug, url in candidates:
            title = _slug_to_title(slug)
            items.append(Item(
                source=self.name,
                source_label=_SECTION_LABEL.get(section, f"OpenAI {section}"),
                id=f"openai:{slug}",
                title=title,
                url=url,
                summary="",
                published=lastmod,
                extra={"section": section, "slug": slug},
            ))
        return items


_ACRONYMS = {
    "ai": "AI", "api": "API", "cli": "CLI", "cpu": "CPU", "gpu": "GPU",
    "gpt": "GPT", "ide": "IDE", "io": "IO", "llm": "LLM", "ml": "ML",
    "nlp": "NLP", "openai": "OpenAI", "os": "OS", "rl": "RL",
    "rlhf": "RLHF", "sdk": "SDK", "ui": "UI", "ux": "UX",
}
_SMALL = {"a", "an", "the", "and", "or", "for", "of", "in", "on", "to", "with", "vs"}


def _slug_to_title(slug: str) -> str:
    # Tokens that look like a model-version fragment (digits, or 2-3 chars
    # mixing digits) are hyphen-joined to the preceding token so that
    # "introducing-gpt-5-2" becomes "Introducing GPT-5-2" rather than
    # "Introducing GPT 5 2".
    words = [w for w in slug.split("-") if w]
    out: list[str] = []
    join_with_prev = False
    for i, w in enumerate(words):
        lw = w.lower()
        # Trailing "s" on an acronym (e.g. "llms") -> "LLMs".
        if lw.endswith("s") and lw[:-1] in _ACRONYMS:
            tok = _ACRONYMS[lw[:-1]] + "s"
        elif lw in _ACRONYMS:
            tok = _ACRONYMS[lw]
        elif i > 0 and lw in _SMALL:
            tok = lw
        else:
            tok = w[:1].upper() + w[1:]

        is_version_frag = w.isdigit() or (len(w) <= 3 and any(c.isdigit() for c in w))
        if join_with_prev and out and is_version_frag:
            out[-1] = f"{out[-1]}-{tok}"
        else:
            out.append(tok)

        # Continue the join chain if this token is an acronym/name that
        # commonly takes a version suffix, or itself a version fragment.
        join_with_prev = lw in {"gpt", "o", "claude", "dall", "sora", "whisper"} or is_version_frag

    return " ".join(out)
