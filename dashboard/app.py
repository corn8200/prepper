"""Streamlit dashboard for monitoring + config CRUD."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
import os
import io
import zipfile
import subprocess
from typing import Dict

import streamlit as st
import yaml
import requests

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
LATEST_RUN_META = DATA_DIR / "latest_run.meta.json"

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def read_latest_run() -> Dict:
    if not LATEST_RUN.exists():
        return {}
    return json.loads(LATEST_RUN.read_text())


def save_yaml(path: Path, payload: Dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def read_latest_run_meta() -> Dict:
    if not LATEST_RUN_META.exists():
        return {}
    try:
        return json.loads(LATEST_RUN_META.read_text())
    except Exception:
        return {}


def write_latest_run_meta(meta: Dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LATEST_RUN_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception as err:  # pragma: no cover - best effort
        LOGGER.warning("Failed to write meta: %s", err)


def _detect_repo() -> tuple[str, str]:
    """Best-effort detection of owner/repo for GitHub API.

    Tries GITHUB_REPOSITORY env, then parses `git remote get-url origin`.
    """
    env_repo = os.getenv("GITHUB_REPOSITORY")
    if env_repo and "/" in env_repo:
        owner, name = env_repo.split("/", 1)
        return owner, name
    try:
        url = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=str(ROOT), text=True).strip()
        if url.startswith("git@github.com:"):
            path = url.split(":", 1)[1]
        elif url.startswith("https://github.com/"):
            path = url.split("github.com/", 1)[1]
        else:
            path = url
        if path.endswith(".git"):
            path = path[:-4]
        owner, name = path.split("/", 1)
        return owner, name
    except Exception:
        pass
    return ("", Path(ROOT).name)


def sync_latest_ci_snapshot(token: str, owner: str, repo: str, *, branch: str = "main", workflow_file: str = "prepper-alerts.yml") -> tuple[str, dict]:
    """Download the latest successful 'Prepper Alerts' run's artifact (latest_run.json).

    Returns (written_path, meta) where meta contains run_number, head_sha, updated_at, html_url.
    """
    if not owner or not repo:
        raise RuntimeError("Could not detect repository; set GITHUB_REPOSITORY or configure git remote origin.")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = f"https://api.github.com/repos/{owner}/{repo}"
    # Find latest successful run for the workflow on the branch
    runs_url = f"{base}/actions/workflows/{workflow_file}/runs?per_page=20&branch={branch}"
    rr = requests.get(runs_url, headers=headers, timeout=20)
    rr.raise_for_status()
    runs = rr.json().get("workflow_runs", [])
    chosen = None
    for run in runs:
        # Prefer completed + success
        if run.get("conclusion") == "success":
            chosen = run
            break
    if not chosen and runs:
        # Fallback to the most recent run even if not success
        chosen = runs[0]
    if not chosen:
        raise RuntimeError("No workflow runs found for Prepper Alerts.")
    run_id = chosen["id"]
    artifacts_url = f"{base}/actions/runs/{run_id}/artifacts?per_page=100"
    ar = requests.get(artifacts_url, headers=headers, timeout=20)
    ar.raise_for_status()
    artifacts = ar.json().get("artifacts", [])
    latest = next((a for a in artifacts if a.get("name") == "latest-run" and not a.get("expired")), None)
    if not latest:
        raise RuntimeError("Run has no 'latest-run' artifact. Ensure the workflow's upload-artifact step ran.")
    aid = latest["id"]
    zr = requests.get(f"{base}/actions/artifacts/{aid}/zip", headers=headers, timeout=30)
    zr.raise_for_status()
    buf = io.BytesIO(zr.content)
    with zipfile.ZipFile(buf) as zf:
        member = None
        for name in zf.namelist():
            if name.endswith("latest_run.json"):
                member = name
                break
        if not member:
            raise RuntimeError("Artifact does not contain latest_run.json")
        payload = zf.read(member)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "latest_run.json"
    out_path.write_bytes(payload)
    meta = {
        "run_id": chosen.get("id"),
        "run_number": chosen.get("run_number"),
        "head_sha": chosen.get("head_sha", "")[:7],
        "updated_at": chosen.get("updated_at") or chosen.get("created_at"),
        "html_url": chosen.get("html_url"),
    }
    return str(out_path), meta


def list_recent_runs(token: str, owner: str, repo: str, *, branch: str = "main", workflow_file: str = "prepper-alerts.yml", per_page: int = 20) -> list[dict]:
    """Return recent workflow runs (dicts with id, run_number, head_sha, status/conclusion, updated_at, html_url)."""
    if not owner or not repo:
        return []
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = f"https://api.github.com/repos/{owner}/{repo}"
    runs_url = f"{base}/actions/workflows/{workflow_file}/runs?per_page={per_page}&branch={branch}"
    rr = requests.get(runs_url, headers=headers, timeout=20)
    rr.raise_for_status()
    runs = rr.json().get("workflow_runs", [])
    out = []
    for r in runs:
        out.append({
            "id": r.get("id"),
            "run_number": r.get("run_number"),
            "head_sha": (r.get("head_sha") or "")[:7],
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "updated_at": r.get("updated_at") or r.get("created_at"),
            "html_url": r.get("html_url"),
        })
    return out


def sync_snapshot_for_run(token: str, owner: str, repo: str, run_id: int) -> tuple[str, dict]:
    """Download latest_run.json artifact for a specific run id."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = f"https://api.github.com/repos/{owner}/{repo}"
    ar = requests.get(f"{base}/actions/runs/{run_id}/artifacts?per_page=50", headers=headers, timeout=20)
    ar.raise_for_status()
    artifacts = ar.json().get("artifacts", [])
    target = next((a for a in artifacts if a.get("name") == "latest-run" and not a.get("expired")), None)
    if not target:
        # Fallback to latest repository-level artifact so the sync still works
        path, meta = _sync_repo_latest_artifact(token, owner, repo)
        meta.setdefault("note", "fallback: repo-level artifact used (selected run had none)")
        return path, meta
    aid = target["id"]
    zr = requests.get(f"{base}/actions/artifacts/{aid}/zip", headers=headers, timeout=30)
    zr.raise_for_status()
    buf = io.BytesIO(zr.content)
    with zipfile.ZipFile(buf) as zf:
        member = None
        for name in zf.namelist():
            if name.endswith("latest_run.json"):
                member = name
                break
        if not member:
            raise RuntimeError("Artifact does not contain latest_run.json")
        payload = zf.read(member)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "latest_run.json"
    out_path.write_bytes(payload)
    # Minimal meta — consumers can combine with list_recent_runs output
    return str(out_path), {"run_id": run_id}


