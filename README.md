# Preppers Alerts

Multi-location situational awareness pipeline for Harper's Ferry (home), Frederick (work), and user-defined locations. The project polls official (NWS, USGS) and intelligence (RSS, NewsAPI, GDELT, Wikipedia, etc.) sources on a 10-minute cadence, deduplicates and fuses the signals, and emits ultra-low-noise alerts via email and Pushover. A Streamlit dashboard surfaces config CRUD, thresholds, dry-run toggles, and observability for runs, metrics, and decisions.

## Key Features
- **Reliable automation:** GitHub Actions workflow runs every 10 minutes with concurrency control, installs Python 3.11 dependencies, rebuilds keywords, runs the orchestrator, and persists run state back into the repository when necessary using a bot identity.
- **Configurable fusion logic:** `config/locations.yaml` is the source of truth for monitored geos; `config/settings.yaml` controls thresholds, surge detection, quotas, and toggles.
- **Observability-first dashboard:** Streamlit UI now includes news stack + allowlist editors, per-location overrides, CRUD for locations/settings, insight into alerts, persistent metrics, and hallway testing (dry-run, send test push) without touching CI.
- **Alerts with guardrails:** Email/Pushover delivery layers implement severity gates, cooldowns, multi-source confirmation, and dedupe to keep false positives low.
- **LLM-first news triage (optional):** RSS + Google News feeds are fetched, full text is extracted, and an OpenAI model classifies prepper relevance with categories and severity. Accepted items can act as confirming evidence or emit alerts directly (env‑controlled).

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
2. Configure secrets under **Settings → Actions → Secrets and variables → Actions**:
   - `NWS_USER_AGENT`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ALERT_EMAIL_TO`, `PUSHOVER_USER_KEY`, `PUSHOVER_APP_TOKEN`
   - Optional: `NEWS_API_KEY`, `AIRNOW_API_KEY`, `GH_BOT_NAME`, `GH_BOT_EMAIL`, `GH_PUSH_TOKEN`
   - Optional (LLM classification): `OPENAI_API_KEY`
   - Optional (LLM classification): `OPENAI_API_KEY`
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
   
   python -m scripts.cli rebuild-keywords
   python -m scripts.prepper_alerts --dry-run
   ```
5. Launch the dashboard for config CRUD/observability:
   ```bash
   streamlit run dashboard/app.py
   ```

See `SECURITY.md` for coordinated disclosure guidance.
