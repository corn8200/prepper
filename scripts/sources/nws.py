"""NWS CAP alert ingestion."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import requests

from .base import BaseSource, SourceResult

API_URL = "https://api.weather.gov/alerts/active"
USER_AGENT = os.getenv("NWS_USER_AGENT", "prepper-alerts/0.1 (contact@example.com)")


class NWSClient(BaseSource):
    provider = "nws"

    def fetch(self, location: Dict[str, Any], keywords: Optional[Dict[str, Any]] = None) -> SourceResult:
        params = {
            "point": f"{location['lat']},{location['lon']}",
            "status": "actual",
            "message_type": "alert",
        }
        headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
        start = time.perf_counter()
        try:
            resp = requests.get(API_URL, params=params, headers=headers, timeout=20)
            latency_ms = int((time.perf_counter() - start) * 1000)
            resp.raise_for_status()
        except requests.RequestException as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return SourceResult(provider=self.provider, location_id=location["id"], ok=False, error=str(exc), latency_ms=latency_ms)
        data = resp.json()
        items = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            items.append(
                {
                    "id": props.get("id") or feature.get("id"),
                    "event": props.get("event"),
                    "severity": props.get("severity"),
                    "urgency": props.get("urgency"),
                    "headline": props.get("headline"),
                    "description": props.get("description"),
                    "expires": props.get("expires"),
                    "area_desc": props.get("areaDesc"),
                    "uri": props.get("@id"),
                }
            )
        return SourceResult(provider=self.provider, location_id=location["id"], items=items, latency_ms=latency_ms)
