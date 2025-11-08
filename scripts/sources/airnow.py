"""AirNow AQI polling."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import requests

from .base import BaseSource, SourceResult

AIRNOW_KEY = os.getenv("AIRNOW_API_KEY")
AIRNOW_URL = "https://www.airnowapi.org/aq/observation/latLong/current/"


class AirNowClient(BaseSource):
    provider = "airnow"

    def fetch(self, location: Dict[str, Any], keywords: Optional[Dict[str, Any]] = None) -> SourceResult:
        if not AIRNOW_KEY:
            return SourceResult(provider=self.provider, location_id=location["id"], ok=False, error="AIRNOW_API_KEY missing")
        params = {
            "format": "application/json",
            "latitude": location["lat"],
            "longitude": location["lon"],
            "distance": int(location.get("radius_km", 50)),
            "API_KEY": AIRNOW_KEY,
        }
        start = time.perf_counter()
        resp = requests.get(AIRNOW_URL, params=params, timeout=20)
        latency_ms = int((time.perf_counter() - start) * 1000)
        if resp.status_code != 200:
            return SourceResult(provider=self.provider, location_id=location["id"], ok=False, error=resp.text, latency_ms=latency_ms)
        data = resp.json()
        return SourceResult(provider=self.provider, location_id=location["id"], items=data, latency_ms=latency_ms)
