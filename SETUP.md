# Setup & Deployment Guide

Everything you need to go from zero to a live, publicly accessible AI persona with voice + chat + calendar booking. Read once fully before starting.

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- Git
- Accounts on: **Anthropic**, **OpenAI**, **Qdrant Cloud**, **Vapi**, **Cal.com**, **Railway**, **Vercel**

All free tiers are sufficient except Railway ($5/mo minimum for always-on service).

---

## Step 1 — Fill in Your Data

### 1a. Resume
Place your resume PDF at:
```
backend/data/resume.pdf
```
The ingestion script parses it automatically. Any standard PDF works.

### 1b. Persona Config
Edit `backend/data/persona_config.json`. Every field you fill in becomes knowledge the AI can draw from. The richer the detail, the more specific the answers.

Key fields:
- `name` — used in every greeting and first-person response
- `summary` — 3-5 sentence bio; this is the single most-retrieved chunk
- `github_repos` — list of repo names to ingest (must match GitHub repo names exactly)
- `experience` — specific highlights with numbers/outcomes are better than job titles alone
- `honest_gaps` — the AI will acknowledge these when pressed; builds trust


---

## Step 2 — External Services Setup

### Qdrant Cloud (vector database)
1. Sign up at [cloud.qdrant.io](https://cloud.qdrant.io)
2. Create a free cluster (1GB, US East works well alongside Railway)
3. Copy the **Cluster URL** and **API Key** → goes into `QDRANT_URL` and `QDRANT_API_KEY`

### Cal.com (calendar booking)
1. Sign up at [cal.com](https://cal.com)
2. Connect your Google Calendar (Settings → Connected Calendars)
3. Create an event type named "30 Minute Interview" with slug `30min`
4. Set your actual availability hours
5. Go to Settings → API Keys → create a key → `CALCOM_API_KEY`
6. Your username is the part of `cal.com/YOUR_USERNAME` → `CALCOM_USERNAME`

### Vapi (voice agent)
1. Sign up at [vapi.ai](https://vapi.ai)
2. Go to Phone Numbers → Buy a number (US numbers ~$2/mo) → copy the **Phone Number ID** → `VAPI_PHONE_NUMBER_ID`
3. Go to API Keys → copy → `VAPI_API_KEY`
4. The assistant will be auto-created via the webhook on first call. No manual config needed.

> **India-based?** Buy a US Twilio number in Vapi. Vapi handles PSTN routing globally. Alternatively, Vapi supports web calls (browser) at no extra cost for testing.

---

## Step 3 — Backend Deployment (Railway)

Railway gives you a persistent backend with automatic HTTPS — critical for Vapi's webhook.

### 3a. Deploy
1. Push your repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
3. Select `ai-persona-scaler` → set root directory to `backend`
4. Railway auto-detects the Dockerfile

### 3b. Set environment variables
In Railway → your service → Variables tab, add all keys from `backend/.env.example`:

```
ANTHROPIC_API_KEY      = sk-ant-...
OPENAI_API_KEY         = sk-...
QDRANT_URL             = https://your-cluster.qdrant.io
QDRANT_API_KEY         = your-key
VAPI_API_KEY           = your-vapi-key
VAPI_PHONE_NUMBER_ID   = your-phone-number-id
CALCOM_API_KEY         = cal_live_...
CALCOM_USERNAME        = your-calcom-username
CALCOM_EVENT_TYPE_SLUG = 30min
GITHUB_USERNAME        = your-github-username
GITHUB_TOKEN           = ghp_...   (optional, raises API rate limit)
API_BASE_URL           = https://YOUR-SERVICE.up.railway.app
CORS_ORIGINS           = https://YOUR-FRONTEND.vercel.app
INGEST_SECRET          = pick-a-long-random-string
```

### 3c. Get your Railway URL
Once deployed, Railway assigns a URL like `https://ai-persona-scaler-production.up.railway.app`.  
Update `API_BASE_URL` in Railway vars with this URL.

### 3d. Verify
```bash
curl https://YOUR-SERVICE.up.railway.app/health
# → {"status":"ok","version":"1.0.0",...}
```

---

## Step 4 — Ingest Your Knowledge Base

With the backend live, trigger ingestion via the protected endpoint:

```bash
curl -X POST https://YOUR-SERVICE.up.railway.app/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"secret": "your-ingest-secret", "sources": ["resume","github","persona"]}'
```

Or locally (faster, shows progress):
```bash
cd backend
cp .env.example .env   # fill in your keys
pip install -r requirements.txt
python scripts/ingest_all.py
```

Expected output:
```
✅ Done!
   Sources processed : ['resume', 'github', 'persona']
   Chunks added      : 312
   Time elapsed      : 18.4s
```

Re-run this any time you update your resume or push new code to GitHub repos.

---

## Step 5 — Frontend Deployment (Vercel)

### 5a. Deploy
1. Go to [vercel.com](https://vercel.com) → New Project → Import from GitHub
2. Set root directory to `frontend`
3. Framework: Next.js (auto-detected)

### 5b. Environment variables
In Vercel → your project → Settings → Environment Variables:

```
NEXT_PUBLIC_API_URL        = https://YOUR-SERVICE.up.railway.app
NEXT_PUBLIC_PERSONA_NAME   = Your Full Name
NEXT_PUBLIC_CALCOM_URL     = https://cal.com/your-username/30min
```

### 5c. Deploy & get URL
Vercel gives you `https://your-project.vercel.app` — this is your **public chat URL**.

---

## Step 6 — Configure Vapi Voice Agent

### 6a. Set webhook URL
In Vapi dashboard → Assistants → Server URL:
```
https://YOUR-SERVICE.up.railway.app/api/vapi/webhook
```

This is the URL Vapi calls for every event. The backend auto-configures the assistant on first call.

### 6b. Test the voice agent
Call your Vapi phone number. You should hear:
> "Hi there! I'm the AI assistant set up by [your name] to represent them during this screening..."

### 6c. Customise the voice (optional)
In `backend/app/routes/vapi.py`, find `_build_assistant_config()` and change:
```python
"voiceId": "21m00Tcm4TlvDq8ikWAM"   # Rachel (default)
```
Browse voices at [elevenlabs.io/voice-library](https://elevenlabs.io/voice-library) and use any voice ID from there.

---

## Step 7 — Verify Everything End to End

### Chat
- [ ] Open your Vercel URL
- [ ] Ask: "Tell me about yourself" → should answer with your actual bio
- [ ] Ask: "Tell me about [one of your GitHub repos]" → should know the tech stack
- [ ] Ask: "What's your availability?" → booking modal should appear
- [ ] Complete a booking → you should get a Cal.com confirmation email

### Voice
- [ ] Call your Vapi phone number
- [ ] Ask: "Why are you right for this role?" → grounded answer
- [ ] Say: "Can we schedule an interview?" → should offer slots from your calendar
- [ ] Book a slot → you should get a Cal.com confirmation email

---

## Running Evals

```bash
cd backend
python scripts/run_evals.py --output evals/report.json
```

This runs 25 questions across 5 categories and produces:
- Hallucination rate
- Judge score (0-1) per question
- Average response latency
- Per-category breakdown

View the JSON report or pipe it through `jq` for quick stats:
```bash
cat evals/report.json | python -c "
import json,sys
r = json.load(sys.stdin)
print(f'Hallucination rate : {r[\"hallucination_rate\"]:.1%}')
print(f'Avg judge score    : {r[\"avg_judge_score\"]:.2f}')
print(f'Avg latency        : {r[\"avg_latency_ms\"]:.0f}ms')
"
```

---

## Updating Knowledge

Every time you update your resume or push to GitHub:

```bash
# Re-ingest (takes ~20-30s)
curl -X POST https://YOUR-SERVICE.up.railway.app/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"secret":"YOUR_INGEST_SECRET","sources":["resume","github","persona"]}'
```

No restart needed — Qdrant upserts are idempotent (same chunk hash → no duplicate).

---

## Keeping It Live (7+ Day Requirement)

Railway free tier sleeps after inactivity. Use the **Starter plan ($5/mo)** or set up a free uptime pinger:

**Option A: BetterStack (free)**
1. Sign up at [betterstack.com](https://betterstack.com)
2. Add monitor → URL: `https://YOUR-SERVICE.up.railway.app/health`
3. Ping every 5 minutes

**Option B: cron-job.org (free)**
1. Add a job hitting your `/health` endpoint every 10 minutes

Vercel frontend stays live indefinitely on the free plan.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Chat returns "I don't have context" | Ingestion not run or failed | Check Railway logs, re-run `ingest_all.py` |
| Voice agent doesn't answer | Vapi webhook URL wrong | Set Server URL in Vapi dashboard to your Railway URL |
| Booking fails | Cal.com API key / username wrong | Double-check env vars, test event type slug |
| First response >2s | Railway cold start | Upgrade to Railway Starter; use uptime pinger |
| CORS error in browser | `CORS_ORIGINS` missing Vercel URL | Update Railway env var, redeploy |
| GitHub repos not ingested | Repo names wrong in `persona_config.json` | Names must exactly match GitHub repo names |

---

## Cost Summary (7-Day Eval Period)

| Item | Cost |
|------|------|
| Railway Starter | $5 flat |
| Qdrant Cloud | $0 (free) |
| Vercel | $0 (free) |
| Anthropic (est. 200 turns) | ~$1.20 |
| OpenAI embeddings (ingestion + queries) | ~$0.10 |
| Vapi (est. 10 calls × 3min) | ~$1.50 |
| Cal.com | $0 (free) |
| **Total** | **~$7.80** |
