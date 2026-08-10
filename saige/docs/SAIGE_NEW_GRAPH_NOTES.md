# Saige production migration plan

**Branch:** `saige/developments` (do not commit/push unless asked)  
**Rule:** Evolve the existing supervisor graph in place — one workflow only.

Topology (unchanged):
`User Agent → Supervisor → Specialists|Joke → Synthesizer → Policy → HITL → Execute`

---

## Phases

### Phase 1 — Safety + durability ✅ (in progress / largely done)
1. **LLM:** Gemini 2.5 Flash Lite primary (`SAIGE_LLM_PROVIDER=gemini`, `GEMINI_MODEL_NAME` / `VERTEX_AI_MODEL` / `GEMINI_MODEL`); Grok reserved / not wired.
2. **Write lockdown:** `tools/tool_policy.py` strips write tools from specialist ReAct; runtime block + HITL-only Execute.
3. **SQL control plane:** DDL applied; `proposals` / `plans` / `monitoring` prefer SQL with JSON fallback.
4. **API hygiene:** Duplicate unsecured weather routes removed; `/proposals/{id}/events` audit; richer `/health`.

### Phase 2 — Media + streaming + observability ✅ (foundation landed)
5. **GCS:** `data/storage/media.py` (shim: `media_storage.py`) + `/attach` (local fallback when bucket unset); optional `scout=true` vision.
6. **True SSE:** `/chat/stream` uses `iter_chat_events` (graph `updates` stages + tokens + done).
7. **Traces:** `core/logging.py` (shim: `observability.py`) + `trace_id` on chat turns.

### Phase 3 — Agents + tests + deploy (partial)
8. Sibling **handoff** surfaced in synthesizer response (edges still HTTP siblings under `agents/sibling/`).
9. Vision scout module (`tools/agriculture/vision_scout.py`) via `/attach?scout`.
10. Proactive / monitoring / plan stores on SQL (`workers/proactive.py`).
11. `tests/` package — tool policy, graph, API routes.
12. Docker `COPY .` + HEALTHCHECK; entry remains `uvicorn api:app`.

---

## Remaining
- [ ] Wire Redis on staging for checkpoints + rate limits
- [ ] CORS allowlist instead of `*`
- [ ] Expand execute registry for remaining marketplace writes (proposal path)
- [ ] Soak / eval harness
- [ ] Set `SAIGE_MEDIA_GCS_BUCKET` in Cloud Run
- [ ] True sibling graph edges (optional; currently guided handoff)

---

## Local run

Saige may be on **:8002** if :8001 is a stale process. Frontend `.env.development` → `VITE_SAIGE_API_URL=http://localhost:8002`.

```powershell
cd oatmealfarmnetworkbackend\saige
py -3.13 apply_control_plane_schema.py   # once
py -3.13 -m uvicorn api:app --host 127.0.0.1 --port 8002 --reload
py -3.13 -m pytest tests -q
```
