# Backend Reorg — Cleanup & Remaining Work

> **Companion to:** `Tasks.md`  
> **Integration branch:** `epic/backend-reorg`  
> **Cleanup branches:** see [Cleanup branches & git workflow](#cleanup-branches--git-workflow)  
> **Purpose:** Per-developer record of what is **done** vs what still needs doing before the reorg ships to `main`.

All Phase 1 task branches have been merged into `epic/backend-reorg` (PRs #27–#36). The structural moves are largely in place. What remains is **model deduplication**, **import cleanup (Phase 2)**, and a handful of loose ends.

---

## Overall status

| Developer | Name | Phase 1 branch (merged) | Cleanup branch (use this) | Cleanup remaining |
|-----------|------|-------------------------|----------------------------|-------------------|
| Dev 1 | Sai Ram | `task/reorg-scripts-gitignore` | `task/reorg-scripts-cleanup` | Script imports + root `.sql` moves |
| Dev 2 | David | `task/reorg-skeleton-and-ci`, `task/reorg-core-app` | `task/reorg-import-cleanup` | Phase 2 lead — shims, imports, boot gate |
| Dev 3 | Sankeerth | `task/reorg-services-utils` | `task/reorg-services-imports` | Router imports for moved services/utils |
| Dev 4A | Bringesh | `task/reorg-models-core` | `task/reorg-models-core-cleanup` | `models.py` dedup + `Pricing` |
| Dev 4B | Navdeep | `task/reorg-models-ag-events` | `task/reorg-models-ag-cleanup` | `app.database` import in 4 model files |
| Dev 4C | Guia | `task/reorg-models-web` | `task/reorg-models-web-cleanup` | Remove 6 web duplicates from `models.py` |

**Not started:** most cleanup branches above; final PR `epic/backend-reorg → main`.

> **Rule:** Phase 1 task branches are **merged — do not push new work to them.** Always cut a **new cleanup branch** from latest `epic/backend-reorg` and open a fresh PR into epic.

---

## Cleanup branches & git workflow

All cleanup work branches off **`epic/backend-reorg`**. Every PR targets **`epic/backend-reorg`** (not `main`).

### Daily sync (everyone — run before starting work)

```bash
cd oatmealfarmnetworkbackend/          # repo root (where .git lives)
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git merge main                         # keep epic current with main; resolve small conflicts early
```

### Start your cleanup branch

Replace `<your-cleanup-branch>` with your row from the table above:

```bash
git checkout epic/backend-reorg
git pull origin epic/backend-reorg
git checkout -b <your-cleanup-branch>
# ... make changes ...
git add -A
git commit -m "describe your cleanup change"
git push -u origin <your-cleanup-branch>
# Open PR on GitHub:  <your-cleanup-branch>  →  epic/backend-reorg
```

### Suggested merge order (reduces `models.py` conflicts)

| Order | Developer | Cleanup branch | Why this order |
|-------|-----------|----------------|----------------|
| 1 | Guia (4C) | `task/reorg-models-web-cleanup` | Removes 6 web duplicates from `models.py` first |
| 2 | Bringesh (4A) | `task/reorg-models-core-cleanup` | Removes 5 user duplicates + `Pricing`; `models.py` → one-line shim |
| 3 | Navdeep (4B) | `task/reorg-models-ag-cleanup` | 4 files under `app/models/` only — no `models.py` |
| 4 | Sai Ram (Dev 1) | `task/reorg-scripts-cleanup` | Independent — `scripts/` + `data/` |
| 5 | Sankeerth (Dev 3) | `task/reorg-services-imports` | Router/service import rewrites |
| 6 | David (Dev 2) | `task/reorg-import-cleanup` | Integration pass — delete shims, remaining flat imports, boot gate |
| 7 | Team | — | PR `epic/backend-reorg` → `main` (merge commit, **not** squash) |

### Per-developer quick start

```bash
# Dev 1 — Sai Ram
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git checkout -b task/reorg-scripts-cleanup

# Dev 2 — David (start after steps 1–5 above land on epic)
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git merge main
git checkout -b task/reorg-import-cleanup

# Dev 3 — Sankeerth
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git checkout -b task/reorg-services-imports

# Dev 4A — Bringesh (wait for 4C's models.py PR to merge first)
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git checkout -b task/reorg-models-core-cleanup

# Dev 4B — Navdeep
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git checkout -b task/reorg-models-ag-cleanup

# Dev 4C — Guia (go first — owns web duplicates in models.py)
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git checkout -b task/reorg-models-web-cleanup
```

### If your branch falls behind epic while a PR is open

```bash
git checkout <your-cleanup-branch>
git fetch origin
git merge origin/epic/backend-reorg    # merge, don't rebase — epic is shared
# resolve conflicts, then:
git push
```

---

## Developer 1 — Sai Ram

**Goal:** Git cleanup & script consolidation.

**Phase 1 branch (merged):** `task/reorg-scripts-gitignore`  
**Cleanup branch:** `task/reorg-scripts-cleanup`

```bash
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git checkout -b task/reorg-scripts-cleanup
# ... work ...
git push -u origin task/reorg-scripts-cleanup
# PR: task/reorg-scripts-cleanup → epic/backend-reorg
```

### Done

- [x] Added `*.err` and `*.out` to `.gitignore` (lines 107–108).
- [x] Created `scripts/migrations/`, `scripts/seeds/`, `db/migrations/`.
- [x] Moved all 5 root `migrate_*.py` files → `scripts/migrations/`:
  - `migrate_animal_photos.py`
  - `migrate_image_styling.py`
  - `migrate_screen_page_bg.py`
  - `migrate_typography_italic_px.py`
  - `migrate_website_columns.py`
- [x] Moved all root `seed_*.py` + `upload_local_animal_photos.py` → `scripts/seeds/` (25 seed scripts).
- [x] Moved 6 seeds already in `scripts/` → `scripts/seeds/`:
  - `seed_full_15665.py`, `seed_carbon_15665.py`, `seed_alerts_15665.py`
  - `seed_analyses_15665.py`, `seed_activity_journal_15665.py`, `seed_aggregator.py`
- [x] Moved `check_cc_tables.py` and `generate_knowledgebase_images.py` → `scripts/`.
- [x] Moved all 14 root `migrations/*.sql` DDL files → `db/migrations/`.
- [x] Most moved seeds/migrations already updated to `from app.database import ...`.

**Merged:** PR #36 (`task/reorg-scripts-gitignore` → `epic/backend-reorg`).

### Still to do

1. **Fix two scripts still using flat `from database import`** (root `database.py` no longer exists — these may be broken):
   - `scripts/import_sfproducts.py` — change to `from app.database import engine`
   - `scripts/backfill_field_size_from_boundary.py` — change to `from app.database import SessionLocal`

2. **Relocate 3 root `.sql` data dumps** (Tasks.md “done when” says no loose `*.sql` at repo root):
   - `aggregator_sales_test_data_15671.sql`
   - `esci_test_data_15671.sql`
   - `seed_oatmeal_ai.sql`  
   Suggested destination: `data/` (needs team decision — see Unassigned section). Use `git mv`.

3. **Phase 2 support (optional / coordinate with David):** After Dev 2's import cleanup, scan `scripts/` and `scrapers/` for any remaining flat imports (`from database import`, `from models import`) and fix them.

### Done when (your section)

- Repo root has no loose `seed_*`, `migrate_*`, or `*.sql` files.
- All scripts under `scripts/` import from `app.*`, not flat root modules.

---

## Developer 2 — David

**Goal:** Core `app/` package, launchers, Phase 0 skeleton, Phase 2 integration lead.

**Phase 1 branches (merged):** `task/reorg-skeleton-and-ci`, `task/reorg-core-app`  
**Cleanup / Phase 2 branch:** `task/reorg-import-cleanup` — start **after** model + script cleanup PRs merge into epic.

```bash
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git merge main
git checkout -b task/reorg-import-cleanup
# ... work ...
git push -u origin task/reorg-import-cleanup
# PR: task/reorg-import-cleanup → epic/backend-reorg
```

### Done

- [x] **Phase 0 skeleton:** Created `app/` with subfolders `core/`, `models/`, `routers/`, `services/`, `utils/`, each with `__init__.py`.
- [x] **Phase 0:** Empty `app/models/__init__.py` committed (unblocks 4A/4B/4C).
- [x] Moved `main.py`, `database.py`, `dependencies.py` → `app/`.
- [x] Moved `auth.py`, `jwt_auth.py` → `app/core/`.
- [x] Moved entire `routers/` tree → `app/routers/`.
- [x] Updated `Dockerfile` CMD to `uvicorn app.main:app`.
- [x] Updated `server_all.py` to load `app/main.py` via explicit file-path import.
- [x] Removed CropMonitor runtime integration from `server_all.py` (no more `CropMonitoringBackend/` phase).
- [x] PR #35 (`task/reorg-core-app-phase-II`): deleted root `database.py`, `auth.py`, `jwt_auth.py`.

**Merged:** PRs #27 (skeleton), #31/#34 (core-app), #35 (phase-II).

### Still to do

#### Phase 0 (unfinished)

1. **Add smoke CI workflow** — Tasks.md specifies a tiny workflow:
   ```yaml
   # .github/workflows/smoke-backend.yml (suggested name)
   # pip install -r requirements.txt
   # python -c "import app.main"
   ```
   Currently only `.github/workflows/deploy-saige.yml` exists (path-scoped to `saige/**`).

#### Phase 1 polish

2. **Update `server_all.py` docstring** — lines 1–7 still mention CropMonitor (`/cm/*`). Remove stale references; doc should reflect main backend + Saige only.

3. **Revisit premature shim deletion** — PR #35 removed root `database.py`, `auth.py`, `jwt_auth.py` before Phase 2 import rewrite. ~120+ files under `app/` still use flat imports (`from database import`, `from models import`, `from auth import`). Either:
   - Restore temporary shims until Phase 2 completes, **or**
   - Proceed immediately to Phase 2 import rewrite (preferred if app boots via `sys.path` tricks).

#### Phase 2 — `task/reorg-import-cleanup` (lead — **not started**)

See **Cleanup branches & git workflow** above for full git commands. Quick start:

```bash
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git merge main
git checkout -b task/reorg-import-cleanup
```

**Step 1 — Delete remaining shim files at repo root:**

| Shim file | Forwards to |
|-----------|-------------|
| `models.py` | Replace with one-liner after 4A/4C dedup (see below) |
| `external_apis.py` | `app.services.external_apis` |
| `image_service.py` | `app.services.image_service` |
| `marketplace_accounting.py` | `app.services.marketplace_accounting` |
| `marketplace_catalog.py` | `app.services.marketplace_catalog` |
| `marketplace_stripe.py` | `app.services.marketplace_stripe` |
| `marketplace_emails.py` | `app.services.marketplace_emails` |
| `herd_health_accounting.py` | `app.services.herd_health_accounting` |
| `event_emails.py` | `app.services.event_emails` |
| `meeting_emails.py` | `app.services.meeting_emails` |
| `geo_utils.py` | `app.utils.geo_utils` |
| `gee_helper.py` | `app.utils.gee_helper` |
| `page_templates.py` | `app.utils.page_templates` |

**Step 2 — Rewrite flat imports → `app.*` across:**

- `app/` (all routers, services, models, `main.py`) — ~120+ files
- `scripts/` (Dev 1's remaining 2 files + any stragglers)
- `scrapers/`

Common replacements:

```python
from database import X     →  from app.database import X
from models import X       →  from app.models import X
from auth import X         →  from app.core.auth import X
from jwt_auth import X     →  from app.core.jwt_auth import X
import page_templates      →  from app.utils import page_templates
from marketplace_stripe  →  from app.services import marketplace_stripe
```

**Step 3 — Verify deploy configs:**

- `Dockerfile` — already `uvicorn app.main:app` ✓
- `cloudbuild.yaml` — runs `docker build .` (should work if Dockerfile is correct)
- Run locally: `docker build .` + `uvicorn app.main:app` + `python server_all.py`

**Step 4 — Boot gate:**

```bash
python -c "import app.main"
uvicorn app.main:app --port 8080
python server_all.py
```

**Step 5 — Open PR:** `task/reorg-import-cleanup` → `epic/backend-reorg`

#### Final PR

After Phase 2 merges into epic and everything boots:

- Open PR: `epic/backend-reorg` → `main`
- Use a **merge commit** (do NOT squash — preserves `git mv` history).

### Done when (your section)

- Smoke CI passes on every PR.
- `uvicorn app.main:app` and `server_all.py` both start clean.
- No shim files remain; nothing imports flat root paths.
- Phase 2 PR merged; final epic → main PR opened.

---

## Developer 3 — Sankeerth

**Goal:** Move business logic & helpers into `app/services/` and `app/utils/`.

**Phase 1 branch (merged):** `task/reorg-services-utils`  
**Cleanup branch:** `task/reorg-services-imports`

```bash
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git checkout -b task/reorg-services-imports
# ... work ...
git push -u origin task/reorg-services-imports
# PR: task/reorg-services-imports → epic/backend-reorg
```

### Done

- [x] Moved 9 files → `app/services/`:
  - `external_apis.py`, `image_service.py`, `marketplace_accounting.py`
  - `marketplace_catalog.py`, `marketplace_stripe.py`, `marketplace_emails.py`
  - `herd_health_accounting.py`, `event_emails.py`, `meeting_emails.py`
- [x] Moved 3 files → `app/utils/`:
  - `geo_utils.py`, `gee_helper.py`, `page_templates.py`
- [x] Added 12 root shim files (one-liner `from app.services.X import *` or `from app.utils.X import *`).

**Merged:** PR #33 (`task/reorg-services-utils` → `epic/backend-reorg`).

### Still to do (Phase 2 — coordinate with David)

After David starts `task/reorg-import-cleanup`, update importers in these routers/files to use `app.*` directly (then shims get deleted):

| Router / file | Current import style | Target |
|---------------|---------------------|--------|
| `app/routers/marketplace.py` | `from database import ...` + service shims | `from app.database import ...`, `from app.services.marketplace_catalog import ...` |
| `app/routers/stripe_payments.py` | flat imports | `from app.services.marketplace_stripe import ...` |
| `app/routers/website_builder.py` | `import page_templates` (lazy) | `from app.utils import page_templates` |
| `app/routers/website_ai.py` | flat imports | `from app.utils.page_templates import ...` |
| `app/routers/meetings.py` | flat imports | `from app.services.meeting_emails import ...` |
| All `app/routers/event_*.py` | flat imports | `from app.services.event_emails import ...` |
| `app/services/marketplace_stripe.py` | `from database import get_db` | `from app.database import get_db` |
| `app/services/marketplace_catalog.py` | `from database import get_db` | `from app.database import get_db` |

**Full list of affected routers** (any file importing your moved modules via root shim or flat path): marketplace, stripe_payments, website_builder, website_ai, meetings, and all 27 `event_*` routers.

### Done when (your section)

- All 12 files live under `app/services/` or `app/utils/` ✓ (already true).
- Routers import via `app.services.*` / `app.utils.*` (not root shims).
- Root shim files deleted.
- App boots with services imported via `app.*`.

---

## Developer 4A — Bringesh

**Goal:** Extract users + accounting models into `app/models/`.

**Phase 1 branch (merged):** `task/reorg-models-core`  
**Cleanup branch:** `task/reorg-models-core-cleanup` — start **after** Guia's `task/reorg-models-web-cleanup` merges (both edit `models.py`).

```bash
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git checkout -b task/reorg-models-core-cleanup
# ... work ...
git push -u origin task/reorg-models-core-cleanup
# PR: task/reorg-models-core-cleanup → epic/backend-reorg
```

### Done

- [x] Created `app/models/users.py` with 8 classes:
  `People`, `Business`, `Address`, `BusinessAccess`, `BusinessTypeLookup`, `Country`, `StateProvince`, `Websites`
- [x] Created `app/models/accounting.py` with 17 classes:
  `AccountType`, `Account`, `JournalEntry`, `JournalEntryLine`, `AccountingCustomer`, `AccountingVendor`, `Item`, `Invoice`, `InvoiceLine`, `Payment`, `PaymentApplication`, `Bill`, `BillLine`, `Expense`, `ExpenseLine`, `FiscalYear`, `FiscalPeriod`
- [x] Created `app/models/marketplace.py` as placeholder (comment only).
- [x] Added to `app/models/__init__.py`: `from .users import *`, `from .accounting import *`
- [x] `users.py` and `accounting.py` use `from app.database import Base` (correct convention).

**Merged:** PR #29 (`task/reorg-models-core` → `epic/backend-reorg`).

### Still to do

1. **Clean up root `models.py`** — it is NOT a pure shim. It still contains **12 duplicate `class X(Base):` definitions** that should be removed:

   **Your duplicates (move already done — just delete from `models.py`):**
   - `BusinessAccess`, `BusinessTypeLookup`, `Country`, `StateProvince`, `Websites`

   **4C's duplicates (coordinate with Guia — delete after confirming `app/models/web.py` is canonical):**
   - `BusinessWebsite`, `BusinessWebPage`, `BusinessWebBlock`, `WebsiteCustomDomain`, `SiteSettings`, `BusinessBlogPost`

   **Unassigned class still in `models.py`:**
   - `Pricing` — decide home (see step 2).

   After cleanup, `models.py` should be **only**:

   ```python
   from app.models import *  # noqa: F401,F403
   ```

   (Phase 2 will delete this shim entirely once all importers use `from app.models import ...`.)

2. **Decide `Pricing` model home** — currently the only real ORM class left unassigned:
   - Option A: move to `app/models/marketplace.py`
   - Option B: move to `app/models/users.py` (animal pricing tied to livestock)
   - After moving: add `from .marketplace import *` (or export from users) in `__init__.py`.

3. **Verify:** `python -c "from app.models import People, Invoice; print('ok')"`

### Done when (your section)

- `from app.models import People, Invoice` works ✓
- Root `models.py` has zero `class ... (Base):` definitions (shim only).
- `Pricing` assigned and moved out of root `models.py`.
- App boots.

---

## Developer 4B — Navdeep

**Goal:** Extract livestock, precision-ag, crop, and event models.

**Phase 1 branch (merged):** `task/reorg-models-ag-events`  
**Cleanup branch:** `task/reorg-models-ag-cleanup`

```bash
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git checkout -b task/reorg-models-ag-cleanup
# ... work ...
git push -u origin task/reorg-models-ag-cleanup
# PR: task/reorg-models-ag-cleanup → epic/backend-reorg
```

### Done

- [x] Created `app/models/livestock.py` — 13 classes:
  `Animal`, `AnimalRegistration`, `AnimalColor`, `Ancestor`, `AncestryPercent`, `Fiber`, `Award`, `SpeciesAvailable`, `SpeciesBreedLookup`, `SpeciesColorLookup`, `SpeciesRegistrationTypeLookup`, `SpeciesCategory`, `Photo`
- [x] Created `app/models/precision_ag.py` — 10 classes:
  `Field`, `FieldNote`, `FieldBiomassAnalysis`, `FieldMaturitySample`, `FieldHarvestTarget`, `FieldAssessmentReport`, `FieldScout`, `FieldSoilSample`, `FieldPrescription`, `FieldActivityLog`
- [x] Created `app/models/crops.py` — 2 classes: `Produce`, `CropRotationEntry`
- [x] Created `app/models/events.py` — 2 classes: `Event`, `Association`
- [x] Appended to `app/models/__init__.py`:
  `from .livestock import *`, `from .precision_ag import *`, `from .crops import *`, `from .events import *`
- [x] Removed all 27 classes from root `models.py` (no 4B duplicates remain there).

**Merged:** PR #30 (`task/reorg-models-ag-events` → `epic/backend-reorg`).

### Still to do

1. **Fix `Base` import in your 4 model files** — still using old flat import with a stale comment:

   Files:
   - `app/models/livestock.py`
   - `app/models/precision_ag.py`
   - `app/models/crops.py`
   - `app/models/events.py`

   Change:
   ```python
   from database import Base
   ```
   To:
   ```python
   from app.database import Base
   ```

   Remove the outdated comment about waiting for Dev 2's move (that move is done).

2. **Phase 2 support:** If any router still does `from models import Animal` etc., it will be fixed in David's import cleanup — no action needed unless you want to help rewrite imports in ag/livestock routers.

### Done when (your section)

- All 27 classes import via `from app.models import ...` ✓ (structure done).
- All 4 model files use `from app.database import Base`.
- App boots.

---

## Developer 4C — Guia

**Goal:** Extract 6 website-builder models.

**Phase 1 branch (merged):** `task/reorg-models-web`  
**Cleanup branch:** `task/reorg-models-web-cleanup` — **go first** (removes web duplicates from `models.py` before 4A).

```bash
git checkout epic/backend-reorg && git pull origin epic/backend-reorg
git checkout -b task/reorg-models-web-cleanup
# ... work ...
git push -u origin task/reorg-models-web-cleanup
# PR: task/reorg-models-web-cleanup → epic/backend-reorg
```

### Done

- [x] Created `app/models/web.py` with 6 classes:
  `BusinessWebsite`, `BusinessWebPage`, `BusinessWebBlock`, `WebsiteCustomDomain`, `SiteSettings`, `BusinessBlogPost`
- [x] Did NOT move `Websites` (correctly left in 4A's `users.py`).
- [x] Appended to `app/models/__init__.py`: `from .web import *`
- [x] `web.py` uses `from app.database import Base`.

**Merged:** PR #32 (`task/reorg-models-web` → `epic/backend-reorg`).

### Still to do

1. **Remove duplicate class definitions from root `models.py`** — all 6 web classes are still defined there (lines ~118–316), duplicating `app/models/web.py`:
   - `BusinessWebsite`
   - `BusinessWebPage`
   - `BusinessWebBlock`
   - `WebsiteCustomDomain`
   - `SiteSettings`
   - `BusinessBlogPost`

   Delete these class bodies from `models.py`. Coordinate with Bringesh (4A) who owns the `models.py` cleanup PR.

2. **Verify:** `python -c "from app.models import BusinessWebsite, SiteSettings; print('ok')"`

3. **Confirm** `app/routers/website_builder.py` and `app/routers/blog.py` can import web models (Phase 2 will fix their `from database` / `from models` flat imports).

### Done when (your section)

- `models.py` has **zero** remaining `class ... (Base):` definitions (only shim line remains).
- All 6 web models import only from `app.models.web`.
- App boots.

---

## Phase 2 — Integration checklist (David, all devs support)

Run only after 4C + 4A finish `models.py` dedup (branches `task/reorg-models-web-cleanup` and `task/reorg-models-core-cleanup`).

| # | Task | Owner | Cleanup branch | Status |
|---|------|-------|----------------|--------|
| 1 | Remove 6 web duplicates from `models.py` | 4C | `task/reorg-models-web-cleanup` | Not done |
| 2 | Remove 5 user duplicates + move `Pricing` + `models.py` → shim | 4A | `task/reorg-models-core-cleanup` | Not done |
| 3 | 4B model files use `app.database` | 4B | `task/reorg-models-ag-cleanup` | Not done |
| 4 | Dev 1 script import fixes (2 files) + root `.sql` moves | Dev 1 | `task/reorg-scripts-cleanup` | Not done |
| 5 | Rewrite service/utils imports in routers | Dev 3 | `task/reorg-services-imports` | Not done |
| 6 | Rewrite remaining flat imports in `app/` | Dev 2 (lead) | `task/reorg-import-cleanup` | Not done |
| 7 | Delete all root shims (12 service/utils + `models.py`) | Dev 2 | `task/reorg-import-cleanup` | Not done |
| 8 | Fix `scripts/` + `scrapers/` imports | Dev 1 + Dev 2 | scripts-cleanup + import-cleanup | Partial |
| 9 | Smoke CI workflow | Dev 2 | `task/reorg-import-cleanup` | May be done — verify on epic |
| 10 | `docker build` + boot locally | Dev 2 | `task/reorg-import-cleanup` | Not verified |
| 11 | PR cleanup branches → epic | All | (see table above) | Not started |
| 12 | PR `epic/backend-reorg` → `main` (merge commit) | Team | — | Not started |

See **Cleanup branches & git workflow** for merge order and per-developer `git checkout` commands.

---

## Unassigned / standup decisions (no owner yet)

| Item | Location | Suggested action |
|------|----------|-------------------|
| `Pricing` ORM class | root `models.py` | 4A decides: `marketplace.py` or `users.py` |
| 3 root `.sql` data dumps | repo root | Dev 1: `git mv` → `data/` (create folder) |
| `main.jsx` | repo root | Move to `src/` or delete |
| `saige/null` | `saige/null` | Delete (junk file) |
| `src/index.js` | `src/index.js` | Keep, deprecate, or document |
| `architecture.png` | unknown | Move to `docs/` if it exists |
| Smoke CI workflow | `.github/workflows/` | Dev 2 creates |

---

## Quick verification commands

```bash
# From repo root: oatmealfarmnetworkbackend/

# Check for loose root artifacts (Dev 1)
ls seed_*.py migrate_*.py *.sql 2>/dev/null

# Count duplicate model classes in root models.py (should be 0 before Phase 2)
rg "^class \w+\(Base\):" models.py

# Count flat imports still in app/ (should be 0 after Phase 2)
rg "from database import|from models import|from auth import" app/

# Boot check
python -c "import app.main"
uvicorn app.main:app --port 8080
```

---

*Last updated: cleanup branch names + git workflow added. Update this file as tasks close.*
