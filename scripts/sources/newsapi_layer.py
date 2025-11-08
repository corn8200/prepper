"""NewsAPI integration used when quotas permit."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import requests
import tldextract

from .base import BaseSource, SourceResult

NEWSAPI_URL = "https://newsapi.org/v2/everything"


class NewsAPIClient(BaseSource):
    provider = "newsapi"

    def __init__(self, allow_domains: Optional[list[str]] = None) -> None:
        self.allow_domains = [domain.lower() for domain in allow_domains or []]

    def fetch(self, location: Dict[str, Any], keywords: Optional[Dict[str, Any]] = None) -> SourceResult:
        api_key = os.getenv("NEWS_API_KEY")
        if not api_key:
            return SourceResult(provider=self.provider, location_id=location["id"], ok=False, error="NEWS_API_KEY missing")
        query_terms = keywords.get("geo_terms", []) if keywords else []
        query = " OR ".join(query_terms) if query_terms else location.get("label", "")
        params = {
            "apiKey": api_key,
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 50,
        }
        start = time.perf_counter()
        resp = requests.get(NEWSAPI_URL, params=params, timeout=20)
        latency_ms = int((time.perf_counter() - start) * 1000)
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            return SourceResult(provider=self.provider, location_id=location["id"], ok=False, error=str(exc), latency_ms=latency_ms)
        data = resp.json()
        articles = []
        for article in data.get("articles", []):
            url = article.get("url", "")
            domain = (
                tldextract.extract(url).registered_domain
                or (article.get("source", {}) or {}).get("name", "")
            ).lower()
            if self.allow_domains and domain not in self.allow_domains:
                continue
            articles.append(
                {
                    "title": article.get("title"),
                    "url": url,
                    "publishedAt": article.get("publishedAt"),
                    "source": domain,
                }
            )
        return SourceResult(provider=self.provider, location_id=location["id"], items=articles, latency_ms=latency_ms)
