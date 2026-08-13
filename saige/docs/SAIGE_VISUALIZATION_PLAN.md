# Saige Visualization Implementation Plan

**Owners:** David (lead), Guia (frontend primitives)  
**Status:** Planning — no implementation until this document is followed  
**Repos:**
- Backend: `oatmealfarmnetworkbackend/saige/`
- Frontend: `oatmealfarmnetwork/src/`
- LOA (later): `livestock-of-america/src/`

---

## Table of contents

1. [Goal](#1-goal)
2. [Current state](#2-current-state)
3. [Architecture](#3-architecture)
4. [Visualization catalog](#4-visualization-catalog)
5. [Roles and working agreement](#5-roles-and-working-agreement)
6. [JSON contract](#6-json-contract)
7. [Shared rules](#7-shared-rules)
8. [Phase 0 — Contract](#8-phase-0--contract)
9. [Phase 1 — Tier 1 (in-chat)](#9-phase-1--tier-1-in-chat)
10. [Phase 2 — Farm-specific](#10-phase-2--farm-specific)
11. [Phase 3 — Advanced](#11-phase-3--advanced)
12. [Week-by-week schedule](#12-week-by-week-schedule)
13. [Dependency graph](#13-dependency-graph)
14. [QA checklist](#14-qa-checklist)
15. [Definition of done (Tier 1)](#15-definition-of-done-tier-1)
16. [Out of scope](#16-out-of-scope)

---

## 1. Goal

Saige is a farm AI. Answers that are numbers, series, inventories, alerts, or maps must render as **visual primitives in chat**, not as paragraphs of digits.

Saige must **not draw charts in prose**. It emits a typed visualization spec next to the spoken caption. The chat UI renders it — the same pattern as `[MAP_CMD]` (map fly-to) and HITL proposal cards (structured objects on a message).

---

## 2. Current state

| Layer | Reality |
|---|---|
| Chat contract | `/chat` and `/chat/stream` return `diagnosis`, `recommendations`, `citations`, `proposals`. No viz field. |
| History | Firestore `metadata` exists; viz specs can live there so reloads keep charts. |
| In-chat visuals | Only `[MAP_CMD: flyTo …]` (parsed in `SaigeWidget.jsx`) and HITL proposal cards. |
| Page chrome | `SaigeFieldsCard`, `FieldHealthWidget`, `MarketIntelligenceWidget` sit **beside** chat, not inside it. |
| Existing charts/maps | Precision Ag (`leaflet` + rasters), `CropAnalysisSummary.jsx`, `FarmKPIDashboard.jsx` — all **Recharts**. |
| Tool output | Irrigation `daily[]`, GDD `daily[]`, NDVI history, field activity, animals, weather, prices, alerts — but tools **stringify** that data for the LLM. |
| Clients | OFN `SaigePage.jsx` (`/saige`, uses `/chat` only), OFN `SaigeWidget.jsx` (stream then `/chat` fallback), LOA `SaigeWidget.jsx`. |

Specialists concatenate tool results as strings (`precision_ag_context += tool_result`). Tools must keep returning **text**. Viz payloads go through a side channel (see D3).

---

## 3. Architecture

```
Tool (text for LLM + viz_emit side channel)
    → mapper (deterministic, no LLM)
    → visualizations[] on /chat, SSE done, history metadata
    → VizRenderer in chat bubble
```

**LLM writes the caption only.** It never invents series, axes, or GeoJSON.

```
User: "Should I irrigate North 40?"
  → get_field_irrigation_tool
      → text: "Cumulative deficit 0.42 in…"
      → viz_emit(KPI + line_chart)
  → synthesizer: one-sentence caption
  → API: { diagnosis, visualizations: [...] }
  → ChatBubble: <p>caption</p> + <VizRenderer />
```

### 3.1 Why a side channel (not dict tool returns)

`graph/nodes.py` does `precision_ag_context += tool_result` in dozens of branches. Changing `@tool` return type to `dict` will break specialists.

**Do this instead:** tools still `return "\n".join(lines)`. Structured specs are pushed to a `ContextVar` list (`viz_emit` / `viz_take`).

### 3.2 Stream vs JSON

- Stream **text first** (existing `token` events).
- Attach `visualizations` only on SSE `done` so charts do not flicker mid-token.
- `SaigePage` uses `/chat` (not stream) today — both endpoints must carry the same field.

### 3.3 Maps and rasters

Chat specs carry **IDs only** (`field_id`, `analysis_id`, `layer: "NDVI"`). The client fetches GeoJSON/rasters from Crop Monitor the same way `PrecisionAgMaps.jsx` already does. Never put rasters on SSE.

---

## 4. Visualization catalog

### Tier 1 — Essential (ship first)

| Type | Example | Existing source | Notes |
|---|---|---|---|
| `kpi` | Soil moisture **28%** | Irrigation snapshot, latest NDVI, animal count | Easiest win. Number + unit + optional delta. |
| `line_chart` | Moisture / NDVI over 30 days | Irrigation `daily[]`, `get_field_history_tool`, GDD `daily[]` | Prefer NDVI + ET/precip first. Label proxies honestly. |
| `bar_chart` | Yield by field | `get_field_yield_forecast_tool`, `get_farm_benchmark_tool` | Say forecast vs actual. |
| `table` | Livestock inventory | `list_my_animals_detail_tool` | Cap 20 rows in UI; 50 in payload. |
| `alert_card` | Heat stress warning | `get_field_alerts_tool`, weather heat thresholds | Same urgency colors as `SaigeFieldsCard`. |
| `timeline` | Field activities | `get_field_activity_log_tool`, scouting | Spray / tillage / irrigation / harvest. |
| `progress` | Crop growth stage | `get_field_gdd_tool`, `get_field_maturity_tool` | Stage name + % to next milestone. |

### Tier 2 — Farm-specific

| Type / need | Source | Approach |
|---|---|---|
| Farm map | Field boundaries (Leaflet already) | Spec `{ field_ids }`. Compact map or existing `MAP_CMD`. |
| Field map | NDVI rasters (`PrecisionAgMaps`) | Spec `{ field_id, analysis_id, layer }`. Client fetches `/cm`. |
| Weather chart | `weather_service` (today only `format_for_llm`) | Expose daily temp/rain arrays from the same fetch. |
| Forecast chart | Same, `forecast_days` already parsed | Reuse `line_chart` with two series. Prefer no new type. |
| Livestock chart | Animals grouped by species/breed | Donut or `bar_chart`. |
| Price chart | `get_price_trends_tool`, `price_forecast_tool` | Historical + forecast band. |
| Monitoring chart | `get_field_analysis_tool` + history | Multi-series NDVI / EVI / SAVI. |
| Pest visualization | Scouting, pest detections, Farm KPI pest log | Photo thumb + confidence, or table. |

### Tier 3 — Advanced

| Need | Rule |
|---|---|
| Heatmap | Only if Crop Monitor has a grid. Else deep-link the raster map. |
| Geo heatmap | Only if pest/scout rows have lat/lon. Else pins on farm map. |
| Radar | Only with a real animal-health score vector. Do not fake axes. |
| Sankey | Needs resource-flow data. **Defer.** |
| Calendar | `planting_calendar_tool` + activity dates. Good first Tier-3 item. |
| Comparison dashboard | Two `line_chart`s + KPI row. Compose Tier 1. |
| Interactive farm dashboard | `SaigePage` chrome (`/precision-ag/dashboard` + widgets), not a chat bubble. |

---

## 5. Roles and working agreement

### David (lead) — all core work

Schema, mapper, tools, LangGraph, `/chat` + SSE, history metadata, Recharts, maps, LOA wiring, synthesizer prompt.

### Guia (fresher) — presentational React only

KPI, alert, table, progress, timeline, empty states, action buttons, i18n, playground, QA checklist.

**Guia does not:** Recharts, Leaflet, SSE, LangGraph, Python tools, `SaigeWidget` message parsing, LOA (until asked).

### Working rules

1. David writes the contract first — mock JSON the same day as D1.
2. Guia never waits on live Saige. She builds against mocks in `src/saige-viz/`.
3. David plugs Guia’s components in once `/chat` returns `visualizations[]`.
4. **One PR per task.** Guia PRs are frontend-only (`oatmealfarmnetwork/src/saige-viz/` + i18n).
5. Daily 15 min: David reviews Guia’s PR. Guia does not merge schema/tool changes.
6. Guia’s public API for every component:

```jsx
export default function KpiViz({ spec }) { /* spec.type, spec.title, spec.data, spec.actions */ }
```

If a prop name is wrong, David adapts the mapper. Guia does not chase backend changes.

### Palette (copy, do not invent)

From `SaigePage.jsx`:

| Token | Value |
|---|---|
| Green | `#3D6B34` |
| Green dark | `#2c4f25` |
| Light | `#f0f7ee` |
| Border | `#c7dfc2` |
| Body font | Montserrat |
| Heading font | Lora |

Copy patterns from `SaigeFieldsCard.jsx`, `CropAnalysisSummary.jsx`, and `FarmKPIDashboard.jsx`.

---

## 6. JSON contract

Every visualization:

```json
{
  "id": "viz_1",
  "type": "kpi",
  "title": "Soil moisture",
  "source_tool": "get_field_irrigation_tool",
  "data": { "value": 28, "unit": "%", "delta": -4, "hint": "drier than last week" },
  "actions": [{ "label": "Open field", "href": "/precision-ag/fields/12" }]
}
```

### `data` by type (Tier 1)

| `type` | `data` |
|---|---|
| `kpi` | `{ "value": 28, "unit": "%", "delta": -4, "hint": "vs last week" }` |
| `line_chart` | `{ "xKey": "date", "yKey": "value", "unit": "%", "series": [{ "date": "2026-07-01", "value": 32 }] }` |
| `bar_chart` | `{ "xKey": "field", "yKey": "yield", "unit": "bu/ac", "series": [{ "field": "North 40", "yield": 180 }] }` |
| `table` | `{ "columns": ["Name", "Sex", "DOB", "Status"], "rows": [["Bella", "F", "2022-03-01", "for-sale"]] }` |
| `alert_card` | `{ "severity": "high", "message": "Heat stress likely this afternoon", "field_name": "North 40" }` |
| `timeline` | `{ "items": [{ "date": "2026-08-01", "action": "Sprayed", "field": "North 40" }] }` |
| `progress` | `{ "label": "Flowering", "percent": 62, "hint": "next: grain fill" }` |

### Validation (drop the spec, keep the text)

- Unknown `type`
- `line_chart` / `bar_chart` with empty `series`
- `table` with no `rows`
- `kpi` with no `value`

### Caps

- Max **3** specs per turn on `SaigePage`
- Max **2** in the floating widget
- Series max **90** points
- Table max **50** rows in payload; UI shows **20** + “+N more”

---

## 7. Shared rules

**Do**

- Label proxies honestly (ET deficit is not soil moisture %; yield forecast is not harvested yield).
- Empty data → omit the viz, keep the caption (or Guia’s empty state if the spec is present but `data` is empty).
- TTS speaks the caption only, never the table.
- Same JWT + `business_id` scoping as tools.
- Deep-link to Precision Ag / Farm KPI for the rest: `actions: [{ "href": "/precision-ag/maps?field=12" }]`.

**Do not**

- Let Gemini emit Vega/Recharts JSON.
- Send GeoJSON or NDVI rasters through `/chat`.
- Add new chart libraries (`recharts` and `leaflet` are already in OFN `package.json`).
- Mix Guia PRs into Python / LangGraph files.
- Show viz for jokes, greetings, or how-to answers with no series.

**Intent (mapper in charge, not a second LLM call)**

- “How’s moisture / NDVI / yield / herd / weather / prices” → matching spec if data exists.
- How-to or diagnosis with no series → text only.
- Route from the tool that already ran (`get_field_irrigation_tool` → KPI + line).

---

## 8. Phase 0 — Contract

Guia starts G1 the hour D1 mocks exist.

### D1 — Visualization schema + mock JSON (David)

**Goal:** Typed catalog + a file Guia can paste.

**Create**

- `saige/schemas/visualizations.py`
- `saige/docs/viz_mocks.json`
- `saige/tests/test_visualizations.py`

**Edit**

- `saige/schemas/models.py` — add `visualizations: Optional[List[Dict[str, Any]]]` on `SaigeState`

**Steps**

1. Allowed types (Tier 1 only): `kpi | line_chart | bar_chart | table | alert_card | timeline | progress`
2. Pydantic `VisualizationSpec` with `id`, `type`, `title`, `source_tool`, `data`, `actions`
3. `validate_spec(raw) -> VisualizationSpec | None` (see [Validation](#validation-drop-the-spec-keep-the-text))
4. Write `viz_mocks.json` with **one example of each type** (shapes in [§6](#data-by-type-tier-1))
5. Tests (copy env setup from `saige/tests/test_hitl.py`): valid KPI parses; empty line series → `None`; unknown type → `None`

**Check:** `pytest saige/tests/test_visualizations.py -q`

**Hand to Guia the same day:** `viz_mocks.json` + “your components receive `spec` exactly like this.”

---

### D2 — Empty `visualizations[]` on the chat contract (David)

**Goal:** Clients can receive the field before tools emit anything.

**Edit**

- `saige/chat/service.py` — `_finalize_result` (success **and** interrupted)
- `saige/chat/service.py` — assistant `save_message` metadata (~line 286)
- `saige/chat/streaming.py` — already spreads `**result` on `done`; confirm the field is present

**Steps**

1. Add `"visualizations": final_values.get("visualizations") or []` to both result dicts.
2. Extend assistant metadata:

```python
metadata={
    "type": "advisory",
    "advisory_type": final_values.get("advisory_type"),
    "trace_id": trace_id,
    "visualizations": final_values.get("visualizations") or [],
}
```

3. `history.py` `get_messages` already returns `metadata`. No Firestore migration.
4. Do **not** ship a hardcoded fake chart. Prove the field with a unit test or a local flag.

**Check**

- POST `/saige/chat` → `"visualizations": []`
- POST `/saige/chat/stream` → last `done` event includes `"visualizations": []`
- GET `/saige/threads/{id}/messages` after a turn → assistant `metadata.visualizations` present

---

### G1 — Playground + stub renderer (Guia)

**Goal:** See mock cards. No API.

**Create**

- `oatmealfarmnetwork/src/saige-viz/vizMocks.js`
- `oatmealfarmnetwork/src/saige-viz/VizRenderer.jsx`
- `oatmealfarmnetwork/src/saige-viz/VizPlayground.jsx`

**Steps**

1. Create the folder. Do not touch `SaigeWidget.jsx` or Python.
2. Paste David’s JSON into `vizMocks.js` as `export const VIZ_MOCKS = [...]`.
3. `VizRenderer` switches on `spec.type`; unknown type → title + “Chart coming soon”.
4. `VizPlayground` maps `VIZ_MOCKS` to `<VizRenderer spec={m} />`.
5. Show only in dev. Ask David to add this on `SaigePage.jsx`, or add it yourself at the bottom of the page:

```jsx
{new URLSearchParams(window.location.search).get('vizdev') === '1' && (
  <VizPlayground />
)}
```

If unsure about editing `SaigePage.jsx`, ask David for those five lines.

**Check:** Open `http://localhost:5173/saige?vizdev=1` — seven titled placeholder cards.

**Do not:** `npm install` anything.

---

## 9. Phase 1 — Tier 1 (in-chat)

### 9.1 Guia — presentational components

Work one file at a time. Import into `VizRenderer` when it looks right. Copy styles; do not invent. No fetch, no API hooks.

#### G2 — KPI card

- **Create:** `src/saige-viz/KpiViz.jsx`
- **Copy from:** `Kpi` in `CropAnalysisSummary.jsx`
- **Show:** `spec.title` (muted); `spec.data.value` + `unit` (big, green); `delta` amber if negative, green if positive; `hint` in 12px gray
- **Missing value:** show “—”
- **Check:** Playground reads “Soil moisture **28%**” with delta

#### G3 — Alert card

- **Create:** `src/saige-viz/AlertViz.jsx`
- **Copy from:** `URGENCY_STYLE` in `SaigeFieldsCard.jsx`
- **Show:** severity colors (`critical` / `high` / `medium` / `low`), title, `data.message`, `data.field_name`
- **Do not:** dismiss button, API, bell logic
- **Check:** High looks like the existing field urgency banner

#### G4 — Table

- **Create:** `src/saige-viz/TableViz.jsx`
- **Must:** `<table>` from `columns` + `rows`; slice to 20 + “+N more”; 12–13px; header `#f0f7ee`; border `#c7dfc2`
- **Check:** Animals mock renders; empty rows do not crash

#### G5 — Progress / range

- **Create:** `src/saige-viz/ProgressViz.jsx`
- **Copy from:** `NDVIMiniBar` in `SaigeFieldsCard.jsx`
- **Must:** clamp 0–100; fill `#3D6B34`; label + hint
- **Check:** 62% fill, label “Flowering”

#### G6 — Timeline

- **Create:** `src/saige-viz/TimelineViz.jsx`
- **Must:** vertical list from `data.items` — date · action · field. No chart library.
- **Check:** 4–5 mock activities stack cleanly

#### G7 — Empty state + action button

- **Create:** `src/saige-viz/VizActions.jsx`
- Empty `data` → title + “No data yet” + first action if any
- Map `spec.actions` to links; Saige green button style (proposal Approve on `SaigePage`)
- Use `VizActions` under every card
- **Check:** mock with `"data": {}` does not crash; “Open field” goes to `/precision-ag/fields/12`

#### G8 — i18n

- **Edit:** `oatmealfarmnetwork/public/locales/en/translation.json`
- Add `saige_viz.no_data`, `saige_viz.more_rows`, `saige_viz.open_full`
- Use `useTranslation` like other Saige files
- Copy keys to other locales if they exist; English-only is OK if David agrees

---

### 9.2 David — plumbing + charts

#### D3 — Dual output without breaking ReAct

**Create:** `saige/visualizations/pending.py`

```python
from contextvars import ContextVar

_pending: ContextVar[list] = ContextVar("saige_viz_pending", default=None)

def viz_reset():
    _pending.set([])

def viz_emit(spec: dict):
    bucket = _pending.get()
    if bucket is None:
        bucket = []
        _pending.set(bucket)
    bucket.append(spec)

def viz_take() -> list:
    out = list(_pending.get() or [])
    _pending.set([])
    return out
```

**Call `viz_reset()`** at the start of a chat turn (`_prepare_turn` in `chat/service.py` or the top of the specialist loop).

**Emit from these five tools first** (before `return "\n".join(lines)`):

| Tool | File | Emit |
|---|---|---|
| `get_field_irrigation_tool` | `tools/agriculture/precision_ag.py` | KPI (deficit) + line (`daily` precip/ET) |
| `get_field_history_tool` | same | NDVI line by date |
| `get_field_alerts_tool` | same | up to 3 `alert_card`s |
| `get_field_gdd_tool` | same | `progress` or GDD KPI |
| `list_my_animals_detail_tool` | `tools/farm/business_data.py` | `table` from SQL rows |

Example:

```python
from visualizations.pending import viz_emit

viz_emit({
    "id": f"irrig_{field_id}",
    "type": "line_chart",
    "title": f"Water balance — {field.get('name') or field_id}",
    "source_tool": "get_field_irrigation_tool",
    "data": {
        "xKey": "date",
        "yKey": "deficit_in",
        "unit": "in",
        "series": series[-90:],
    },
    "actions": [{ "label": "Open field", "href": f"/precision-ag/fields/{field_id}" }],
})
return "\n".join(lines)
```

**Honesty:** irrigation `daily` is ET vs rain. Title it “Water deficit” or “ET vs rainfall”, not “Soil moisture %”, unless Crop Monitor stores moisture.

**If series empty:** do not `viz_emit`.

**Check:** mocked `_api_get` / `_query` with 7 daily rows → `viz_take()` has one line chart; empty daily → `[]`.

---

#### D4 — Mapper

**Create:** `saige/visualizations/mapper.py`

- `map_pending(raw_list) -> list[dict]`
- Run each item through `validate_spec`
- Cap 3 specs / 90 points / 50 table rows
- Dedupe by `(type, title)`
- **No LLM**

**Check:** empty in → `[]`; bad spec dropped; 5 alerts → 3 cards

---

#### D5 — Attach to graph + finalize

**Edit:** `saige/graph/nodes.py` (tool loop ~line 1658, synthesizer return ~3840)

After the tool loop:

```python
from visualizations.pending import viz_take
from visualizations.mapper import map_pending

visualizations = map_pending(viz_take())
```

Return on specialist packet **and** synthesizer output. If multiple specialists run, concat then cap.

Synthesizer prompt (~line 3766) add:

> If charts will be shown, describe them in one sentence. Do not paste tables of numbers or ASCII charts.

`_finalize_result` already copies `visualizations` from D2.

**Check (logged-in farm with fields, inspect JSON not UI):**

| Prompt | Expect |
|---|---|
| “Should I irrigate [field]?” | KPI and/or line |
| “List my animals” | table |
| “Tell me a joke” | `[]` |
| “Hello” | `[]` |

---

#### D6 — Line and bar (Recharts)

**Create**

- `oatmealfarmnetwork/src/saige-viz/LineChartViz.jsx`
- `oatmealfarmnetwork/src/saige-viz/BarChartViz.jsx`

**Copy from:** `CropAnalysisSummary.jsx`

- `ResponsiveContainer` 100% × 220px
- X = `xKey`, Y = `yKey`; unit in tooltip
- `series.length < 2` → Guia’s empty state
- Wire `line_chart` / `bar_chart` in `VizRenderer`; leave Guia’s cases alone

---

#### D7 — Wire `SaigePage` chat

**Edit:** `oatmealfarmnetwork/src/SaigePage.jsx`

1. In `ChatBubble`, under `{message.content}` (~line 210):

```jsx
{!isUser && Array.isArray(message.visualizations) && message.visualizations.map((v) => (
  <div key={v.id || v.title} style={{ marginTop: 10 }}>
    <VizRenderer spec={v} />
  </div>
))}
```

Widen assistant bubble when viz exist (`maxWidth: '90%'`).

2. On `/chat` success (~line 1082), same pattern as `proposals`:

```js
const visualizations = Array.isArray(payload.visualizations) ? payload.visualizations : [];
// on the message:
...(visualizations.length ? { visualizations } : {}),
```

3. TTS stays `playTTS(content)` only.

4. `handleSelectThread` (~line 889) currently drops metadata. Change to:

```js
messages = (d.messages || []).map((m) => ({
  role: m.role,
  content: m.content,
  visualizations: m.metadata?.visualizations || m.visualizations || [],
}));
```

**Check:** irrigate question on `/saige` shows caption + chart; thread reload keeps it; joke has none.

---

#### D8 — `SaigeWidget` + stream `done`

**Edit:** `oatmealfarmnetwork/src/SaigeWidget.jsx`

1. On `evt.type === 'done'` (~line 663), attach `visualizations` like `proposals`.
2. Same on `/chat` fallback (~line 737).
3. Render `<VizRenderer />` under assistant text. Widget: `visualizations.slice(0, 2)`.
4. Charts appear **after** `done`, not during `token` events.

**Check:** floating widget on a farm page; irrigate prompt; chart after stream finishes.

---

## 10. Phase 2 — Farm-specific

Start only after Tier 1 is on staging.

### David

| ID | Task | How |
|---|---|---|
| **D9** | Weather / forecast | Keep `format_for_llm` string. `viz_emit` a `line_chart` from the same `weather_data`. 7-day forecast = second series or second `line_chart`. Prefer **no new type**. |
| **D10** | Price + herd composition | Price tools → line + optional band. Animals by species → `bar_chart`. Inventory question still uses Guia’s table. |
| **D11** | Farm / field map | Spec `{ type: "farm_map", data: { field_ids: [12, 15] } }` or `{ type: "field_map", data: { field_id, layer: "NDVI" } }`. Client loads like `PrecisionAgMaps.jsx`. v1 may be `MAP_CMD` + “Open map” link. |
| **D12** | Pest + monitoring | Scouting → table or timeline. Photo pest → `alert_card` with confidence. No heatmap without lat/lon. |
| **D13** | LOA widget | Same `VizRenderer` in `livestock-of-america`. Livestock / price / weather only. |

### Guia

| ID | Task | How |
|---|---|---|
| **G9** | Chart chrome | Legend labels and tooltip strings only. Do not change Recharts keys. |
| **G10** | Action row everywhere | Confirm `VizActions` under every viz. Done if G7 already covered this. |
| **G11** | Loading skeleton | `VizSkeleton.jsx` — gray KPI + chart boxes. David mounts it next to the thinking spinner. |
| **G12** | QA | Run [§14](#14-qa-checklist) on staging. Pass/fail in the PR description with screenshots. |

---

## 11. Phase 3 — Advanced

| ID | Owner | Task | Note |
|---|---|---|---|
| **D14** | David | Calendar | Planting + activity dates. Avoid a new library if a month grid + timeline is enough. |
| **D15** | David | Field A vs Field B | Two line charts + KPI row. Compose Tier 1. |
| **D16** | David | Heatmap / geo heatmap | Only if rasters or lat/lon exist. Else deep-link Precision Ag. |
| **D17** | David | Whole-farm overview | Stay on `SaigePage` chrome (`SaigeFieldsCard`, `/precision-ag/dashboard`). Chat links in; it does not embed the dashboard. |
| **G13** | Guia | Calendar day cells | Colored dots for plant vs harvest. CSS + mock dates. Only if D14 exists. |

**Skip:** Sankey, radar — no data model yet. Do not assign to Guia.

---

## 12. Week-by-week schedule

**Week 1**

- David: D1 → D2 → D3 (irrigation + history only)
- Guia: G1 → G2 → G3 → G4 → G7

**Week 2**

- David: D4 → D5 → D6 → D7 (`SaigePage`)
- Guia: G5 → G6 → G8
- David merges Guia’s components into `VizRenderer`

**Week 3**

- David: D8 (widget + history), then D9–D10
- Guia: G9–G11, then G12 QA

**Week 4+**

- David: D11 maps, D13 LOA, D14–D15
- Guia: G12 ongoing + G13 if calendar ships

**First three commits**

- David: D1, D2, D3
- Guia: G1, G2, G3

---

## 13. Dependency graph

```
D1 mocks ─┬─► G1 playground ─► G2 KPI ─► G3 alert ─► G4 table
          │                              G5 progress, G6 timeline, G7 empty
          └─► D2 API field ─► D3 viz_emit in 5 tools ─► D4 mapper ─► D5 graph
                                                              │
                         D6 Recharts ─► D7 SaigePage ◄────────┘
                                      ─► D8 Widget
                         G8 i18n, G9–G11 polish, G12 QA
```

Guia is unblocked after D1. David can implement D3–D5 without waiting on UI. D7 is the first merge of both tracks.

---

## 14. QA checklist

Run on staging with a real business that has fields. If a prompt 500s, send David the `trace_id`.

| Prompt | Expect |
|---|---|
| “Should I irrigate [field]?” | KPI and/or line + one-sentence caption |
| “How has [field] NDVI been?” | NDVI line |
| “Any field alerts?” | Alert card or “none” text |
| “Show my animals” | Table |
| “What growth stage is [field]?” | Progress or GDD KPI |
| “Tell me a joke” | No viz |
| “Hello” | No viz |
| Reload the thread | Charts still render |

---

## 15. Definition of done (Tier 1)

- [ ] `/chat` JSON includes `visualizations` (possibly empty)
- [ ] `/chat/stream` `done` includes the same field
- [ ] Five tools can emit specs without breaking specialist text
- [ ] Joke / hello emit none
- [ ] `SaigePage` bubble renders Guia’s KPI / table / alert / progress / timeline and David’s line
- [ ] Thread reload restores charts from `metadata.visualizations`
- [ ] Widget shows at most two viz after stream `done`
- [ ] No new npm packages
- [ ] Guia never had to edit `graph/nodes.py`

---

## 16. Out of scope

- Rebuilding Farm KPI or Precision Ag inside the chat bubble
- LLM-generated chart specs
- Sankey / radar until a real data model exists
- Sending rasters or GeoJSON through SSE
- Guia owning schema, tools, streaming, maps, or Recharts

---

## First actions

1. **David:** D1 schema + `saige/docs/viz_mocks.json`, then D2 empty `visualizations[]` on `/chat`.
2. **Guia:** G1 folder + stub renderer using that JSON, then G2 KPI card.
)