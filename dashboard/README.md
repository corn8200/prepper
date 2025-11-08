# Dashboard

The Streamlit dashboard (`dashboard/app.py`) exposes:
- Overview of the last GitHub Actions run with per-location source health.
- Locations CRUD surface that edits `config/locations.yaml` and re-runs the keyword builder.
- Threshold tuning forms for global surge multipliers.
- Decisions explorer that renders the most recent emitted alerts + reasons.
- Logs tab displaying the raw `data/latest_run.json` payload.

## Running Locally
```bash
streamlit run dashboard/app.py
```

Use the sidebar to toggle dry-run mode, rebuild keywords, and review helpful notes. When editing config, validation is enforced via the shared Pydantic models. On save, the dashboard writes YAML back to `config/` and requests a rerun so the UI reflects the latest state.
