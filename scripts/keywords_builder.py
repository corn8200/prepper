"""Builds derived keyword lists per location using FCC + heuristics."""

from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Dict, List

import requests
import yaml

from .config_models import KeywordsConfig, LocationsConfig
from .validate import load_yaml

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
FCC_ENDPOINT = "https://geo.fcc.gov/api/census/area"


def normalize_ascii(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def slugify(value: str) -> str:
    safe = normalize_ascii(value).lower().replace("'", "").replace(" ", "-")
    return "".join(char for char in safe if char.isalnum() or char == "-")


def fetch_geo(lat: float, lon: float) -> Dict[str, str]:
    params = {"lat": lat, "lon": lon, "format": "json"}
    try:
        resp = requests.get(FCC_ENDPOINT, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.warning("FCC lookup failed for %s,%s: %s", lat, lon, exc)
        return {}
    payload = resp.json()
    results = payload.get("results") or []
    if not results:
        return {}
    result = results[0]
    return {
        "county": result.get("county_name", "").strip(),
        "county_fips": result.get("county_fips", "").strip(),
        "state": result.get("state_name", "").strip(),
        "state_code": result.get("state_code", "").strip(),
    }


def build_keywords() -> None:
    locations_raw = load_yaml(CONFIG_DIR / "locations.yaml")
    locations_cfg = LocationsConfig.model_validate(locations_raw)
    keyword_map: Dict[str, Dict[str, List[str]]] = {}
    union_terms: Dict[str, List[str] | Dict[str, str]] = {"geo_terms": [], "wiki_pages": [], "roads": [], "metadata": {}}
    for loc in locations_cfg.locations:
        geo = fetch_geo(loc.lat, loc.lon)
        city_tokens = [loc.label.split(",")[0].strip()]
        county = geo.get("county") or f"{loc.label.split(',')[0]} County"
        state_full = geo.get("state") or loc.label.split(",")[-1].strip()
        state_code = geo.get("state_code") or state_full[:2].upper()
        metadata = {
            "city": city_tokens[0],
            "county": county,
            "state": state_full,
            "state_code": state_code,
        }
        tokens = {
            "geo_terms": sorted({
                normalize_ascii(value)
                for value in [*city_tokens, county, f"{county} County", state_full, state_code]
                if value
            }),
            "wiki_pages": sorted({
                slugify(city_tokens[0]),
                slugify(f"{county} County, {state_full}") if county and state_full else "",
                *(slugify(road) for road in loc.roads),
            } - {""}),
            "roads": sorted({normalize_ascii(road) for road in loc.roads}),
            "metadata": metadata,
        }
        keyword_map[loc.id] = tokens
        for key, values in tokens.items():
            if key == "metadata":
                continue
            union_terms[key].extend(values)  # type: ignore[arg-type]
    collapsed_union = {k: sorted({*v}) for k, v in union_terms.items() if k != "metadata"}
    keywords = {"locations": keyword_map, "union": {**collapsed_union, "metadata": {}}}
    KeywordsConfig.model_validate(keywords)  # validation guard
    CONFIG_DIR.joinpath("keywords.yaml").write_text(
        yaml.safe_dump(keywords, sort_keys=False, allow_unicode=False), encoding="utf-8"
    )
    LOGGER.info("Wrote %s", CONFIG_DIR / "keywords.yaml")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_keywords()
