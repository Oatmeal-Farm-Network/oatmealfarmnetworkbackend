# Saige package migration — results

**Branch:** `saige/developments`  
**Scope:** Commits 1–11 (code moves + shims) + docs/deploy stabilization.

## Entrypoints (unchanged)

| Entry | Status |
|-------|--------|
| `uvicorn api:app` | OK via root shim `api.py` → `app.api:app` |
| `server_all.py` mount `/saige` | Unchanged |
| Frontend routes | Unchanged |
| Sibling HTTP agents | Still independent of LangGraph |

## Deploy verification

| Artifact | Check |
|----------|-------|
| `saige/Dockerfile` | `COPY . .` + `CMD ["uvicorn", "api:app", …]` |
| `saige/Dockerfile.backend` | Same |
| `saige/docker-compose.yml` | Builds `Dockerfile.backend`, `PYTHONPATH=/app` |
| `saige/deploy.ps1` | Builds `./saige` image; no flat-file COPY |
| `.github/workflows/deploy-saige.yml` | `docker build -f saige/Dockerfile.backend ./saige` |

Images must copy the **full package tree**. Copying only `*.py` at the Saige root would omit `app/`, `graph/`, etc.

## Import smoke (local)

```text
from api import app
from graph import graph
from chat import run_chat
from execute_registry import run_approved_tool
from llm import *
from rag import *
```

`pytest saige/tests` — expected green after migration.

## Package map (canonical)

| Package | Role |
|---------|------|
| `app/` | FastAPI |
| `graph/` | LangGraph farm graph |
| `chat/` | Turn handlers, streaming, history, buffer |
| `core/` | Config, security, policies, logging, paths |
| `schemas/` | Models + contracts |
| `tools/` | Execute registry, tool policy, domain tools |
| `agents/sibling/` | Cassia, Pairsley, Rosemarie, Chef |
| `integrations/` | Gemini, RAG, embeddings, Firestore seed |
| `services/` | Shared non-tool services |
| `data/` | SQL, Redis, media storage |
| `workers/` | Farm digest + proactive jobs |

Root flat modules remain **compatibility shims**. Prefer editing package implementations.

## Remaining cleanup (optional, not blocking)

- Remove root shims only after all call sites use package imports
- Retire exploratory notebooks / legacy `test_*.py` at Saige root if superseded by `tests/`
- Wire Redis on staging for checkpoints + rate limits
- Expand execute registry / soak harness (product work, not layout)
