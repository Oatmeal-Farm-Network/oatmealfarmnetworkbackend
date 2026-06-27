# Main Backend — Test Plan (Post-Reorg)

> **Companion to:** `Tasks.md`, `REORG-CLEANUP.md`  
> **Integration branch:** `epic/backend-reorg`  
> **Purpose:** Divide pytest work evenly so the reorg can ship to `main` with automated smoke coverage — without one person owning everything.

The main backend currently has **no pytest suite** (only `python -c "import app.main"` in CI). Saige has its own tests under `saige/`; this plan covers **only the main `app/` backend**.

**Reorg cleanup** (import rewrite, shim deletion) stays in `REORG-CLEANUP.md` — David owns that there. **This doc is only for tests** and spreads work across all six developers.

---

## Balanced workload (v1)

| Developer | Name | Test branch | What you own |
|-----------|------|-------------|--------------|
| Dev 2 | David | `task/reorg-test-infra` | **Harness only:** `pytest.ini`, `conftest.py`, `/health` smoke, CI wiring (~1 small PR) |
| Dev 1 | Vidyanand | `task/reorg-tests-scripts` | Scripts/scrapers imports + repo hygiene + **`docker build`** verify |
| Dev 3 | Sankeerth | `task/reorg-tests-services` | Services/utils imports + service routers + **`server_all.py`** boot verify |
| Dev 4A | Bringesh | `task/reorg-tests-models-core` | Core models + auth/accounting routers + **`uvicorn app.main:app`** verify |
| Dev 4B | Navdeep | `task/reorg-tests-models-ag` | Ag/livestock/events models + ag router import hygiene |
| Dev 4C | Guia | `task/reorg-tests-models-web` | Web models + website/blog routers + `models.py` shim check |

Everyone writes **~1 test file**, **import/static checks for their slice**, **one mocked HTTP test**, and **one manual boot/deploy check**. David does **not** own domain tests or the full boot gate alone.

---

## Strategy

| Layer | Who | What |
|-------|-----|------|
| **Harness** | David | `pytest.ini`, `tests/conftest.py`, `tests/test_health.py`, CI update |
| **Domain smoke** | Vidyanand, Sankeerth, Bringesh, Navdeep, Guia | Imports + flat-import guards + one mocked route each |
| **Manual boot** | Split (see table above) | Each person verifies one launcher/deploy path |
| **Final gate** | Team | Full `pytest` green on epic → PR to `main` |

**What we are not doing in v1**

- 100% router coverage (150+ routers).
- Real MSSQL in CI (mocks only; optional `@pytest.mark.integration` locally).
- David writing every domain test on top of Phase 2 import cleanup (`REORG-CLEANUP.md`).

---

## Prerequisites

Per `REORG-CLEANUP.md`, David’s **`task/reorg-import-cleanup`** should land on epic **before** tests are finalized (flat `app.*` imports, shims deleted). Domain tests can be **drafted in parallel** on branches using `app.*` paths; merge after import cleanup to avoid rework.

---

## Git workflow — branches & merge targets

**Repo root:** `oatmealfarmnetworkbackend/` (where `.git` lives)

**Rule:** All test branches cut from **`epic/backend-reorg`**. Every test PR merges into **`epic/backend-reorg`** — not `main`.

**Final ship:** Full `pytest` green on epic → PR **`epic/backend-reorg` → `main`** (merge commit, **not** squash).

```
main  ←────────────────────────────────────────────  (final PR, team)
  ↑
epic/backend-reorg  ←── all test PRs merge here
  ↑
task/reorg-test-infra              (David — merge first)
task/reorg-tests-scripts           (Vidyanand)  ─┐
task/reorg-tests-services          (Sankeerth)   ├─ parallel after infra
task/reorg-tests-models-core       (Bringesh)    │
task/reorg-tests-models-ag         (Navdeep)     │
task/reorg-tests-models-web        (Guia)       ─┘
```

