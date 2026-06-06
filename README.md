# AI Persona — RAG-Grounded Voice & Chat Representative

A production-grade AI system that represents a candidate in professional screening conversations — answering questions about their background with evidence from their actual resume and GitHub repos, and autonomously booking interviews without any human in the loop.

> Built for reliability, not demos. Every answer is grounded in retrieved source material. The voice agent runs under 700ms first-response latency. The eval framework measures this objectively.

---

## What It Does

| Capability | Detail |
|------------|--------|
| **Voice agent** | Phone number powered by Vapi · Deepgram STT · ElevenLabs TTS · <700ms first response |
| **Chat interface** | Streaming SSE chat · Markdown rendering · Source + confidence badges |
| **RAG knowledge base** | Resume PDF + GitHub repos + structured persona facts → Qdrant |
| **Calendar booking** | Real-time slot lookup + confirmed booking via Cal.com API |
| **Eval framework** | Claude-as-judge hallucination detection · 25-question golden set · retrieval precision |
| **Anti-hallucination** | Confidence gating · grounded system prompt · honest gap acknowledgement |

---

## Architecture

```
Phone call / Chat
      │
      ▼
Vapi (STT + TTS)  /  Next.js frontend
      │                    │
      └─────────┬──────────┘
                ▼
        FastAPI backend  (Railway)
                │
        ┌───────┴──────────┐
        ▼                  ▼
   RAG Pipeline        Cal.com API
   ┌──────────────┐
   │ Query reform │  ← Claude Haiku
   │ Embed query  │  ← OpenAI ada-3
   │ Qdrant MMR   │  ← top-6 chunks
   │ Claude stream│  ← Sonnet
   └──────────────┘
```

Full architecture with latency budget → [`docs/architecture.md`](docs/architecture.md)

---

## Stack

**Backend:** Python · FastAPI · Anthropic Claude (Sonnet + Haiku) · OpenAI Embeddings · Qdrant  
**Voice:** Vapi · Deepgram Nova-2 · ElevenLabs  
**Frontend:** Next.js 14 · TypeScript · Tailwind CSS  
**Calendar:** Cal.com REST API  
**Infra:** Railway (backend) · Vercel (frontend) · Qdrant Cloud (vector DB)

---

## Repo Structure

```
ai-persona-scaler/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI entry point
│   │   ├── config.py             # Pydantic settings
│   │   ├── models.py             # Request/response types
│   │   ├── rag/
│   │   │   ├── ingest.py         # PDF + GitHub + JSON ingestion
│   │   │   ├── retriever.py      # Qdrant search + MMR reranking
│   │   │   └── pipeline.py       # Stream generation + session history
│   │   ├── agents/
│   │   │   └── system_prompts.py # Voice + chat persona prompts
│   │   ├── routes/
│   │   │   ├── chat.py           # SSE chat + booking endpoints
│   │   │   ├── vapi.py           # Vapi webhook + custom LLM endpoint
│   │   │   └── calendar.py       # Standalone calendar routes
│   │   └── integrations/
│   │       ├── calcom.py         # Cal.com slot + booking API
│   │       └── github.py         # GitHub repo metadata
│   ├── scripts/
│   │   ├── ingest_all.py         # CLI ingestion runner
│   │   └── run_evals.py          # Eval runner (outputs JSON report)
│   ├── evals/
│   │   └── golden_qa.json        # 25 golden Q&A pairs
│   ├── data/
│   │   ├── persona_config.json   # Structured persona facts (fill this in)
│   │   └── resume.pdf            # Your resume (add before ingesting)
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── app/                  # Next.js app router
│       └── components/
│           ├── ChatInterface.tsx  # Main shell
│           ├── ChatMessage.tsx    # Message bubble + source badges
│           ├── ChatInput.tsx      # Auto-grow textarea
│           └── BookingModal.tsx   # Slot picker + booking form
├── docs/
│   └── architecture.md
├── docker-compose.yml            # Full local dev
├── README.md
└── SETUP.md                      # Step-by-step deployment guide
```

---

## Quick Start (Local)

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/ai-persona-scaler
cd ai-persona-scaler

# 2. Backend env
cp backend/.env.example backend/.env
# Fill in ANTHROPIC_API_KEY, OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY

# 3. Add your data
cp /path/to/your/resume.pdf backend/data/resume.pdf
# Edit backend/data/persona_config.json with your real info

# 4. Ingest knowledge base
cd backend
pip install -r requirements.txt
python scripts/ingest_all.py

# 5. Run backend
uvicorn app.main:app --reload

# 6. Frontend (new terminal)
cd ../frontend
cp .env.example .env.local
npm install && npm run dev
```

Open `http://localhost:3000`.

---

## Deployment

Full step-by-step → [`SETUP.md`](SETUP.md)

| Service | Platform | Free? |
|---------|----------|-------|
| Backend API | Railway | $5/mo starter |
| Frontend | Vercel | Free |
| Vector DB | Qdrant Cloud | Free (1GB) |
| Voice | Vapi | Pay-per-minute |
| Calendar | Cal.com | Free |

---

## Evaluations

```bash
cd backend
python scripts/run_evals.py --output evals/report.json
```

Runs 25 questions across categories: general, technical, resume, calendar, adversarial.

Uses Claude Haiku as judge — outputs hallucination rate, judge score distribution, latency stats, and per-category breakdown.

See [`SETUP.md#evals`](SETUP.md#running-evals) for full instructions.

---

## Key Design Decisions

**Why custom LLM endpoint for Vapi instead of native Claude integration?**  
Native Vapi + Claude doesn't let us inject per-turn RAG context. The custom endpoint intercepts every message, runs retrieval, and injects chunks into the system prompt before forwarding to Claude — giving us grounded voice responses with no added latency round-trip.

**Why MMR reranking over pure cosine similarity?**  
Top-K cosine often returns near-duplicate chunks (same paragraph chunked differently). MMR with λ=0.5 balances relevance and diversity, giving Claude richer context from multiple document sections.

**Why Haiku for query reformulation instead of Sonnet?**  
Reformulation is a simple instruction-following task. Haiku at ~70ms adds negligible latency while saving ~8× the cost vs Sonnet for this step.

**In-memory session store vs Redis:**  
For a 7-day eval deployment with light concurrent traffic, in-memory is sufficient. The session dict is bounded by `HISTORY_WINDOW` setting. Redis swap is a one-line change in `pipeline.py`.

---

## License

MIT
