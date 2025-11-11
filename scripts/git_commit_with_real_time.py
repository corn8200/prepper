#!/usr/bin/env python3
"""Run a git subcommand with author/committer dates based on real UTC."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import typing as t
import urllib.error
import urllib.request

_TIME_SOURCES: tuple[tuple[str, t.Callable[[t.Mapping[str, t.Any]], str | None]], ...] = (
    (
        "https://worldtimeapi.org/api/timezone/Etc/UTC",
        lambda payload: t.cast(str | None, payload.get("utc_datetime")),
    ),
    (
        "https://timeapi.io/api/Time/current/zone?timeZone=UTC",
        lambda payload: t.cast(str | None, payload.get("dateTime")),
    ),
)


def _parse_datetime(value: str) -> dt.datetime:
    value = value.strip()
    iso_formats = (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    )
    for fmt in iso_formats:
        try:
            parsed = dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    try:
        epoch_seconds = float(value)
    except ValueError as exc:  # pragma: no cover - defensive path
        raise ValueError(f"Unsupported datetime value: {value!r}") from exc
    return dt.datetime.fromtimestamp(epoch_seconds, tz=dt.timezone.utc)


def _resolve_from_sources() -> dt.datetime:
    last_error: Exception | None = None
    headers = {"User-Agent": "prepper/git-time-sync"}
    for url, pick_key in _TIME_SOURCES:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            continue
        raw_value = pick_key(payload)
        if not raw_value:
            continue
        try:
            return _parse_datetime(raw_value)
        except ValueError as exc:
            last_error = exc
            continue
    raise RuntimeError("Failed to resolve a trusted UTC timestamp") from last_error


def _resolve_datetime(explicit: str | None) -> dt.datetime:
    if explicit:
        return _parse_datetime(explicit)
    env_value = os.getenv("REAL_GIT_COMMIT_TIME")
    if env_value:
        return _parse_datetime(env_value)
    return _resolve_from_sources()


def _format_git_date(timestamp: dt.datetime) -> str:
    return timestamp.strftime("%Y-%m-%dT%H:%M:%S%z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run git with corrected commit timestamps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/git_commit_with_real_time.py commit -am 'Fix bug'\n"
            "  python scripts/git_commit_with_real_time.py --datetime 2024-09-12T12:30:00Z commit\n"
            "  REAL_GIT_COMMIT_TIME=1726109400 python scripts/git_commit_with_real_time.py commit --amend"
        ),
    )
    parser.add_argument(
        "--datetime",
        dest="override",
        help="Override the timestamp (ISO-8601 or unix epoch seconds)",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the resolved timestamp and exit",
    )
    parser.add_argument(
        "git_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to git (prefix with '--' if needed)",
    )

    ns = parser.parse_args(argv)
    git_args = ns.git_args or []
    if git_args and git_args[0] == "--":
        git_args = git_args[1:]

    timestamp = _resolve_datetime(ns.override)
    formatted = _format_git_date(timestamp)

    if ns.print_only:
        print(formatted)
        return 0

    if not git_args:
        parser.error("No git arguments provided. Example: commit -am 'Fix'")

    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = formatted
    env["GIT_COMMITTER_DATE"] = formatted

    result = subprocess.run(["git", *git_args], env=env)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