### Daily sync (everyone)

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git merge main
```

### Merge order

| Order | Developer | Branch | PR target |
|-------|-----------|--------|-----------|
| 1 | David | `task/reorg-test-infra` | → `epic/backend-reorg` |
| 2–6 | Vidyanand, Sankeerth, Bringesh, Navdeep, Guia | `task/reorg-tests-*` | → `epic/backend-reorg` (parallel) |
| 7 | Team | — | `epic/backend-reorg` → `main` |

### If your branch falls behind epic

```bash
git checkout <your-branch>
git fetch origin
git merge origin/epic/backend-reorg
git push
```

> **Per-developer git commands** are in each developer’s task section below.

---

## Shared rules (everyone)

1. **Use David’s `conftest.py`** — do not fork a second client fixture.
2. **Mock `get_db`** in HTTP tests — no real MSSQL in CI.
3. **Use `app.*` imports** in tests and in code under test.
4. **Per-dev done when:** your test file passes + your manual boot check (below) + PR merged.
5. **Before opening your PR:** `pytest tests/test_<your_file>.py` locally.
6. **Integration tests** — `@pytest.mark.integration`, skip when `DB_SERVER` unset (optional, local only).

---

## David (Dev 2) — test harness only

**Branch:** `task/reorg-test-infra`  
**Merge PR into:** `epic/backend-reorg`  
**Start after:** epic has latest cleanup from `REORG-CLEANUP.md` (or draft in parallel; merge when imports are stable).  
**Merge before:** domain test branches (Vidyanand, Sankeerth, Bringesh, Navdeep, Guia).

David does **not** write domain tests or run the entire boot gate alone. Phase 2 import cleanup remains in `REORG-CLEANUP.md`.

### Git commands

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-test-infra

# Add: pytest.ini, tests/conftest.py, tests/test_health.py
# Update: .github/workflows/smoke-backend.yml

git add pytest.ini tests/ .github/workflows/smoke-backend.yml
git commit -m "test: add pytest harness and health smoke CI"
git push -u origin task/reorg-test-infra
# GitHub PR:  task/reorg-test-infra  →  epic/backend-reorg
```

### Deliverables

```
pytest.ini
tests/
├── conftest.py       # TestClient + mocked get_db
└── test_health.py    # GET /health, GET /openapi.json
```

Keep `test_smoke.py` **out of David’s PR** — each domain owner adds import smoke in their own file (avoids one person owning all model imports).

### `pytest.ini`

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --tb=short
markers =
    integration: needs real DB env vars (skip in CI by default)
```

### `tests/conftest.py` (sketch)

```python
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db


def _fake_get_db():
    db = MagicMock()
    try:
        yield db
    finally:
        pass


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = _fake_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

### `tests/test_health.py` (sketch)

```python
def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_loads(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
```

### CI — `.github/workflows/smoke-backend.yml`

```yaml
- name: Run pytest
  run: pytest
```

Start with `pytest tests/test_health.py` in the first PR; switch to full `pytest` once domain files land.

### David’s manual check

- [ ] CI workflow passes on PR to epic.
- [ ] Another developer can add `tests/test_*.py` without changing `conftest.py`.

---

## Vidyanand (Dev 1) — scripts & repo hygiene

**Branch:** `task/reorg-tests-scripts`  
**Merge PR into:** `epic/backend-reorg`  
**Start after:** `task/reorg-test-infra` merged into epic  
**File:** `tests/test_scripts.py`

### Git commands

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-tests-scripts

# ... add tests/test_scripts.py ...
pytest tests/test_scripts.py

git add tests/test_scripts.py
git commit -m "test: scripts hygiene and import tests"
git push -u origin task/reorg-tests-scripts
# GitHub PR:  task/reorg-tests-scripts  →  epic/backend-reorg
```

### Tests to write

- No loose root `seed_*.py`, `migrate_*.py`, or `*.sql`.
- `scripts/` and `scrapers/` use `app.database` / `app.*` — no flat `from database import` or `from models import`.
- At least two moved scripts verified by reading source or import.

### Example

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_loose_root_artifacts():
    assert list(ROOT.glob("seed_*.py")) == []
    assert list(ROOT.glob("migrate_*.py")) == []
    assert list(ROOT.glob("*.sql")) == []


def test_backfill_script_uses_app_database():
    text = (ROOT / "scripts" / "backfill_field_size_from_boundary.py").read_text()
    assert "from app.database import" in text
    assert "from database import" not in text
```

### Vidyanand’s manual check

