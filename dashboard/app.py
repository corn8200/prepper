"""Streamlit dashboard for monitoring + config CRUD."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict

import streamlit as st
import yaml

from dashboard.components.forms import (
    location_form,
    news_stack_form,
    overrides_form,
    safety_form,
    thresholds_form,
)

ROOT = Path(__file__).resolve().parents[1]

try:
    from scripts import keywords_builder  # type: ignore
    from scripts.config_models import LocationsConfig, SettingsConfig
    from scripts.validate import load_yaml
except ModuleNotFoundError:  # pragma: no cover - streamlit debugging context
    if str(ROOT) not in sys.path:
        sys.path.append(str(ROOT))
    from scripts import keywords_builder  # type: ignore
    from scripts.config_models import LocationsConfig, SettingsConfig
    from scripts.validate import load_yaml

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
LATEST_RUN = DATA_DIR / "latest_run.json"

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def read_latest_run() -> Dict:
    if not LATEST_RUN.exists():
        return {}
    return json.loads(LATEST_RUN.read_text())


def save_yaml(path: Path, payload: Dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def main() -> None:
    st.set_page_config(page_title="Prepper Alerts Dashboard", layout="wide")
    st.title("Prepper Alerts Dashboard")
    locations_payload = load_yaml(CONFIG_DIR / "locations.yaml")
    settings_payload = load_yaml(CONFIG_DIR / "settings.yaml")
    latest_run = read_latest_run()

    sidebar(settings_payload)

    tabs = st.tabs(
        [
            "Overview",
            "Locations",
            "Thresholds",
            "News Stack",
            "Overrides",
            "Decisions",
            "Logs",
        ]
    )
    with tabs[0]:
        show_overview(latest_run)
    with tabs[1]:
        show_locations(locations_payload)
    with tabs[2]:
        show_thresholds(settings_payload)
    with tabs[3]:
        show_news_stack(settings_payload)
    with tabs[4]:
        show_overrides(settings_payload, locations_payload)
    with tabs[5]:
        show_decisions(latest_run)
    with tabs[6]:
        show_logs(latest_run)


def sidebar(settings_payload: Dict) -> None:
    st.sidebar.header("Run Controls")
    dry_run_value = st.sidebar.checkbox("Dry run mode", value=settings_payload.get("testing", {}).get("dry_run", False))
    if dry_run_value != settings_payload.get("testing", {}).get("dry_run", False):
        settings_payload.setdefault("testing", {})["dry_run"] = dry_run_value
        save_settings(settings_payload)
        st.sidebar.success("Saved dry run toggle")
    if st.sidebar.button("Rebuild keywords"):
        keywords_builder.build_keywords()
        st.sidebar.success("Keywords rebuilt")
    st.sidebar.write("Secrets for email/Pushover live in GitHub Actions.")


def show_overview(latest_run: Dict) -> None:
    st.subheader("Latest run status")
    if not latest_run:
        st.info("No run data yet. Trigger the workflow once.")
        return
    st.write(f"Run ID: {latest_run.get('run_id')}")
    cols = st.columns(3)
    for idx, (location_id, summary) in enumerate(latest_run.get("locations", {}).items()):
        col = cols[idx % len(cols)]
        sources = summary.get("sources", {})
        healthy = sum(1 for _, meta in sources.items() if meta.get("ok"))
        col.metric(label=f"{location_id} sources", value=f"{healthy}/{len(sources)}")
        if summary.get("alerts"):
            col.warning(f"{len(summary['alerts'])} alerts last run")


def show_locations(locations_payload: Dict) -> None:
    st.subheader("Locations")
    locations_cfg = LocationsConfig.model_validate(locations_payload)
    st.dataframe([loc.dict() for loc in locations_cfg.locations])
    st.write("---")
    existing_ids = [loc.id for loc in locations_cfg.locations]
    selected = st.selectbox("Select location to edit", options=["(new)", *existing_ids])
    initial = None
    if selected != "(new)":
        initial = next((loc.dict() for loc in locations_cfg.locations if loc.id == selected), None)
    payload = location_form(initial=initial, key=f"location-form-{selected}")
    if payload:
        updated = [loc for loc in locations_payload["locations"] if loc["id"] != payload["id"]]
        updated.append(payload)
        locations_payload["locations"] = sorted(updated, key=lambda loc: loc["id"])
        LocationsConfig.model_validate(locations_payload)
        save_yaml(CONFIG_DIR / "locations.yaml", locations_payload)
        keywords_builder.build_keywords()
        st.success("Location saved and keywords rebuilt.")
        st.experimental_rerun()
    if selected != "(new)" and st.button("Delete location"):
        locations_payload["locations"] = [loc for loc in locations_payload["locations"] if loc["id"] != selected]
        LocationsConfig.model_validate(locations_payload)
        save_yaml(CONFIG_DIR / "locations.yaml", locations_payload)
        st.success("Location removed.")
        st.experimental_rerun()


def save_settings(payload: Dict) -> None:
    SettingsConfig.model_validate(payload)
    save_yaml(CONFIG_DIR / "settings.yaml", payload)


def show_thresholds(settings_payload: Dict) -> None:
    st.subheader("Thresholds & Safety")
    thresholds = settings_payload.get("thresholds", {})
    edited = thresholds_form(thresholds)
    if edited:
        settings_payload["thresholds"] = edited
        save_settings(settings_payload)
        st.success("Thresholds updated")
    domains = settings_payload.get("global", {}).get("safety", {}).get("allowlist_domains", [])
    updated_domains = safety_form(domains)
    if updated_domains is not None:
        settings_payload.setdefault("global", {}).setdefault("safety", {})["allowlist_domains"] = updated_domains
        save_settings(settings_payload)
        st.success("Allowlist updated")


def show_news_stack(settings_payload: Dict) -> None:
    st.subheader("News stack controls")
    news_stack = settings_payload.get("news_stack", {})
    edited = news_stack_form(news_stack)
    if edited:
        settings_payload["news_stack"] = edited
        save_settings(settings_payload)
        st.success("News stack updated")


def show_overrides(settings_payload: Dict, locations_payload: Dict) -> None:
    st.subheader("Per-location overrides")
    overrides = settings_payload.setdefault("per_location_overrides", {})
    location_ids = [loc["id"] for loc in locations_payload.get("locations", [])]
    result = overrides_form(overrides, location_ids)
    if result:
        target_id, payload = result
        overrides[target_id] = payload
        settings_payload["per_location_overrides"] = overrides
        save_settings(settings_payload)
        st.success(f"Overrides saved for {target_id}")


def show_decisions(latest_run: Dict) -> None:
    st.subheader("Decisions explorer")
    if not latest_run:
        st.info("No runs yet.")
        return
    for location_id, summary in latest_run.get("locations", {}).items():
        with st.expander(f"{location_id} alerts"):
            for alert in summary.get("alerts", []):
                st.write(f"**{alert['title']}** — priority {alert['priority']}")
                st.caption(alert.get("reason"))
                st.json(alert.get("channels", {}))


def show_logs(latest_run: Dict) -> None:
    st.subheader("Logs & raw payload")
    st.json(latest_run or {})


if __name__ == "__main__":
    main()
