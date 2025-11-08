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
    import subprocess, sys
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

if __name__ == "__main__":
    cli()