- [ ] `docker build .` succeeds from repo root.
- [ ] Container starts (`uvicorn app.main:app` via Dockerfile CMD).

---

## Sankeerth (Dev 3) — services, utils & service routers

**Branch:** `task/reorg-tests-services`  
**Merge PR into:** `epic/backend-reorg`  
**Start after:** `task/reorg-test-infra` merged into epic  
**File:** `tests/test_services.py`

### Git commands

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-tests-services

# ... add tests/test_services.py ...
pytest tests/test_services.py

git add tests/test_services.py
git commit -m "test: services, utils, and service-router tests"
git push -u origin task/reorg-tests-services
# GitHub PR:  task/reorg-tests-services  →  epic/backend-reorg
```

### Scope

**Modules** — import without root shims:

- `app.services.marketplace_stripe`, `marketplace_catalog`, `event_emails`, `meeting_emails`, `image_service`
- `app.utils.page_templates`, `geo_utils`

**Routers** — static guard: these files must not use flat `from database import`, `import models`, or root shims:

- `app/routers/marketplace.py`, `stripe_payments.py`, `meetings.py`
- `app/routers/website_builder.py`, `website_ai.py`
- At least **3** `app/routers/event_*.py` files (pick the ones you moved imports for in cleanup)

**HTTP (mocked):** one route that lazy-imports a service (e.g. `meetings` or `event_simple`).

### Example

```python
def test_marketplace_stripe_has_router():
    from app.services import marketplace_stripe
    assert hasattr(marketplace_stripe, "stripe_router")


def test_marketplace_router_no_flat_database_import():
    text = open("app/routers/marketplace.py").read()
    assert "from database import" not in text
    assert "from app.database import" in text
```

### Sankeerth’s manual check

- [ ] `uvicorn server_all:app --port 8000` starts without import errors.
- [ ] `GET /health` returns 200 through `server_all` (optional curl).

---

## Bringesh (4A) — core models & auth/accounting routers

**Branch:** `task/reorg-tests-models-core`  
**Merge PR into:** `epic/backend-reorg`  
**Start after:** `task/reorg-test-infra` merged into epic  
**File:** `tests/test_models_core.py`

### Git commands

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-tests-models-core

# ... add tests/test_models_core.py ...
pytest tests/test_models_core.py

git add tests/test_models_core.py
git commit -m "test: core models and auth/accounting router tests"
git push -u origin task/reorg-tests-models-core
# GitHub PR:  task/reorg-tests-models-core  →  epic/backend-reorg
```

### Scope

**Models** — `from app.models import` works:

- `People`, `Business`, `Account`, `Invoice`, `JournalEntry`, `Pricing`

**Routers** — no flat imports in:

- `app/routers/auth.py`, `accounting.py`, `businesses.py`, `forgot_password.py`

**HTTP (mocked):** `GET /auth/site-settings` — defaults when DB returns no row.

### Example

```python
from app.models import People, Invoice, Pricing


def test_core_model_tables():
    assert People.__tablename__ == "People"
    assert Invoice.__tablename__ == "Invoice"
    assert Pricing.__tablename__ == "Pricing"


def test_auth_router_uses_app_imports():
    text = open("app/routers/auth.py").read()
    assert "from app.database import" in text or "from app.core" in text
    assert "from database import" not in text
```

### Bringesh’s manual check

- [ ] `uvicorn app.main:app --port 8080` starts clean.
- [ ] `python -c "from app.models import People, Invoice, Pricing; print('ok')"`

---

## Navdeep (4B) — ag / livestock / events models & routers

**Branch:** `task/reorg-tests-models-ag`  
**Merge PR into:** `epic/backend-reorg`  
**Start after:** `task/reorg-test-infra` merged into epic  
**File:** `tests/test_models_ag.py`

### Git commands

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-tests-models-ag

# ... add tests/test_models_ag.py ...
pytest tests/test_models_ag.py

