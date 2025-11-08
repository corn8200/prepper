"""Lightweight article text extraction for LLM triage.

Uses requests + readability-lxml + BeautifulSoup to fetch and extract the
main content text from article URLs. Intended for small batches and short
timeouts; respects an allowlist of domains from settings.
"""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from readability import Document


DEFAULT_UA = os.getenv(
    "NWS_USER_AGENT",
    "prepper-alerts/0.1 (+github.com/corn8200/prepper)",
)


@dataclass
class Article:
    url: str
    title: str
    text: str
    domain: str


def _clean_text(text: str) -> str:
    # Strip scripts/styles, decode entities, collapse whitespace
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_article_text(url: str, *, timeout: int = 8, user_agent: str = DEFAULT_UA) -> str:
    """Fetch URL and return best-effort main text or empty string on failure."""
    try:
        resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    except Exception:
        return ""
    if not resp.ok or not resp.content:
        return ""
    try:
        doc = Document(resp.text)
        html_body = doc.summary(html_partial=True)
        soup = BeautifulSoup(html_body, "lxml")
        # Remove likely nav/aside leftovers
        for tag in soup(["script", "style", "noscript", "header", "footer", "aside", "form"]):
            tag.decompose()
        text = soup.get_text(" ")
        return _clean_text(text)
    except Exception:
        try:
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            return _clean_text(soup.get_text(" "))
        except Exception:
            return ""


def enrich_items_with_fulltext(items, *, allow_domains: Iterable[str], max_items: int, max_chars: int = 1000) -> list[dict]:
    """Fetch full text for up to `max_items` items, attach as `content` key.

    Respects `allow_domains` (no fetch if domain not allowed). Truncates text to
    `max_chars` to control LLM cost.
    """
    allowed = {d.lower() for d in allow_domains}
    out = []
    for item in items[: max(1, max_items)]:
        domain = (item.get("domain") or "").lower()
        if allowed and domain and domain not in allowed:
            out.append(item)
            continue
        url = item.get("link") or item.get("url")
        if not url:
            out.append(item)
            continue
        body = fetch_article_text(url)
        if body:
            item = dict(item)
            item["content"] = body[: max_chars]
        out.append(item)
    return out
