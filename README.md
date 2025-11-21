# Prepper Alerts

This repo is a personal command center for “is anything going sideways near my family?”

Every ten minutes it wakes up, pulls official alerts for your home/work, scrapes your trusted news outlets, lets ChatGPT read the articles for you, and only pings you when a story is both local **and** urgent. When something matters you get an email plus a Pushover notification (including the loud, repeating “break glass” alert on your phone).

You don’t have to be a developer—think of it as a tailored warning siren you can run locally, in GitHub, or on Google Cloud with a point-and-click dashboard.

## What You Get

| Need | What the system does |
| --- | --- |
| Weather + quake warnings | Talks to NWS and USGS directly, respects their severity levels, and only wakes you up when it’s serious. |
| Hyperlocal intelligence | Pulls RSS + Google News for your exact cities, counties, and highways. Full text is fed to OpenAI, which classifies relevance/severity. |
| Zero spam | Multi-source confirmation, dedupe, and per-location cooldowns keep chatter out of your inbox. |
| Instant delivery | Email and Pushover (including emergency priority with custom sounds). |
| Command dashboard | Launch `python -m scripts.cli dashboard` to edit locations, allowlist domains, dry-run, rebuild keywords, and sync the latest CI run—all without touching a terminal. |

## How the Pipeline Works

1. **Gather** — Official feeds (NWS, USGS, EONET) + curated RSS + live Google News feeds per location. RSS hits are deduped and only from allow-listed publishers.
2. **Enrich** — Every news link is fetched, cleaned, and summarized. Google News redirects are resolved to the real publisher so allowlists work.
3. **Judge** — ChatGPT (via OpenAI API) reads each article and assigns: relevant? category? severity 1–3? It only passes items that mention your city/county/roads.
4. **Fuse** — Surges (news volume), hysterias (multiple sources confirming), and official warnings join forces. This keeps false positives low.
5. **Alert** — When thresholds are met, an alert is written to `data/latest_run.json`, logged to SQLite, and sent over email + Pushover. Emergency alerts repeat until acknowledged.
6. **Review** — The dashboard can sync the latest cloud run so you see exactly who said what, when, and why it did (or didn’t) notify you.

## What You Need

| Item | Why |
| --- | --- |
| GitHub repo with Actions enabled | Runs the 10‑minute job for you while you sleep. |
| Secrets in **Settings → Actions → Secrets and variables → Actions** | `OPENAI_API_KEY`, `NWS_USER_AGENT`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ALERT_EMAIL_TO`, `PUSHOVER_USER_KEY`, `PUSHOVER_APP_TOKEN`. Optional: `GH_BOT_NAME`, `GH_BOT_EMAIL`, `GH_PUSH_TOKEN`. |
| Pushover + Gmail app password | Outbound notifications. You can swap other providers if you prefer. |
| Location data | `config/locations.yaml` already includes Harper’s Ferry and Frederick; add your own IDs/lat/lon/roads. |

## Quick Start (Local)

> Tip: use Python 3.11/3.12 so Streamlit/pyarrow wheels install cleanly. On 3.13+, the core CLI still works but the dashboard dependencies are skipped.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional knobs – mirrors the defaults in CI
export LLM_CLASSIFY_NEWS=1
export OPENAI_API_KEY=sk-...
export LLM_MAX_ITEMS=10
export LLM_MAX_CHARS=1000
export LLM_EMIT_ALERTS=1
export LLM_MIN_SEVERITY=3
export LLM_CONFIRM_MIN_SEVERITY=2
export LLM_ALLOW_CATEGORIES="evacuation,hazmat,lockdown,outage,disaster,severe_weather,public_health,crime"
export LLM_EMERGENCY_CATEGORIES="evacuation,hazmat,lockdown,outage,disaster,public_health,crime"
export NEWS_REQUIRE_HAZARD=0        # let the LLM decide what’s relevant
export PUSHOVER_PRIORITY2_SOUND=siren
export PUSHOVER_EMERGENCY_RETRY=30
export PUSHOVER_EMERGENCY_EXPIRE=300

# Build derived keywords + run a dry check
python -m scripts.cli rebuild-keywords
python -m scripts.prepper_alerts --dry-run

# Launch the dashboard
PYTHONPATH=. python -m scripts.cli dashboard --port 8501
# visit http://localhost:8501
```

Useful tooling:

