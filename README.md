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

The RSF Recovery Alert fires when BOMA and the billed area differ by more than 5%; the estimate is gap × average rent per SF. With leases but no rent roll, only the leased suites are compared.

## Layout

- `backend/` — FastAPI + LangGraph. Entry point `main.py`, pipeline `graph.py`.
- `frontend/` — Next.js dashboard. Calls `POST /backend/analyze` directly from the browser.
- `app/`, `components/`, `lib/` at the root mirror `frontend/` for the v0 dev server. Keep both in sync.
- Analyses are saved in the browser (localStorage). The backend stores nothing.

## Environment

| Variable | Where | Required | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | backend | yes | `/analyze` returns 503 without it |
| `CLAUDE_MODEL` | backend | no | defaults to `claude-sonnet-4-5` |
| `LANGSMITH_API_KEY` | backend | no | turns on LangSmith tracing |
| `NEXT_PUBLIC_BACKEND_URL` | frontend | no | defaults to `/backend` |
| `NEXT_PUBLIC_MAX_UPLOAD_MB` | frontend | no | defaults to 4.4 (Vercel's request limit is 4.5 MB) |

## Run locally

```bash
# backend
cd backend
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
uvicorn main:app --port 8000

# frontend (proxies /backend to localhost:8000)
cd frontend
npm install
npm run dev
```

## Tests

```bash
cd backend
pip install pytest pytest-asyncio httpx reportlab
python -m pytest
```

The suite runs the 5041 Bayou Blvd test package (`tests/fixtures.py`) through the metrics, scoring, the full graph with Claude stubbed, and the API.

## Known limits

- **Upload size.** Vercel caps a request at 4.5 MB. Large scanned packages need to be split, or the backend moved to a host without that cap (or files uploaded to blob storage first).
- **Run time.** A full package takes 1–3 minutes. The backend function's timeout must allow that.
- **Very long scans.** OCR transcribes up to about 20,000 tokens per file; the document is flagged if it was cut off.
