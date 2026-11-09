# CRE Document Intelligence

Upload a commercial real estate due diligence package — rent roll or management report, leases, BOMA measurement, financials, county record — and get a scored deal analysis: tenant roster, RSF reconciliation, WALT, receivables, arithmetic checks, red flags, and what to request next.

## How it works

```
upload ─▶ ingest ─▶ classify ─▶ extract ×N ─▶ compute metrics ─▶ AI review ─▶ score + report
          (OCR)      (Claude)     (Claude)        (code)            (Claude)      (code)
```

Claude **reads** the documents. Code **computes** every number. That split is the point:

| Step | Where | What it does |
|---|---|---|
| Ingest | `backend/agents/document_parsing.py`, `ocr_agent.py` | Text from PDFs, XLSX/XLS, CSV. Scanned PDFs and screenshots go to Claude directly — no Tesseract needed. |
| Classify | `agents/universal_extractor.py` | Lease, lease abstract, rent roll, BOMA, management report, financial model, CAM rec, county PA, or other. |
| Extract | `agents/universal_extractor.py` + `config/extraction_prompts.py` | One extractor, one schema per document type. Values only as printed; nulls when absent. |
| Compute | `services/deal_metrics.py` | Tenant roster (rent roll + leases + BOMA + AR matched by suite and name), RSF reconciliation, WALT, NOI basis, vacancy, arithmetic checks against stated totals. |
| AI review | `agents/synthesis.py` | Lease-level risks, cross-document conflicts, executive summary, requests. Never produces dashboard numbers. |
| Score | `services/deal_metrics.py` | Six categories (20/20/20/20/15/15), every point with a reason. GREEN 80+, YELLOW 60–79, ORANGE 40–59, RED below 40. |

The RSF Recovery Alert fires when BOMA and the billed area differ by more than 5%; the estimate is gap × (average rent per SF + CAM per SF). With leases but no rent roll, only the leased suites are compared.

**Lease audit** (`services/lease_audit.py`, the Lease Audit tab) answers Don's core question — is each tenant paying for the space it occupies? Suite by suite:

- billed SF (rent roll or lease) vs BOMA SF, and the billed vs measured load factor
- base rent gap = SF gap × the tenant's rent per SF
- CAM gap = expense pool × BOMA share − CAM billed. The pool is the CAM reconciliation total when there is one, otherwise the management report's operating expenses annualized. Gross leases recover no CAM; base-year leases are marked as an upper bound.
- a leverage call from each lease's remeasurement and "deemed area" language: can remeasure, negotiable, locked, need lease, or overbilled (a claim risk)

## Layout

- `backend/` — FastAPI + LangGraph. `main.py` serves the API under `/api` and the built dashboard at `/`.
- `frontend/` — Next.js dashboard, built to static files (`npm run build` → `frontend/out`).
- An analysis runs as a background job: `POST /api/analyze` returns a job id, the browser polls `GET /api/jobs/{id}` and shows progress. Every request stays short, so no proxy timeout can cut off a long run.
- Finished analyses are saved in the browser (localStorage). The server keeps jobs in memory for 6 hours, so run **one** instance.
- **Adding documents to a deal.** Each result carries what was already read (`carry`: document types and extractions, no raw text). "Add documents" sends that back with only the new files as `prior`; the server reads just the new files, then recomputes metrics, the lease audit, flags, AI review, and score across everything. A new file with the same name replaces the old one; removing a document re-runs without reading anything. Because the carry lives with the saved analysis, this works in the browser where the deal was first analyzed.

## Deploy (any server with Docker)

One image holds everything. `docker-compose.yml` runs it behind Caddy, which gets an HTTPS certificate automatically and puts a username and password in front of the app.

1. Get a small Linux server (2 vCPU / 4 GB is plenty) and point a domain's A record at its IP.
2. Install Docker, clone this repo, then:
   ```bash
   cp .env.example .env
   docker run --rm caddy:2.8 caddy hash-password --plaintext 'choose-a-password'
   # put the hash in .env (inside single quotes), plus ANTHROPIC_API_KEY and DOMAIN
   docker compose up -d --build
   ```
3. Open `https://your-domain`, log in, and check `https://your-domain/api/health` shows `"anthropic_key_configured": true`.

To update: `git pull && docker compose up -d --build`.

Without Compose (e.g. a container platform that handles HTTPS itself): build the `Dockerfile`, set `ANTHROPIC_API_KEY`, expose port 8000, and use `/health` as the health check. Put your own login in front of it — the app has none.

## Deploy on Render

`render.yaml` defines one free web service built from the `Dockerfile`. In Render: **New → Blueprint**, pick this repo, enter `ANTHROPIC_API_KEY` when asked. Render generates `APP_PASSWORD`; find it under the service's **Environment** tab and log in as `don`.

The free plan sleeps after 15 idle minutes (the first visit after that takes about a minute) and has 512 MB of memory, so it runs one analysis at a time with uploads up to 50 MB.

## Environment

| Variable | Required | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | yes | `/api/analyze` returns 503 without it |
| `APP_PASSWORD` | yes, unless Caddy handles login | the app's own login (user `APP_USER`, default `don`); `/health` stays open |
| `DOMAIN`, `APP_USER`, `APP_PASSWORD_HASH` | with Compose | Caddy's HTTPS domain and login |
| `CLAUDE_MODEL` | no | defaults to `claude-sonnet-5-5` |
| `MAX_UPLOAD_MB` | no | defaults to 100 |
| `MAX_CONCURRENT_ANALYSES` | no | defaults to 3; extra jobs wait their turn |
| `LANGSMITH_API_KEY` | no | turns on LangSmith tracing |

## Run locally

```bash
# backend
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
uvicorn main:app --port 8000

# frontend with hot reload (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Or build the dashboard once (`cd frontend && npm run build`) and open http://localhost:8000 — the backend serves it.

## Tests

```bash
cd backend
pip install pytest pytest-asyncio httpx reportlab
python -m pytest
```

The suite runs the 5041 Bayou Blvd test package (`tests/fixtures.py`) through the metrics, scoring, the full graph with Claude stubbed, and the job API.

## Known limits

- **One instance.** Jobs are held in memory. Scaling out needs a shared job store (Redis or a database).
- **Run time.** A full package takes 1–3 minutes; three run at once by default.
- **Very long scans.** OCR transcribes up to about 20,000 tokens per file, and a single scanned file must be under 30 MB. The document is flagged if it was cut off.
