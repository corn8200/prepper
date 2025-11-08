# Deployment + Setup To-Do

This checklist covers everything that still needs **your** action. Work through it top-to-bottom. Each step is written for a low-code user.

## 1. Environment + Repo
- [ ] Make sure git is initialized and clean: `git status`. If needed run `git init` once.
- [ ] Commit current work and push to your remote:
  1. `git add .`
  2. `git commit -m "Initial prepper alerts scaffolding"`
  3. `git remote add origin <your-repo-url>` (first time only)
  4. `git push -u origin main`

## 2. Python Prereqs
- [ ] Install Python 3.11 (if not already) and create a virtualenv: `python3 -m venv .venv`
- [ ] Activate it (`source .venv/bin/activate`) and install deps: `pip install -r requirements.txt`
- [ ] Verify everything passes: `python -m pytest` and `python -m ruff check .`

## 3. Configuration Files
- [ ] Open `config/locations.yaml` and confirm coordinates/labels/roads for every location you want monitored (home, work, etc.).
- [ ] Edit `config/settings.yaml` if you need different thresholds, domains, or NewsAPI modes.
- [ ] Run `python -m scripts.cli rebuild-keywords` after changing locations so `config/keywords.yaml` stays in sync.

## 4. GitHub Repository Secrets (Settings → Actions → Secrets and variables → Actions)
Add these values from your accounts/services:
- `NWS_USER_AGENT` – something like `yourname-prepper-alerts/1.0 (email@yourdomain.com)`
- `GMAIL_USER` / `GMAIL_APP_PASSWORD` – Gmail account + app password for sending emails
- `ALERT_EMAIL_TO` – where email alerts should land
- `PUSHOVER_USER_KEY` / `PUSHOVER_APP_TOKEN` – from your Pushover account/app
- Optional but recommended:
  - `NEWS_API_KEY` (NewsAPI.org)
  - `AIRNOW_API_KEY`
  - `GH_BOT_NAME`, `GH_BOT_EMAIL`, `GH_PUSH_TOKEN` (if you want CI to push data changes back)

## 5. Local Testing
- [ ] Run the orchestration locally in dry-run mode to make sure configs are valid: `python -m scripts.prepper_alerts --dry-run`
- [ ] Inspect `data/latest_run.json` to see the summary output.

## 6. Streamlit Dashboard (local)
- [ ] Launch the dashboard: `streamlit run dashboard/app.py`
- [ ] Use the UI to tweak locations/settings and confirm validation works before deploying.

## 7. Docker / Cloud Run Deployment
1. **Install gcloud**: follow https://cloud.google.com/sdk/docs/install if you haven’t already.
2. **Set environment variables** (adjust to your project):
   ```bash
   PROJECT_ID="YOUR_GCP_PROJECT_ID"
   REGION="us-east1"
   SERVICE="preppers-dashboard"
   DOMAIN="app.yourdomain.com"
   GROUP_EMAIL="dash-viewers@yourdomain.com"
   SUPPORT_EMAIL="you@yourdomain.com"
   ```
3. **Authenticate and set defaults**:
   ```bash
   gcloud auth login
   gcloud config set project "$PROJECT_ID"
   gcloud config set run/region "$REGION"
   ```
4. **Enable APIs** (safe to rerun):
   ```bash
   gcloud services enable run.googleapis.com iam.googleapis.com iap.googleapis.com \
     secretmanager.googleapis.com cloudbuild.googleapis.com
   ```
5. **Build + deploy the container** (Dockerfile is already provided):
   ```bash
   gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE
   gcloud run deploy "$SERVICE" \
     --image gcr.io/$PROJECT_ID/$SERVICE \
     --allow-unauthenticated=false \
     --region "$REGION" \
     --memory 1Gi
   ```
6. **Configure Identity-Aware Proxy (Workspace SSO)**:
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
7. **Domain mapping + DNS**:
   ```bash
   gcloud run domain-mappings create \
     --service "$SERVICE" \
     --domain "$DOMAIN" \
     --region "$REGION" || true
   ```
   The command prints DNS records (A/CNAME). Add them at your registrar (Namecheap, Cloudflare, etc.) and wait for propagation.
8. **Verify access**: browse to `https://$DOMAIN` and log in with a user from `$GROUP_EMAIL`.

## 8. Monitoring & Maintenance
- [ ] Check Cloud Run logs and GitHub Actions runs after first deployment to confirm everything succeeds.
- [ ] Periodically rotate API keys/app passwords and update the GitHub/Secret Manager entries.
- [ ] Keep dependencies updated: `pip install --upgrade -r requirements.txt`, rerun tests, commit, push.
