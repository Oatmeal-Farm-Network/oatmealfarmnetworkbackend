# Saige package migration plan

**Branch:** `saige/developments`  
**Rule:** Incremental moves only. Compatibility shims preserve flat imports. No bulk rewrite. No deletes until verified.

## Goals

- Production-grade layout: `app/`, `core/`, `graph/`, `chat/`, `tools/`, `agents/`, `data/`, `integrations/`, `schemas/`, `workers/`
- Preserve behavior and entrypoints:
  - `uvicorn api:app`
  - `server_all.py` mount at `/saige`
  - Frontend routes unchanged (`/chat`, `/chat/stream`, `/resume`, `/proposals/{id}/decide`, sibling agents)
  - LangGraph supervisor + HITL interrupt/resume unchanged

## Constraints / risks

| Risk | Mitigation |
|------|------------|
| `graph/` package vs root `graph.py` | Package `__init__.py` re-exports; remove root module only after shim equivalent works |
| `chat/` package vs root `chat.py` | Same as graph |
| Existing `data/` runtime JSON | Keep JSON under `saige/data/`; resolve via `core.paths`; Python modules in `data/sql|redis|…` |
| Circular imports (graph→nodes, chat→graph) | Keep one-way edges; extract routing carefully |
| Lazy imports in `api.py` / `nodes.py` | Preserve try/except lazy imports when moving |

## Deprecated / orphans (do not delete yet)

- `models.py` — deprecated shim → `saige_models`
- `main.py` — compat exports (not ASGI entry)
- Notebooks / pngs / `null` — exploratory
- Orphan `__pycache__` only (`*_supervisor`, `llm_grok`, …) — already deleted sources

## Target mapping (later commits)

| Current | Target |
|---------|--------|
| `api.py` | `app/api.py` + root shim `api.py` |
| lifespan / deps | `app/lifecycle.py`, `app/dependencies.py` |
| `config.py` | `core/config.py` + shim |
| `jwt_auth.py` | `core/security.py` + shim |
| `observability.py` | `core/logging.py` + shim |
| `policy.py` | `core/policies.py` + shim |
| `graph.py`, `nodes.py` | `graph/graph.py`, `graph/nodes.py` |
| `chat.py`, `chat_history.py` | `chat/service.py`, `chat/history.py` |
| sibling agents | `agents/sibling/*` |
| specialists | remain in `graph/nodes.py` initially; thin re-exports under `agents/specialists/` |
| `execute_registry`, `tool_policy`, domain tools | `tools/` (+ domain subpackages) |
| SQL stores / db | `data/sql/` |
| redis / buffer | `data/redis/` |
| media | `data/storage/` |
| `llm.py`, `rag.py` | `integrations/gemini.py`, `integrations/rag.py` |
| `saige_models`, `Data_Contract` | `schemas/models.py`, `schemas/contracts.py` |
| embeddings / digest / proactive | `workers/` |

## Commit sequence (executed)

1. Package skeleton + `core/paths.py` + this plan
2. `core/` + `schemas/` + shims
3. `graph/` package
4. `chat/` package
5. FastAPI → `app/`
6. Domain tools → `tools/`
7. Shared services → `services/`
8. Persistence → `data/`
9. Integrations (Gemini / RAG / embeddings)
10. Sibling HTTP agents → `agents/sibling/`
11. Workers (`farm_digest`, `proactive`)
12. Docs / deploy path updates (this stabilization pass)

Each step: move one subsystem → shims immediately → import/tests → commit.

## Rollback

```bash
git revert <commit>
# or
git reset --hard <sha-before-step>
```

## Commit 1 status

- [x] Package skeleton + `core/paths.py` + this plan
- [x] `graph/` / `chat/` package bridges to legacy root modules

## Commit 2 status

- [x] Move config / security / policies / tool_policies / logging into `core/`
- [x] Move saige models + Data_Contract into `schemas/`
- [x] Root compatibility shims + path safety aliases

## Commit 3 status

- [x] Move `graph.py` / `nodes.py` into `graph/` package
- [x] Add `graph/routing.py` + `graph/state.py`
- [x] Package `__init__.py` lazy-exports compiled graph
- [x] Root `nodes.py` shim; root `graph.py` discoverability stub (package wins imports)

## Commit 4 status

- [x] Move chat turn handlers into `chat/service.py` + `chat/streaming.py`
- [x] Move Firestore history → `chat/history.py`, Redis buffer → `chat/buffer.py`
- [x] Root shims: `chat.py` (stub), `chat_history.py`, `message_buffer.py`
- [x] Compat aliases: `get_history`, `get_recent_messages`

## Commits 5–11 status

- [x] FastAPI → `app/` (`api.py` shim → `uvicorn api:app`)
- [x] Domain tools → `tools/`
- [x] Shared services → `services/`
- [x] Persistence → `data/`
- [x] Integrations → `integrations/`
- [x] Sibling agents → `agents/sibling/`
- [x] Workers → `workers/`

## Stabilization (docs / deploy)

- [x] Dockerfiles copy full package (`COPY . .`), not `*.py` only
- [x] Image CMD remains `uvicorn api:app`
- [x] Docs updated to package paths (README, HANDOFF, migration results)
- [x] Verification report: `docs/MIGRATION_RESULTS.md`

