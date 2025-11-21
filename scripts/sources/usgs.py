"""USGS earthquake feed lookup."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from geopy.distance import geodesic
import requests

from .base import BaseSource, SourceResult

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


class USGSClient(BaseSource):
    provider = "usgs"

    def fetch(self, location: Dict[str, Any], keywords: Optional[Dict[str, Any]] = None) -> SourceResult:
        now = datetime.now(timezone.utc)
        params = {
            "format": "geojson",
            "latitude": location["lat"],
            "longitude": location["lon"],
            "maxradiuskm": location.get("radius_km", 250),
            "starttime": (now - timedelta(minutes=60)).isoformat(),
            "endtime": now.isoformat(),
        }
        start = time.perf_counter()
        try:
            resp = requests.get(USGS_URL, params=params, timeout=20)
            latency_ms = int((time.perf_counter() - start) * 1000)
            resp.raise_for_status()
        except requests.RequestException as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return SourceResult(provider=self.provider, location_id=location["id"], ok=False, error=str(exc), latency_ms=latency_ms)
        data = resp.json()
        items = []
        for feature in data.get("features", []):
            geometry = feature.get("geometry") or {}
            coords = geometry.get("coordinates") or []
            if len(coords) < 2:
                continue
            quake_lat, quake_lon = coords[1], coords[0]
            distance_km = geodesic((location["lat"], location["lon"]), (quake_lat, quake_lon)).km
            if distance_km > location.get("radius_km", 250):
                continue
            props = feature.get("properties", {})
            items.append(
                {
                    "id": feature.get("id"),
                    "mag": props.get("mag"),
                    "place": props.get("place"),
                    "time": props.get("time"),
                    "url": props.get("url"),
                    "distance_km": round(distance_km, 1),
                }
            )
        return SourceResult(provider=self.provider, location_id=location["id"], items=items, latency_ms=latency_ms)
