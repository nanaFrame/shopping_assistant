# Shopping Assistant MVP

An AI-powered shopping recommendation backend that uses LangGraph for agent orchestration, DataForSEO for product data, and Google Gemini for intelligent reasoning.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure secrets
cp .env.example .env
# Edit .env with your actual API keys

# 3. Run the server
uvicorn app.main:app --reload --port 8000

# 4. Open the test page
# http://localhost:8000
```

## Configuration

- **`.env`** — Sensitive credentials (API keys, passwords)
- **`config.yaml`** — Business configuration (model params, cache TTL, timeouts)

## Architecture

```
app/
  main.py              # FastAPI entry point
  config.py            # Unified config loader
  api/routes/          # HTTP endpoints (sessions, chat, stream)
  application/         # Service layer (chat, session, stream)
  agent/               # LangGraph state graph + 15 nodes
  integrations/        # DataForSEO + LLM gateways
  storage/             # SQLite sessions, JSON cache, event buffer
  domain/              # Models, events, identifiers
  web/test_page/       # Built-in test UI
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Test page |
| GET | `/healthz` | Health check |
| POST | `/api/sessions` | Create/resume session |
| POST | `/api/chat` | Submit query, start recommendation |
| GET | `/api/stream` | SSE event stream |

## Agent Flow

The recommendation agent follows a 15-node LangGraph topology:

1. **ContextMerge** — Merge user message with session history
2. **IntentParse** — Classify intent (discovery/refinement/targeted/comparison/clarify)
3. **QueryBuild** — Build search plan
4. **LocalCacheRead** — Check local cache coverage
5. **ProductSearch** — Search DataForSEO Products endpoint
6. **StreamCandidates** — Emit candidate cards to stream
7. **CacheUpdateCandidates** — Persist candidates to cache
8. **ProductContextResolve** — Resolve product context
9. **CandidateScore** — Score candidates via LLM
10. **Top3Select** — Pick differentiated Top 3
11. **StreamTop3** — Emit Top 3 to stream
12. **DetailFetch** — Fetch missing fields (Product Info/Sellers/Reviews)
13. **CacheUpdateEnrich** — Persist enriched data
14. **StreamEnrich** — Emit enrichment patches
15. **AnswerGenerate** — Generate intro, comparison table, reasons
16. **MemoryUpdate** — Persist session state