def _sync_repo_latest_artifact(token: str, owner: str, repo: str) -> tuple[str, dict]:
    """Fallback: download latest non-expired 'latest-run' artifact across repo."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    base = f"https://api.github.com/repos/{owner}/{repo}"
    r = requests.get(f"{base}/actions/artifacts?per_page=100", headers=headers, timeout=20)
    r.raise_for_status()
    artifacts = r.json().get("artifacts", [])
    candidates = [a for a in artifacts if a.get("name") == "latest-run" and not a.get("expired")]
    if not candidates:
        raise RuntimeError("No 'latest-run' artifact found in repository.")
    artifact = sorted(candidates, key=lambda a: a.get("updated_at", ""), reverse=True)[0]
    aid = artifact["id"]
    zr = requests.get(f"{base}/actions/artifacts/{aid}/zip", headers=headers, timeout=30)
    zr.raise_for_status()
    buf = io.BytesIO(zr.content)
    with zipfile.ZipFile(buf) as zf:
        member = None
        for name in zf.namelist():
            if name.endswith("latest_run.json"):
                member = name
                break
        if not member:
            raise RuntimeError("Artifact does not contain latest_run.json")
        payload = zf.read(member)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "latest_run.json"
    out_path.write_bytes(payload)
    meta = {
        "run_number": None,
        "head_sha": "",
        "updated_at": artifact.get("updated_at"),
        "html_url": artifact.get("url"),
    }
    return str(out_path), meta


def main() -> None:
    st.set_page_config(page_title="Prepper Alerts Dashboard", layout="wide")
    st.title("Prepper Alerts Dashboard")
    locations_payload = load_yaml(CONFIG_DIR / "locations.yaml")
    settings_payload = load_yaml(CONFIG_DIR / "settings.yaml")
    latest_run = read_latest_run()
    run_meta = st.session_state.get("latest_run_meta") or read_latest_run_meta()
    if run_meta:
        st.session_state["latest_run_meta"] = run_meta

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
        show_overview(latest_run, run_meta)
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

    st.sidebar.divider()
    st.sidebar.header("CI Sync")
    token_default = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
    token = st.sidebar.text_input("GitHub token (repo:read)", value=token_default, type="password", help="Used to fetch latest_run.json artifact from Actions")
    owner, repo = _detect_repo()
    if owner and repo:
        st.sidebar.caption(f"Repo detected: {owner}/{repo}")
    # Optional run picker when a token is available
    selected_run_id = None
    if token and owner and repo:
        try:
            runs = list_recent_runs(token, owner, repo)
        except Exception as e:  # pragma: no cover - UI only
            st.sidebar.error(f"Failed to list runs: {e}")
            runs = []
        labels = ["Latest successful"]
        mapping = {labels[0]: None}
        for r in runs:
            lab = f"#{r['run_number']} {r['head_sha']} {r['conclusion'] or r['status']} {str(r['updated_at'])[:19]}"
            labels.append(lab)
            mapping[lab] = r["id"]
        choice = st.sidebar.selectbox("Choose run", options=labels, index=0)
        selected_run_id = mapping.get(choice)
    if st.sidebar.button("Sync latest CI snapshot"):
        if not token:
            st.sidebar.error("Provide a token with repo read access")
        else:
            try:
                if selected_run_id:
                    p, meta = sync_snapshot_for_run(token, owner, repo, selected_run_id)
                else:
                    p, meta = sync_latest_ci_snapshot(token, owner, repo)
                st.sidebar.success(f"Synced: {p}")
                if meta:
                    write_latest_run_meta(meta)
                    st.session_state["latest_run_meta"] = meta
                if meta:
                    st.sidebar.caption(
                        f"Run #{meta.get('run_number')} • {meta.get('head_sha')} • {meta.get('updated_at')}"
                    )
                # Quick content sanity check: ensure legacy providers are gone
                try:
                    payload = read_latest_run()
                    # gather provider keys from first location
                    providers = set()
                    for loc in (payload.get("locations") or {}).values():
                        providers.update((loc.get("sources") or {}).keys())
                    legacy = {"newsapi", "gdelt", "wiki", "airnow"} & providers
                    if legacy:
                        st.sidebar.warning(
                            "Snapshot contains legacy providers: " + ", ".join(sorted(legacy)) +
                            ". Re-run the workflow on main and sync that run."
                        )
                except Exception:
                    pass
                try:
                    st.rerun()
                except Exception:
                    # Streamlit < 1.20 used experimental_rerun
                    st.experimental_rerun()
            except Exception as e:
                st.sidebar.error(f"Sync failed: {e}")


def show_overview(latest_run: Dict, meta: Dict | None = None) -> None:
    st.subheader("Latest run status")
    if not latest_run:
        st.info("No run data yet. Trigger the workflow once.")
        return
    st.write(f"Run ID: {latest_run.get('run_id')}")
    if meta:
        caption_bits = []
        if meta.get("run_number"):
            caption_bits.append(f"Run #{meta['run_number']}")
        if meta.get("head_sha"):
            caption_bits.append(meta["head_sha"])
        if meta.get("updated_at"):
            caption_bits.append(str(meta["updated_at"]))
        if caption_bits:
            st.caption(" • ".join(caption_bits))
        if meta.get("note"):
            st.warning(meta["note"])
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
        try:
            st.rerun()
        except Exception:
            st.experimental_rerun()
    if selected != "(new)" and st.button("Delete location"):
        locations_payload["locations"] = [loc for loc in locations_payload["locations"] if loc["id"] != selected]
        LocationsConfig.model_validate(locations_payload)
        save_yaml(CONFIG_DIR / "locations.yaml", locations_payload)
        st.success("Location removed.")
        try:
            st.rerun()
        except Exception:
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
