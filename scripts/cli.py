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


if __name__ == "__main__":
    cli()