```bash
# See what RSS / Google News is returning for a location
PYTHONPATH=. python -m scripts.cli debug-news --location home --limit 10

# Fire a real, end-to-end alert (no code changes needed)
PYTHONPATH=. python -m scripts.cli send-test --priority 2 --sound siren --retry 30 --expire 300
```

## GitHub Actions Runbook

The workflow lives at `.github/workflows/prepper-alerts.yml` and runs every 10 minutes. It now fails fast if any required secret is missing, so check the **Actions** tab if you stop getting alerts. The job sequence is:

1. Validate secrets → fail loudly if any are empty.
2. Checkout + install deps.
3. Validate configs + rebuild keywords.
4. Run the orchestrator (non dry-run) → writes `data/latest_run.json` and `data/latest_run.meta.json`.
5. Always upload the snapshot artifact (even if no alerts were generated).
6. Optionally commit artifacts back if `GH_PUSH_TOKEN` is provided.

Use the dashboard “CI Sync” panel (with a Personal Access Token) to pull the latest artifact. You can pick a specific run from the dropdown and it shows the run number, commit SHA, and timestamp so you know what dataset you’re browsing.

## Keeping It Tuned

- **Add news sources:** `config/settings.yaml` already ships with DC/Baltimore/WV outlets. Add more allowlist domains + RSS feeds for your county; the more local, the better.
- **Change thresholds:** use the dashboard “Thresholds” tab or edit `config/settings.yaml` to adjust surge factors, quake magnitudes, etc.
- **Disable hazard prefilter:** Set `NEWS_REQUIRE_HAZARD=0` (default in CI) so the LLM sees all stories and decides what’s relevant. Use `1` only if you need ultra conservative intake.
- **Test end-to-end:** `PYTHONPATH=. python -m scripts.cli send-test --priority 2` sends the loud Pushover alert and an email so you can verify device settings.

## Deploying the Dashboard (Optional)

Want your family to see the dashboard without installing Python? Deploy the Streamlit app to Google Cloud Run with Workspace SSO. Follow the numbered steps below (copied from the original instructions) once you’re happy with your config.

