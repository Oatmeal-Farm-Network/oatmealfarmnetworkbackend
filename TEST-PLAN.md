# Main Backend — Test Plan (Post-Reorg)

> **Companion to:** `Tasks.md`, `REORG-CLEANUP.md`  
> **Integration branch:** `epic/backend-reorg`  
> **Purpose:** Divide pytest work among the team so the reorg can ship to `main` with automated smoke coverage — without one person writing every test.

The main backend currently has **no pytest suite** (only `python -c "import app.main"` in CI). Saige has its own tests under `saige/`; this plan covers **only the main `app/` backend**.

---

## Strategy

| Role | Owner | Responsibility |
|------|-------|----------------|
| **Shared test infra** | David (Dev 2) | `pytest.ini`, `tests/conftest.py`, smoke/health tests, CI wiring, boot gate |
| **Domain tests** | Vidyanand, Sankeerth, Bringesh, Navdeep, Guia | Import + mocked HTTP tests for the slice each developer owns from the reorg |

**Why split this way**

- Each developer already knows their moved code (models, services, scripts).
- Work is parallelizable — five small PRs instead of one giant test PR.
- Failures map to an owner: “Bringesh’s accounting import test failed” is actionable.

**What we are not doing in v1**

- 100% router coverage (150+ routers).
- Real MSSQL in CI (use mocks; optional `@pytest.mark.integration` for local/DB env).
- Assigning David domain tests on top of Phase 2 import cleanup.

---

## Prerequisites

Land tests **after** David’s `task/reorg-import-cleanup` merges (flat imports gone, shims deleted). Tests written against shims will need rewrites.

---

## Git workflow — branches & merge targets

**Repo root:** `oatmealfarmnetworkbackend/` (where `.git` lives)

**Rule:** All test work branches off **`epic/backend-reorg`**. Every test PR merges into **`epic/backend-reorg`** — never directly into `main`.

**Final ship:** After all test PRs are on epic and `pytest` is green → one PR **`epic/backend-reorg` → `main`** (merge commit, **not** squash).

```
main  ←────────────────────────────────────────────  (final PR #7, team)
  ↑
epic/backend-reorg  ←── all test PRs merge here (#1–#6)
  ↑
task/reorg-import-cleanup          (David — must land first)
task/reorg-test-infra              (David — test harness, merge before domain tests)
task/reorg-tests-scripts           (Vidyanand)
task/reorg-tests-services          (Sankeerth)
task/reorg-tests-models-core       (Bringesh)
task/reorg-tests-models-ag         (Navdeep)
task/reorg-tests-models-web        (Guia)
```

### Daily sync (everyone — run before starting work)

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git merge main                    # keep epic current with main
```

### Suggested merge order

| Order | Developer | Branch | PR target | Notes |
|-------|-----------|--------|-----------|-------|
| 0 | David | `task/reorg-import-cleanup` | → `epic/backend-reorg` | **Blocker** — Phase 2 import cleanup must land before tests |
| 1 | David | `task/reorg-test-infra` | → `epic/backend-reorg` | `pytest.ini`, `conftest.py`, smoke tests, CI — **others wait for this** |
| 2 | Vidyanand | `task/reorg-tests-scripts` | → `epic/backend-reorg` | Can run in parallel with rows 3–6 after row 1 merges |
| 3 | Sankeerth | `task/reorg-tests-services` | → `epic/backend-reorg` | Parallel |
| 4 | Bringesh | `task/reorg-tests-models-core` | → `epic/backend-reorg` | Parallel |
| 5 | Navdeep | `task/reorg-tests-models-ag` | → `epic/backend-reorg` | Parallel |
| 6 | Guia | `task/reorg-tests-models-web` | → `epic/backend-reorg` | Parallel |
| 7 | Team | — | `epic/backend-reorg` → `main` | After full `pytest` green on epic |

### If your branch falls behind epic while a PR is open

```bash
git checkout <your-branch>
git fetch origin
git merge origin/epic/backend-reorg    # merge, don't rebase — epic is shared
# resolve conflicts, then:
git push
```

### Branch summary

| Developer | Name | Create branch | Merge PR into | Files you add |
|-----------|------|---------------|---------------|---------------|
| Dev 2 | David | `task/reorg-import-cleanup` then `task/reorg-test-infra` | `epic/backend-reorg` | import cleanup + `pytest.ini`, `tests/conftest.py`, `tests/test_smoke.py`, `tests/test_health.py`, CI |
| Dev 1 | Vidyanand | `task/reorg-tests-scripts` | `epic/backend-reorg` | `tests/test_scripts.py` |
| Dev 3 | Sankeerth | `task/reorg-tests-services` | `epic/backend-reorg` | `tests/test_services.py` |
| Dev 4A | Bringesh | `task/reorg-tests-models-core` | `epic/backend-reorg` | `tests/test_models_core.py` |
| Dev 4B | Navdeep | `task/reorg-tests-models-ag` | `epic/backend-reorg` | `tests/test_models_ag.py` |
| Dev 4C | Guia | `task/reorg-tests-models-web` | `epic/backend-reorg` | `tests/test_models_web.py` |

---

### Per-developer git commands

#### David (Dev 2) — Phase 2 import cleanup (do this first)

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git merge main
git checkout -b task/reorg-import-cleanup

# ... rewrite flat imports, delete root shims, verify boot ...

git add -A
git commit -m "refactor: Phase 2 import cleanup — app.* imports, delete shims"
git push -u origin task/reorg-import-cleanup
# GitHub PR:  task/reorg-import-cleanup  →  epic/backend-reorg
# Merge this PR before anyone starts test branches.
```

