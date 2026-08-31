# Saige local runbook (fully functional + fast RAG)

Supervisor topology (code of record):

```
START → user_agent → supervisor
                      ├─ joke → END
                      └─ specialists (parallel) → synthesizer → policy_gate
                                                      ├─ hitl_gate → execute → END
                                                      └─ finalize → END
```

## One-command local stack

From `oatmealfarmnetworkbackend/saige`:

```powershell
docker compose up -d redis
```

Then three terminals:

```powershell
# 1) Main OFN API (:8000)
cd oatmealfarmnetworkbackend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 2) Saige standalone (:8001)
cd oatmealfarmnetworkbackend\saige
..\..\.venv\Scripts\python.exe -m uvicorn api:app --reload --host 127.0.0.1 --port 8001
# Prefer absolute venv path if relative fails:
# C:\...\oatmealfarmnetworkbackend\.venv\Scripts\python.exe -m uvicorn api:app --reload --host 127.0.0.1 --port 8001

# 3) Frontend (:5173)
cd oatmealfarmnetwork
npm run dev -- --host localhost --port 5173
```

## Required env alignment

| Variable | Where | Notes |
|----------|--------|------|
| `SECRET_KEY` | root `.env` **and** `saige/.env` | Must match or Saige returns 401 |
| `VITE_SAIGE_API_URL` | frontend `.env.development` | `http://localhost:8001` (no `/saige` prefix) |
| `OFN_BACKEND_URL` | `saige/.env` | `http://localhost:8000` for farm tools |
| `REDIS_ENABLED` | `saige/.env` | `true` |
| `REDIS_ALLOW_MEMORY_FALLBACK` | `saige/.env` | `true` only for local if Redis briefly down |
| `GOOGLE_CLOUD_PROJECT` + ADC | `saige/.env` | Required for Firestore vector RAG |

## Smoke checklist

1. `GET http://localhost:8001/ready` → `ready` with `jwt` + `redis` true  
2. `GET http://localhost:8001/health/firestore` → healthy  
3. Login on `http://localhost:5173/login`  
4. Saige chat → 200 (not 401/404)  
5. Response includes `citations` and `latency` spans  

## RAG features (this stack)

- Hybrid dense (Firestore KNN) + lexical fusion (RRF)
- Rerank + min score threshold
- Redis query/embedding cache
- Document-level citations (`doc_id`, `chunk_id`, `title`, `url`, `score`, `quote`)
- Parallel specialists with timeout
- Token SSE via stream queue

## Eval harness

```powershell
cd oatmealfarmnetworkbackend\saige
..\ .venv\Scripts\python.exe scripts\eval_rag.py --out scripts\eval_rag_out.json
```

## Staging parity

`deploy-saige.yml` and `deploy.ps1` set `REDIS_ENABLED=true` and mount `REDIS_URL` from Secret Manager so HITL/checkpoints match local.
