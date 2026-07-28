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

## Commit sequence

1. **Commit 1 (this)** — Package skeleton + `__init__.py` + `core/paths.py` + this plan. **No production moves.**
2. **Commit 2** — `core/` + `schemas/` (config, security, logging, policies, models) + shims
3. **Commit 3** — `graph/` + `chat/` + package re-exports
4. **Commit 4** — `tools/` + `agents/`
5. **Commit 5** — `data/` + `integrations/` + `workers/`
6. **Commit 6** — Docker / deploy / pytest / docs path updates
7. **Commit 7** — Verification report (`MIGRATION_RESULTS.md`)

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
- [x] Root compatibility shims for all previous import paths
- [x] `core.paths` used for media dir + `.env` resolution
- [x] Compat aliases: `settings`, `check_proposal`, `filter_tools`, `MessageContract`