#### David (Dev 2) — test infrastructure (do this second)

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-test-infra

# ... add pytest.ini, tests/conftest.py, tests/test_smoke.py, tests/test_health.py ...
# ... update .github/workflows/smoke-backend.yml ...

git add pytest.ini tests/ .github/workflows/smoke-backend.yml
git commit -m "test: add pytest infra, smoke tests, and CI gate"
git push -u origin task/reorg-test-infra
# GitHub PR:  task/reorg-test-infra  →  epic/backend-reorg
# Merge this PR before domain test branches (Vidyanand, Sankeerth, Bringesh, Navdeep, Guia).
```

#### Vidyanand (Dev 1) — scripts tests

**Start after:** `task/reorg-test-infra` is merged into `epic/backend-reorg`.

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-tests-scripts

# ... add tests/test_scripts.py ...

git add tests/test_scripts.py
git commit -m "test: add scripts import and repo hygiene tests"
git push -u origin task/reorg-tests-scripts
# GitHub PR:  task/reorg-tests-scripts  →  epic/backend-reorg
```

#### Sankeerth (Dev 3) — services & utils tests

**Start after:** `task/reorg-test-infra` is merged into `epic/backend-reorg`.

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-tests-services

# ... add tests/test_services.py ...

git add tests/test_services.py
git commit -m "test: add services and utils import tests"
git push -u origin task/reorg-tests-services
# GitHub PR:  task/reorg-tests-services  →  epic/backend-reorg
```

#### Bringesh (4A) — core models tests

**Start after:** `task/reorg-test-infra` is merged into `epic/backend-reorg`.

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-tests-models-core

# ... add tests/test_models_core.py ...

git add tests/test_models_core.py
git commit -m "test: add core models (users, accounting, Pricing) tests"
git push -u origin task/reorg-tests-models-core
# GitHub PR:  task/reorg-tests-models-core  →  epic/backend-reorg
```

#### Navdeep (4B) — ag / livestock / events models tests

**Start after:** `task/reorg-test-infra` is merged into `epic/backend-reorg`.

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-tests-models-ag

# ... add tests/test_models_ag.py ...

git add tests/test_models_ag.py
git commit -m "test: add ag, livestock, and events model tests"
git push -u origin task/reorg-tests-models-ag
# GitHub PR:  task/reorg-tests-models-ag  →  epic/backend-reorg
```

#### Guia (4C) — web models tests

**Start after:** `task/reorg-test-infra` is merged into `epic/backend-reorg`.

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b task/reorg-tests-models-web

# ... add tests/test_models_web.py ...

git add tests/test_models_web.py
git commit -m "test: add web models and website router tests"
git push -u origin task/reorg-tests-models-web
# GitHub PR:  task/reorg-tests-models-web  →  epic/backend-reorg
```

#### Team — final merge to main (after all above PRs are on epic)

```bash
cd oatmealfarmnetworkbackend/
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git merge main                         # final sync with main

pip install -r requirements.txt
pytest                                 # must pass

git push origin epic/backend-reorg
# GitHub PR:  epic/backend-reorg  →  main
# Use merge commit (NOT squash).
```

---

## Shared rules (everyone)

1. **Do not duplicate `conftest.py`** — use David’s fixture; add helpers only if agreed in PR review.
2. **Default tests use a mocked `get_db`** — no real database in CI.
3. **Import paths use `app.*`** — e.g. `from app.models import People`, not `import models`.
4. **Keep PRs small** — target 1–3 test files, ~50–150 lines each.
5. **Done when per dev:** import test for your slice + at least one HTTP test (mocked DB) OR one structural test (scripts).
6. **Optional integration tests** — mark with `@pytest.mark.integration` and skip when `DB_SERVER` is unset.