git add tests/test_models_ag.py
git commit -m "test: ag models and livestock router tests"
git push -u origin task/reorg-tests-models-ag
# GitHub PR:  task/reorg-tests-models-ag  →  epic/backend-reorg
```

### Scope

**Models** — import via `app.models`:

- `Animal`, `Field`, `Produce`, `Event`, `Association` (+ spot-check a few more from your four files)

**Model files** — all use `from app.database import Base`:

- `livestock.py`, `precision_ag.py`, `crops.py`, `events.py`

**Routers** — no flat imports in:

- `app/routers/livestock.py`, `animals.py`, `precision_ag.py`, `events.py`, `associations.py`

**HTTP (mocked):** one ag/livestock route — expect 200, 401, or 404, not 500.

### Example

```python
from app.models import Animal, Field, Event


def test_ag_model_tables():
    assert Animal.__tablename__ == "Animal"
    assert Field.__tablename__ == "Field"


def test_livestock_router_no_flat_models_import():
    text = open("app/routers/livestock.py").read()
    assert "from models import" not in text
```

### Navdeep’s manual check

- [ ] `pytest tests/test_models_ag.py` passes.
- [ ] `python -c "from app.models import Animal, Field, Event; print('ok')"`

---

## Guia (4C) — web models & website routers

**Branch:** `task/reorg-tests-models-web`  
**Merge PR into:** `epic/backend-reorg`  
**Start after:** `task/reorg-test-infra` merged into epic  
**File:** `tests/test_models_web.py`

### Git commands

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-tests-models-web

# ... add tests/test_models_web.py ...
pytest tests/test_models_web.py

git add tests/test_models_web.py
git commit -m "test: web models and website router tests"
git push -u origin task/reorg-tests-models-web
# GitHub PR:  task/reorg-tests-models-web  →  epic/backend-reorg
```

### Scope

**Models** — `from app.models import`:

- `BusinessWebsite`, `BusinessWebPage`, `SiteSettings`, `BusinessBlogPost`

**Structural** — root `models.py` is shim-only (no `class X(Base):`).

**Routers** — no flat imports in:

- `app/routers/website_builder.py`, `website_ai.py`, `blog.py`

**HTTP (mocked):** one `blog` or `website_builder` route — not 500.

### Example

```python
import re
from pathlib import Path
from app.models import BusinessWebsite, SiteSettings


def test_web_model_tables():
    assert BusinessWebsite.__tablename__ == "BusinessWebsite"
    assert SiteSettings.__tablename__ == "SiteSettings"


def test_root_models_py_is_shim_only():
    text = Path("models.py").read_text()
    assert "from app.models import" in text
    assert re.search(r"^class \w+\(Base\):", text, re.M) is None
```

### Guia’s manual check

- [ ] `pytest tests/test_models_web.py` passes.
- [ ] `GET /openapi.json` lists website/blog routes (via `client` fixture or curl against local uvicorn).

---

## Optional integration tests (any developer, local only)

```python
import os
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("DB_SERVER"), reason="DB env not configured")
def test_db_ping():
    response = TestClient(app).get("/test-db")
    assert response.status_code == 200
```

```bash
pytest -m integration    # local only; not in default CI
```

---

## Team — final merge to `main`

**Start after:** all test PRs (#1–#6) merged into `epic/backend-reorg` and full `pytest` passes.

### Git commands

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git merge main

pip install -r requirements.txt
pytest

git push origin epic/backend-reorg
# GitHub PR:  epic/backend-reorg  →  main  (merge commit, NOT squash)
```

---

## Pre-merge checklist (epic → main)

| Check | Owner |
|-------|-------|
| Phase 2 import cleanup merged (`REORG-CLEANUP.md`) | David |
| `task/reorg-test-infra` merged | David |
| `tests/test_scripts.py` + docker build | Vidyanand |
| `tests/test_services.py` + `server_all` boot | Sankeerth |
| `tests/test_models_core.py` + `uvicorn app.main` | Bringesh |
| `tests/test_models_ag.py` | Navdeep |
| `tests/test_models_web.py` + `models.py` shim | Guia |
| Full `pytest` green on epic | Team |
| Smoke CI on PR to `main` | Team |
| `epic/backend-reorg → main` (merge commit) | Team |

---

## Quick commands

```bash
cd oatmealfarmnetworkbackend/
pip install -r requirements.txt
pytest                              # full suite (after all PRs land)
pytest tests/test_health.py         # harness only
pytest tests/test_models_core.py    # your slice
pytest -m "not integration"         # skip DB tests
```

---
