"""NASA EONET wildfire polling."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests

from .base import BaseSource, SourceResult

EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"


class EONETClient(BaseSource):
    provider = "eonet"

    def fetch(self, location: Dict[str, Any], keywords: Optional[Dict[str, Any]] = None) -> SourceResult:
        params = {"status": "open", "category": "wildfires"}
        start = time.perf_counter()
        try:
            resp = requests.get(EONET_URL, params=params, timeout=20)
            latency_ms = int((time.perf_counter() - start) * 1000)
            resp.raise_for_status()
        except requests.RequestException as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return SourceResult(provider=self.provider, location_id=location["id"], ok=False, error=str(exc), latency_ms=latency_ms)
        data = resp.json()
        events = []
        for event in data.get("events", []):
            events.append({"title": event.get("title"), "link": event.get("link"), "categories": event.get("categories", [])})
        return SourceResult(provider=self.provider, location_id=location["id"], items=events, latency_ms=latency_ms)
