"""Reusable Streamlit form helpers."""

from __future__ import annotations

from typing import Dict, Optional

import streamlit as st


def location_form(initial: Optional[Dict] = None, key: str = "location_form") -> Optional[Dict]:
    initial = initial or {}
    with st.form(key):
        st.write("Add or edit a location.")
        location_id = st.text_input("ID", value=initial.get("id", ""))
        label = st.text_input("Label", value=initial.get("label", ""))
        role = st.text_input("Role", value=initial.get("role", ""))
        lat = st.number_input("Latitude", value=float(initial.get("lat", 0.0)))
        lon = st.number_input("Longitude", value=float(initial.get("lon", 0.0)))
        radius = st.number_input("Radius (km)", value=float(initial.get("radius_km", 50.0)), min_value=1.0, max_value=500.0)
        roads = st.text_input("Roads (comma-separated)", value=",".join(initial.get("roads", [])))
        submitted = st.form_submit_button("Save location")
    if submitted and location_id and label:
        return {
            "id": location_id,
            "label": label,
            "role": role or "",
            "lat": float(lat),
            "lon": float(lon),
            "radius_km": float(radius),
            "roads": [road.strip() for road in roads.split(",") if road.strip()],
        }
    return None


def thresholds_form(initial: Dict, key: str = "thresholds_form") -> Optional[Dict]:
    with st.form(key):
        st.write("Tune global surge thresholds.")
        news_spike = st.number_input("News spike factor", value=float(initial.get("news_spike_factor", 3.0)), min_value=1.0)
        news_mentions = st.number_input("News min mentions", value=int(initial.get("news_min_mentions", 3)), min_value=1)
        wiki_spike = st.number_input("Wiki spike factor", value=float(initial.get("wiki_spike_factor", 4.0)), min_value=1.0)
        submitted = st.form_submit_button("Save thresholds")
    if submitted:
        return {
            **initial,
            "news_spike_factor": float(news_spike),
            "news_min_mentions": int(news_mentions),
            "wiki_spike_factor": float(wiki_spike),
        }
    return None


def safety_form(domains: list[str], key: str = "safety_form") -> Optional[list[str]]:
    with st.form(key):
        st.write("Edit allow-listed domains for unofficial sources.")
        text_value = "\n".join(domains)
        buffer = st.text_area("Domains (one per line)", value=text_value, height=150)
        submitted = st.form_submit_button("Save domains")
    if submitted:
        cleaned = [line.strip() for line in buffer.splitlines() if line.strip()]
        return cleaned
    return None


def news_stack_form(initial: Dict, key: str = "news_stack_form") -> Optional[Dict]:
    with st.form(key):
        st.write("Control RSS, Google News, and NewsAPI behavior.")
        rss_value = "\n".join(initial.get("rss_sources", []))
        rss_sources = st.text_area("RSS sources", value=rss_value, height=160)
        google_value = "\n".join(initial.get("google_news_queries_per_location", []))
        google_queries = st.text_area("Google News queries", value=google_value, height=160)
        cooldown = st.number_input(
            "NewsAPI cooldown (minutes)",
            value=int(initial.get("quotas", {}).get("newsapi_cooldown_minutes", 30)),
            min_value=5,
            step=5,
        )
        burst = st.number_input(
            "NewsAPI burst window (minutes)",
            value=int(initial.get("quotas", {}).get("newsapi_burst_minutes", 60)),
            min_value=15,
            step=15,
        )
        modes = ["auto", "always", "off"]
        current_mode = initial.get("mode", "auto")
        if current_mode not in modes:
            current_mode = "auto"
        mode = st.selectbox("NewsAPI mode", options=modes, index=modes.index(current_mode))
        require_domains = st.number_input(
            "Distinct domains required for surge",
            value=int(initial.get("surge", {}).get("require_distinct_domains", 2)),
            min_value=1,
            max_value=5,
        )
        submitted = st.form_submit_button("Save news stack")
    if submitted:
        return {
            "rss_sources": [line.strip() for line in rss_sources.splitlines() if line.strip()],
            "google_news_queries_per_location": [line.strip() for line in google_queries.splitlines() if line.strip()],
            "quotas": {
                "newsapi_cooldown_minutes": int(cooldown),
                "newsapi_burst_minutes": int(burst),
            },
            "surge": {"require_distinct_domains": int(require_domains)},
            "mode": mode,
        }
    return None


def overrides_form(initial: Dict[str, Dict[str, float]], location_ids: list[str], key: str = "overrides_form"):
    if not location_ids:
        st.info("Add locations before configuring overrides.")
        return None
    selected = st.selectbox("Select location", options=location_ids, key=f"{key}-select")
    defaults = initial.get(selected, {})
    with st.form(key):
        normal = st.number_input("Quake min magnitude (P1)", value=float(defaults.get("quake_min_mag_normal", 4.0)), min_value=0.0, step=0.1)
        emergency = st.number_input("Quake min magnitude (P2)", value=float(defaults.get("quake_min_mag_emergency", 5.5)), min_value=0.0, step=0.1)
        submitted = st.form_submit_button("Save override")
    if submitted:
        return selected, {
            "quake_min_mag_normal": float(normal),
            "quake_min_mag_emergency": float(emergency),
        }
    return None
