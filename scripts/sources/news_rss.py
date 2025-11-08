"""Google News + curated RSS ingestion."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urlparse, parse_qs, unquote

import feedparser
import requests
import tldextract

from .base import BaseSource, SourceResult

GOOGLE_NEWS_SEARCH = "https://news.google.com/rss/search"


class NewsRSSClient(BaseSource):
    provider = "news_rss"

    def __init__(self, rss_feeds: Iterable[str], allow_domains: Iterable[str], google_queries: Iterable[str], hazard_keywords: Iterable[str] | None = None) -> None:
        self.rss_feeds = list(rss_feeds)
        self.allow_domains = {domain.lower() for domain in allow_domains}
        self.google_queries = list(google_queries)
        self.hazard_keywords = [h.lower() for h in (hazard_keywords or [])]
        self.require_hazard = (os.getenv("NEWS_REQUIRE_HAZARD", "1").strip().lower() in {"1", "true", "yes", "on"}) and bool(self.hazard_keywords)

    def fetch(self, location: Dict[str, Any], keywords: Optional[Dict[str, Any]] = None) -> SourceResult:
        items: List[Dict[str, Any]] = []
        domains: Set[str] = set()
        seen: Set[str] = set()
        start = time.perf_counter()
        for feed in self.rss_feeds:
            items.extend(self._pull_feed(feed, location["id"], domains, keywords, seen))
        for template in self.google_queries:
            query = self._format_query(template, location, keywords or {})
            url = f"{GOOGLE_NEWS_SEARCH}?hl=en-US&gl=US&ceid=US:en&q={requests.utils.quote(query)}"
            items.extend(self._pull_feed(url, location["id"], domains, keywords, seen))
        latency_ms = int((time.perf_counter() - start) * 1000)
        return SourceResult(
            provider=self.provider,
            location_id=location["id"],
            items=items,
            latency_ms=latency_ms,
        )

    def _format_query(self, template: str, location: Dict[str, Any], keywords: Dict[str, Any]) -> str:
        metadata = keywords.get("metadata", {})
        city = metadata.get("city") or location.get("label", "").split(",")[0]
        county = metadata.get("county") or city
        state = metadata.get("state") or location.get("label", "").split(",")[-1]
        state_code = metadata.get("state_code") or state[:2]
        replacements = {
            "<CITY STATE>": f"{city} {state_code}".strip(),
            "<COUNTY STATE>": f"{county} {state_code}".strip(),
        }
        query = template
        for marker, value in replacements.items():
            query = query.replace(marker, value)
        return query

    def _pull_feed(
        self,
        url: str,
        location_id: str,
        domains: Set[str],
        keywords: Optional[Dict[str, Any]],
        seen: Set[str],
    ) -> List[Dict[str, Any]]:
        parsed = feedparser.parse(url)
        results: List[Dict[str, Any]] = []
        geo_terms = [term.lower() for term in (keywords or {}).get("geo_terms", [])]
        for entry in parsed.entries:
            link = entry.get("link", "")
            dedupe_key = link or entry.get("title", "")
            if dedupe_key in seen:
                continue
            raw_domain = tldextract.extract(link).registered_domain
            domain = raw_domain
            # For Google News RSS entries, extract the real publisher URL from the 'url' query param
            if raw_domain in {"google.com", "news.google.com"} and "url=" in link:
                try:
                    q = parse_qs(urlparse(link).query)
                    candidate = q.get("url", [None])[0]
                    if candidate:
                        link = unquote(candidate)
                        domain = tldextract.extract(link).registered_domain
                except Exception:
                    domain = raw_domain
            if self.allow_domains and domain not in self.allow_domains:
                continue
            title = entry.get("title", "") or ""
            summary = entry.get("summary", "") or ""
            haystack = f"{title} {summary}".lower()
            if geo_terms and not any(token in haystack for token in geo_terms):
                continue
            if self.require_hazard and not any(hz in haystack for hz in self.hazard_keywords):
                continue
            seen.add(dedupe_key)
            results.append(
                {
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": entry.get("published"),
                    "domain": domain,
                    "location_id": location_id,
                }
            )
            domains.add(domain)
        return results
