"""Wikipedia attention signals."""

from __future__ import annotations

import datetime as dt
import time
from typing import Any, Dict, Optional

import requests

from .base import BaseSource, SourceResult

WIKI_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/{access}/{agent}/{article}/{granularity}/{start}/{end}"


class WikiClient(BaseSource):
    provider = "wiki"

    def fetch(self, location: Dict[str, Any], keywords: Optional[Dict[str, Any]] = None) -> SourceResult:
        keywords = keywords or {}
        pages = keywords.get("wiki_pages", [])
        if not pages:
            return SourceResult(provider=self.provider, location_id=location["id"], items=[])
        start = time.perf_counter()
        end_date = dt.datetime.utcnow().date()
        start_date = end_date - dt.timedelta(days=7)
        totals = []
        for page in pages:
            url = WIKI_URL.format(
                project="en.wikipedia.org",
                access="all-access",
                agent="user",
                article=page,
                granularity="daily",
                start=start_date.strftime("%Y%m%d"),
                end=end_date.strftime("%Y%m%d"),
            )
            resp = requests.get(url, timeout=20)
            if resp.status_code != 200:
                continue
            data = resp.json()
            totals.append({
                "page": page,
                "views": [item.get("views", 0) for item in data.get("items", [])],
            })
        latency_ms = int((time.perf_counter() - start) * 1000)
        return SourceResult(provider=self.provider, location_id=location["id"], items=totals, latency_ms=latency_ms)
