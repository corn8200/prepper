"""GDELT event corroboration."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests

from .base import BaseSource, SourceResult

GDELT_URL = "https://api.gdeltproject.org/api/v2/events/geojson"


class GDELTClient(BaseSource):
    provider = "gdelt"

    def fetch(self, location: Dict[str, Any], keywords: Optional[Dict[str, Any]] = None) -> SourceResult:
        params = {
            "query": "disaster OR protest",
            "maxrecords": 50,
            "format": "geojson",
            "startdatetime": "-1 hours",
        }
        start = time.perf_counter()
        resp = requests.get(GDELT_URL, params=params, timeout=20)
        latency_ms = int((time.perf_counter() - start) * 1000)
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            return SourceResult(provider=self.provider, location_id=location["id"], ok=False, error=str(exc), latency_ms=latency_ms)
        data = resp.json()
        items = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            items.append(
                {
                    "name": props.get("name"),
                    "themes": props.get("themes"),
                    "url": props.get("shareImage"),
                }
            )
        return SourceResult(provider=self.provider, location_id=location["id"], items=items, latency_ms=latency_ms)