---

## David (Dev 2) — shared infrastructure

**Branches:** `task/reorg-import-cleanup` (first) → `task/reorg-test-infra` (second)  
**Merge both into:** `epic/backend-reorg`  
**Git commands:** [David — Phase 2 import cleanup](#david-dev-2--phase-2-import-cleanup-do-this-first) · [David — test infrastructure](#david-dev-2--test-infrastructure-do-this-second)

`task/reorg-test-infra` — **merge before domain test PRs.**

### Deliverables

```
pytest.ini
tests/
├── conftest.py          # TestClient + get_db override
├── test_smoke.py        # import app.main, import app.models
└── test_health.py       # GET /health, GET /openapi.json
```

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

### `tests/test_smoke.py` (sketch)

```python
def test_import_main_app():
    import app.main  # noqa: F401


def test_import_core_models():
    from app.models import People, Invoice
    assert People.__tablename__ == "People"
```

### `tests/test_health.py` (sketch)

```python
def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

### CI — extend `.github/workflows/smoke-backend.yml`

Replace (or supplement) the import-only step:

```yaml
- name: Run pytest smoke suite
  run: pytest tests/test_smoke.py tests/test_health.py
```

Later, when domain tests land:

```yaml
  run: pytest
```

### Boot gate (manual, before epic → main)

```bash
pip install -r requirements.txt
pytest
python -c "import app.main"
uvicorn app.main:app --port 8080
uvicorn server_all:app --port 8000
docker build .
```

### Done when

- `pytest tests/test_smoke.py tests/test_health.py` passes locally and in CI.
- Other developers can add files under `tests/` without editing `conftest.py`.

---

## Vidyanand (Dev 1) — scripts & repo hygiene

**Branch:** `task/reorg-tests-scripts`  
**Merge PR into:** `epic/backend-reorg`  
**Start after:** `task/reorg-test-infra` merged  
**Git commands:** [Vidyanand — scripts tests](#vidyanand-dev-1--scripts-tests)

**Scope:** Moved seeds, migrations, and import hygiene under `scripts/`.

### Tests to write (`tests/test_scripts.py`)

- Sample moved scripts import `app.database` (not flat `from database import`).
- No `from models import` under `scripts/` or `scrapers/`.
- Structural: no loose `seed_*.py`, `migrate_*.py`, or `*.sql` at repo root (path glob / `pathlib` check).

### Example

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_no_loose_root_seeds_or_migrations():
    assert list(ROOT.glob("seed_*.py")) == []
    assert list(ROOT.glob("migrate_*.py")) == []
    assert list(ROOT.glob("*.sql")) == []


def test_backfill_script_imports_app_database():
    source = (ROOT / "scripts" / "backfill_field_size_from_boundary.py").read_text()
    assert "from app.database import" in source
    assert "from database import" not in source
```

### Done when

- `tests/test_scripts.py` passes in CI.
- At least two moved scripts verified for correct `app.*` imports.

---

## Sankeerth (Dev 3) — services & utils

**Branch:** `task/reorg-tests-services`  
**Merge PR into:** `epic/backend-reorg`  
**Start after:** `task/reorg-test-infra` merged  
**Git commands:** [Sankeerth — services tests](#sankeerth-dev-3--services--utils-tests)

**Scope:** `app/services/*`, `app/utils/*`, and routers that import them.

### Tests to write (`tests/test_services.py`)

**Import tests** — each module loads without root shims:

- `app.services.marketplace_stripe`
- `app.services.marketplace_catalog`
- `app.services.event_emails`
- `app.services.meeting_emails`
- `app.services.image_service`
- `app.utils.page_templates`
- `app.utils.geo_utils`

**HTTP tests (mocked `get_db`)** — one per area:

- `GET /health` already covered by David; pick one service-backed route, e.g. lazy import path in `meetings` or `marketplace` that uses `app.services.*`.

### Routers to spot-check (any one mocked test each)

- `app/routers/marketplace.py`
- `app/routers/stripe_payments.py`
- `app/routers/meetings.py`
- `app/routers/website_builder.py`
- One `event_*.py` router (e.g. `event_simple.py`)

### Example import test

```python
def test_marketplace_stripe_imports():
    from app.services import marketplace_stripe
    assert hasattr(marketplace_stripe, "stripe_router")
```

### Done when

- All 7 service/util modules above import cleanly.
- At least one mocked HTTP test hits a route that uses a moved service.

---

## Bringesh (4A) — core models (users + accounting)

**Branch:** `task/reorg-tests-models-core`  
**Merge PR into:** `epic/backend-reorg`  
**Start after:** `task/reorg-test-infra` merged  
**Git commands:** [Bringesh — core models tests](#bringesh-4a--core-models-tests)

**Scope:** `app/models/users.py`, `app/models/accounting.py`, `Pricing` in `livestock.py`.

### Tests to write (`tests/test_models_core.py`)

**Model import tests:**

```python
from app.models import (
    People, Business, Address, BusinessAccess,
    Account, Invoice, JournalEntry, Pricing,
)


def test_core_model_tables():
    assert People.__tablename__ == "People"
    assert Invoice.__tablename__ == "Invoice"
    assert Pricing.__tablename__ == "Pricing"
```

**HTTP test (mocked DB):** `GET /auth/site-settings` — returns defaults when no `SiteSettings` row (see router in `app/routers/auth.py`).

### Done when

- Core user + accounting models import via `from app.models import ...`.
- `Pricing` resolves from `livestock` through `app/models/__init__.py`.
- One mocked router test for an accounting- or auth-related endpoint.

---

## Navdeep (4B) — ag / livestock / events models

**Branch:** `task/reorg-tests-models-ag`  
**Merge PR into:** `epic/backend-reorg`  
**Start after:** `task/reorg-test-infra` merged  
**Git commands:** [Navdeep — ag models tests](#navdeep-4b--ag--livestock--events-models-tests)

**Scope:** `app/models/livestock.py`, `precision_ag.py`, `crops.py`, `events.py`.

### Tests to write (`tests/test_models_ag.py`)

**Model import tests:**

```python
from app.models import (
    Animal, Field, Produce, Event, Association,
)


def test_ag_model_tables():
    assert Animal.__tablename__ == "Animal"
    assert Field.__tablename__ == "Field"
    assert Event.__tablename__ == "Event"
```

**Base import sanity** — all four model files use `from app.database import Base` (static read or import).

**HTTP test (mocked DB):** one router from ag/livestock slice, e.g. `livestock` or `events` — assert non-500 response or expected 401 without auth.

### Done when

- All 27 ag/event model classes import via `app.models`.
- Four model files use `app.database.Base`.
- One mocked HTTP test for an ag/livestock/events router.

---

## Guia (4C) — web models

**Branch:** `task/reorg-tests-models-web`  
**Merge PR into:** `epic/backend-reorg`  
**Start after:** `task/reorg-test-infra` merged  
**Git commands:** [Guia — web models tests](#guia-4c--web-models-tests)

**Scope:** `app/models/web.py`, website/blog routers.

### Tests to write (`tests/test_models_web.py`)

**Model import tests:**

```python
from app.models import (
    BusinessWebsite,
    BusinessWebPage,
    SiteSettings,
    BusinessBlogPost,
)


def test_web_model_tables():
    assert BusinessWebsite.__tablename__ == "BusinessWebsite"
    assert SiteSettings.__tablename__ == "SiteSettings"
```

**Structural:** root `models.py` has no `class X(Base):` definitions (shim only).

**HTTP test (mocked DB):** one route from `blog` or `website_builder` — non-500 with mocked session.

### Done when

- All six web models import from `app.models`.
- Root `models.py` is shim-only (no duplicate ORM classes).
- One mocked HTTP test for `blog` or `website_builder`.

---

## Optional integration tests (any developer, local only)

Mark tests that need a real `.env` / MSSQL:

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
    assert response.json()["db"] == "connected"
```

Run locally:

```bash
pytest -m integration
```

Do **not** enable integration tests in default CI unless GitHub secrets provide DB access.

---

## Pre-merge checklist (epic → main)

| Check | Owner |
|-------|-------|
| David Phase 2 import cleanup merged | David |
| `task/reorg-test-infra` merged | David |
| All five domain test PRs merged | Vidyanand, Sankeerth, Bringesh, Navdeep, Guia |
| `pytest` green on epic | Team |
| `python -c "import app.main"` | David |
| `uvicorn app.main:app` + `server_all.py` start | David |
| `docker build` + container boot | David |
| Smoke CI passes on PR to `main` | Team |
| Final merge commit (not squash) `epic/backend-reorg → main` | Team |

---

## Quick commands

```bash
# From repo root: oatmealfarmnetworkbackend/

pip install -r requirements.txt
pytest                          # full suite (after all PRs land)
pytest tests/test_smoke.py      # fastest gate
pytest -m "not integration"     # skip DB tests
pytest -v --tb=short            # verbose failures
```

---

*Created for post-reorg test rollout. Update this file as test PRs merge.*
