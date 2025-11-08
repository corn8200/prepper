"""Developer utilities for running workflows locally."""

from __future__ import annotations

import logging
from pathlib import Path
import sys

import click

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

try:
    from . import keywords_builder, prepper_alerts
except ImportError:  # pragma: no cover
    from scripts import keywords_builder, prepper_alerts

logging.basicConfig(level=logging.INFO)


@click.group()
def cli() -> None:
    """Prepper alerts developer CLI."""


@cli.command("rebuild-keywords")
def rebuild_keywords() -> None:
    """Trigger keyword rebuild based on config/locations.yaml."""
    keywords_builder.build_keywords()


@cli.command("run")
@click.option("--dry-run", is_flag=True, help="Do not send notifications; still persists run state.")
def run(dry_run: bool) -> None:
    """Execute the orchestrator once (mirrors CI workflow)."""
    prepper_alerts.run_once(dry_run=dry_run)


@cli.command("dashboard")
@click.option("--port", type=int, default=8501, help="Port for Streamlit app")
def dashboard(port: int) -> None:
    """Launch the Streamlit dashboard locally."""
    import subprocess
    import sys
    from pathlib import Path
    app = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app), "--server.port", str(port)]
    subprocess.run(cmd, check=True)

@cli.command("send-test")
@click.option("--priority", type=click.IntRange(1, 2), default=1, help="Pushover/Email priority (1=normal,2=emergency)")
@click.option("--title", default="[TEST] Prepper Alerts end-to-end", help="Alert title")
@click.option("--body", default="This is a manual test of the full sending path.", help="Alert body")
@click.option("--url", default="https://github.com/corn8200/prepper", help="Optional URL")
@click.option("--sound", default=None, help="Override Pushover sound (e.g., siren, spacealarm)")
@click.option("--device", default=None, help="Target a specific Pushover device name")
@click.option("--retry", type=int, default=None, help="Emergency retry seconds (priority=2)")
@click.option("--expire", type=int, default=None, help="Emergency expire seconds (priority=2)")
def send_test(priority: int, title: str, body: str, url: str, sound: str | None, device: str | None, retry: int | None, expire: int | None) -> None:
    """Send a one-off test alert via configured outputs."""
    from .alerting import AlertDispatcher, AlertPayload  # lazy import for speed
    from .validate import load_yaml
    from .config_models import SettingsConfig
    ROOT = Path(__file__).resolve().parents[1]
    settings = SettingsConfig.model_validate(load_yaml(ROOT / "config" / "settings.yaml"))
    outputs = settings.global_.outputs.model_dump()
    if retry is not None:
        outputs["emergency_retry_sec"] = retry
    if expire is not None:
        outputs["emergency_expire_sec"] = expire
    dispatcher = AlertDispatcher(config={"outputs": outputs}, dry_run=False)
    payload = AlertPayload(title=title, body=body, priority=priority, url=url, location_id="test", channels=("email", "pushover"))
    # Allow overriding sound/device via env for the downstream client
    import os
    if sound:
        os.environ["PUSHOVER_SOUND"] = sound
        os.environ["PUSHOVER_PRIORITY2_SOUND"] = sound
    if device:
        os.environ["PUSHOVER_DEVICE"] = device
    result = dispatcher.dispatch(payload)
    click.echo(f"Sent test alert: {result}")


@cli.command("debug-news")
@click.option("--location", required=True, help="Location id to test (e.g., home, work)")
@click.option("--limit", type=int, default=10, help="Max items to print")
def debug_news(location: str, limit: int) -> None:
    """Fetch news_rss for a specific location and print sample items.

    Useful for verifying that RSS + Google News queries are returning results
    before LLM filtering.
    """
    from .validate import load_yaml
    from .config_models import KeywordsConfig, LocationsConfig, SettingsConfig
    from .sources.news_rss import NewsRSSClient
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    locs = LocationsConfig.model_validate(load_yaml(root / "config" / "locations.yaml"))
    settings = SettingsConfig.model_validate(load_yaml(root / "config" / "settings.yaml"))
    keywords = KeywordsConfig.model_validate(load_yaml(root / "config" / "keywords.yaml"))
    loc = next((loc_item for loc_item in locs.locations if loc_item.id == location), None)
    if not loc:
        raise SystemExit(f"Unknown location id: {location}")
    client = NewsRSSClient(
        settings.news_stack.rss_sources,
        settings.global_.safety.allowlist_domains,
        settings.news_stack.google_news_queries_per_location,
        getattr(settings.news_stack, "hazard_keywords", []),
        getattr(settings.news_stack, "require_hazard", True),
    )
    loc_payload = loc.model_dump()
    loc_payload["label"] = loc.label
    kw_entry = keywords.locations.get(location)
    kw = kw_entry.model_dump() if kw_entry else {}
    result = client.fetch(loc_payload, kw)
    print(f"news_rss ok={result.ok} count={len(result.items)} latency_ms={result.latency_ms}")
    for item in result.items[:limit]:
        print("-", item.get("domain"), "|", (item.get("title") or "")[:120])
    if not result.items:
        print("No items found. Consider disabling NEWS_REQUIRE_HAZARD=1 during testing or expanding queries.")

if __name__ == "__main__":
    cli()