1. **Prereqs:** Install the [gcloud SDK](https://cloud.google.com/sdk/docs/install), have a Workspace domain + subdomain (e.g., `alerts.yourdomain.com`), and note the entry point `dashboard/app.py`.
2. **Create an image:** `gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE`
3. **Deploy:** `gcloud run deploy ... --allow-unauthenticated=false` etc.
4. **Enable IAP & custom domain:** follow the commands in the original Cloud Run section.

This gives you a private dashboard on the internet that only Workspace users can access. (Actions continues to run the data collection in the background.)

## Troubleshooting Checklist

- **Actions says “missing secret”:** set the missing key under repo Settings → Actions → Secrets.
- **Dashboard shows old providers (newsapi/gdelt/wiki):** click “Sync latest CI snapshot” and pick the most recent successful run. If the sidebar warns about legacy providers, you’re still viewing an old artifact.
- **No “home” news:** expand the allowlist with more Jefferson County/Winchester/Loudoun sources or temporarily set `NEWS_REQUIRE_HAZARD=0` while tuning.
- **NWS error 403:** your `NWS_USER_AGENT` is blank or not descriptive. Use something like `prepper-alerts/1.0 (you@example.com)`.
- **Pushover emergency didn’t repeat:** set `PUSHOVER_EMERGENCY_RETRY/EXPIRE` in env/Actions and make sure Critical Alerts are allowed on your iPhone.

## Workspace-SSO Streamlit Deployment (Cloud Run + IAP)
Turn the Streamlit dashboard into a Google Workspace–protected site:

1. **Prereqs:** Install the [gcloud SDK](https://cloud.google.com/sdk/docs/install), ensure you have a Google Workspace domain plus a subdomain (e.g., `app.yourdomain.com`), and note that the entry point is `dashboard/app.py`.
2. **Create the container image:** A `Dockerfile` (already in the repo) builds the Streamlit app for Cloud Run.
3. **Set variables (adjust values to your org):**
   ```bash
   PROJECT_ID="YOUR_GCP_PROJECT_ID"
   REGION="us-east1"
   SERVICE="preppers-dashboard"
   DOMAIN="app.yourdomain.com"
   GROUP_EMAIL="dash-viewers@yourdomain.com"
   SUPPORT_EMAIL="you@yourdomain.com"
   ```
4. **Authenticate + pick project/region:**
   ```bash
   gcloud auth login
   gcloud config set project "$PROJECT_ID"
   gcloud config set run/region "$REGION"
   ```
5. **Enable services (idempotent):**
   ```bash
   gcloud services enable run.googleapis.com iam.googleapis.com iap.googleapis.com \
     secretmanager.googleapis.com cloudbuild.googleapis.com
   ```
6. **Build + deploy a private Cloud Run service:**
   ```bash
   gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE
   gcloud run deploy "$SERVICE" \
     --image gcr.io/$PROJECT_ID/$SERVICE \
     --allow-unauthenticated=false \
     --region "$REGION" \
     --memory 1Gi
   ```
7. **Configure Identity-Aware Proxy (IAP) and Workspace auth:**
   ```bash
   gcloud iap oauth-brands create \
     --application_title="Preppers Dashboard" \
     --support_email="$SUPPORT_EMAIL" || true
   BRAND="$(gcloud iap oauth-brands list --format='value(name)')"
   gcloud iap oauth-clients create "$BRAND" --display_name="Preppers IAP Client" || true

   gcloud iap web enable --resource-type=compute
   gcloud iap web add-iam-policy-binding \
     --member="group:$GROUP_EMAIL" \
     --role="roles/iap.httpsResourceAccessor"
   ```
8. **Map your custom domain (creates DNS records to add at your registrar):**
   ```bash
   gcloud run domain-mappings create \
     --service "$SERVICE" \
     --domain "$DOMAIN" \
     --region "$REGION" || true
   ```
9. **Update DNS:** Add the records printed by the previous step; once propagated, only members of `$GROUP_EMAIL` can reach `https://$DOMAIN` via Workspace SSO. 

## Getting Started
1. Create a GitHub repository named `preppers-alerts` (MIT) and push this project.
2. Configure secrets under **Settings → Actions → Secrets and variables → Actions** (required for CI to run successfully):
   - `OPENAI_API_KEY`
   - `NWS_USER_AGENT`
   - `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ALERT_EMAIL_TO`
   - `PUSHOVER_USER_KEY`, `PUSHOVER_APP_TOKEN`
   - Optional: `GH_BOT_NAME`, `GH_BOT_EMAIL`, `GH_PUSH_TOKEN`
3. Install Python 3.11 locally, create a virtual environment, and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Run the orchestration workflow locally (dry-run first):
   ```bash
   # Optional: enable LLM-based filtering of RSS items
   export LLM_CLASSIFY_NEWS=1
   export OPENAI_API_KEY=sk-...      # required if enabling LLM
   export LLM_MAX_ITEMS=10           # cap items per location (optional)
   export LLM_MAX_CHARS=1000         # cap full-text chars per item (optional)
   export LLM_EMIT_ALERTS=1          # emit alerts from LLM-accepted items (optional)
   export LLM_MIN_SEVERITY=3         # only emit alerts for severity >= 3
   export LLM_CONFIRM_MIN_SEVERITY=2 # only count toward confirmation if severity >= 2
   export LLM_ALLOW_CATEGORIES="evacuation,hazmat,lockdown,outage,disaster,severe_weather,public_health,crime"
   export LLM_EMERGENCY_CATEGORIES="evacuation,hazmat,lockdown,outage,disaster,public_health,crime"  # which LLM categories become Pushover emergency
   export NEWS_REQUIRE_HAZARD=0      # send everything to the LLM; it will filter by locality + severity
   export PUSHOVER_PRIORITY2_SOUND=siren     # optional critical sound override
   export PUSHOVER_EMERGENCY_RETRY=30        # retry every 30s for emergency alerts
   export PUSHOVER_EMERGENCY_EXPIRE=300      # give up after 5 minutes

   python -m scripts.cli rebuild-keywords
   python -m scripts.prepper_alerts --dry-run
   ```
5. Launch the dashboard for config CRUD/observability:
   ```bash
   PYTHONPATH=. python -m scripts.cli dashboard --port 8501
   # Then open http://localhost:8501
   ```

6. Inspect intake when tuning queries:
   ```bash
   PYTHONPATH=. python -m scripts.cli debug-news --location home --limit 10
   PYTHONPATH=. python -m scripts.cli debug-news --location work --limit 10
   ```

See `SECURITY.md` for coordinated disclosure guidance.
