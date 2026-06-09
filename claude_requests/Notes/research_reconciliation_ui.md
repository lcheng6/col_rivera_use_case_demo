# Design Memo: Streamlit MVP for Budget Reconciliation Tool

> Research output from subagent run on 2026-06-09. Companion to `research_reconciliation_algorithm.md`. Not yet implemented.
>
> **Revision 2 (2026-06-09):** the workflow grain is now **per APPN** (11 rows in the synthetic data), not per `(APPN, Fiscal Year)` (110 rows). A single grouping covers all FYs; the review screen surfaces per-FY diagnostics so the analyst can see at a glance which years pass and which fail the tolerance gate.
>
> **Decisions made (2026-06-09)** — keyed by Open Question number in §7:
> - **Q1 File-load mode** → **hardcoded paths** (`data/synthetic_data_red_side.xlsx`, `data/synthetic_data_green_side.xlsx`). No file-uploader in MVP.
> - **Q3 Export format** → **long** (one row per red-green pair: `appn, fy, red_cat, green_bucket, red_sum, green_sum, diff_pct, locked`). Easier to pivot downstream than a wide layout.
> - **Q6 Force-lock** → **allowed**. Analyst can lock a group even if some years are outside tolerance, with a required note. The note is captured per-group and exported in the audit log.
> - **Q7 Tolerance default** → **1.5%** in MVP. Loose enough to keep early data variants in scope; user can tighten via the sidebar slider.

**Audience:** Budget analysts at COL Rivera's organization
**Goal:** Let one analyst load two budget datasets, walk through algorithm-proposed groupings per APPN (with per-FY diagnostics), edit them, lock them, and export.

## 1. User Flow

The analyst lives in a single Streamlit app with four logical phases, navigated by a left sidebar:

1. **Load** — landing page. App auto-loads the two Excel files from the hardcoded paths, validates the 11 APPN groups, runs the reconciliation algorithm in the background, caches candidate solutions in `st.session_state`.
2. **Overview** — APPN-status table (11 rows) showing each APPN's current state (Unstarted / Draft / Locked) and a year-pass summary (e.g. "10/10 years within tol" or "7/10 years pass"). Click a row to drill in.
3. **Reconcile** — the workhorse screen. For the selected APPN, show algorithm's top-K candidate groupings, each with a per-FY sum-diff strip so the analyst can see which years pass. Let analyst edit, lock individual groups, request next candidate, then "Lock APPN" overall.
4. **Export** — once N APPNs are locked, download as Excel + JSON.

Transitions: Load → Overview (auto on parse success) → Reconcile (click row) → Overview (back button, state persists) → Export (sidebar). The analyst typically loops Overview ↔ Reconcile 11 times (one per APPN), not 110.

## 2. Key Screens

### 2.1 Landing / Data Load

```
+--------------------------------------------------------+
| Budget Reconciliation Tool                  v0.1 (MVP) |
+--------------------------------------------------------+
| Red-side  (granular)     data/synthetic_data_red_side  |
|                          .xlsx                          |
| Green-side (rolled-up)   data/synthetic_data_green_side|
|                          .xlsx                          |
|                                                        |
| [  Load & Run Reconciliation Algorithm  ]              |
|                                                        |
| Status: idle                                           |
+--------------------------------------------------------+
```

After click: progress bar (`st.status`) shows "Parsing red (25,000 rows)... Parsing green (4,678 rows)... Solving 11 APPN groupings... Done."

### 2.2 APPN-Status Overview

```
+----------------------------------------------------------+
| Overview — 11 APPNs           Locked: 2 | Draft: 1 | --  |
+----------------------------------------------------------+
| APPN  | APPN Title                | $K/yr | Years | State|
| 3400  | Operation & Maintenance-AF | 4.2M  | 10/10 | LOCK |
| 3500  | Military Personnel - AF    | 1.5M  | 9/10  | DRAFT|
| 3740  | O&M - AFR                  |   52K | 10/10 | LOCK |
| 3080  | Other Procurement - AF     |  720K |  6/10 | --   |
| 3600  | RDT&E - AF                 | 1.7M  | 10/10 | --   |
| 0540  | Medicare Retire Cont - AF  | 2.8M  | 10/10 | --   |
| ...                                                       |
+----------------------------------------------------------+
   [ Filter: APPN v ] [ State v ] [ Search ___ ]
```

The "Years" column shows `<years passing>/<years total>` for the current top candidate at the default tolerance — that's the all-year gating check at a glance. Color: green row = locked, yellow = draft, gray = untouched. Click any row → Reconcile screen for that APPN.

### 2.3 Candidate-Grouping Review (the core screen)

```
+-------------------------------------------------------------+
| APPN: 3740 / O&M-AFR                                        |
| Candidate 1 of 5   [< Prev] [Next >]   Confidence: HIGH     |
| All years within tol: 10/10  Total red (10yr): $448K        |
+-------------------------------------------------------------+
| Group 1: "Travel Services"                                  |
|---------------------------|---------------------------------|
| RED (15)                  | GREEN (1)                       |
|  [x] Travel - Airfare     |  [x] Travel Services            |
|  [x] Travel - Lodging     |                                 |
|  [x] Travel - Meals  ...  |                                 |
| similarity: 0.94          | match_type: many-to-one         |
|---------------------------|---------------------------------|
| Per-FY sum-diff:                                            |
|  2024 [v] 0.04%   2025 [v] 0.02%   2026 [v] 0.05%           |
|  2027 [v] 0.03%   2028 [v] 0.04%   2029 [v] 0.06%           |
|  2030 [v] 0.02%   2031 [v] 0.05%   2032 [v] 0.04%           |
|  2033 [v] 0.03%        max: 0.06%  avg: 0.04%               |
|  [ Lock group ]   [ Edit v ]                                |
|-------------------------------------------------------------|
| Group 2: "Personnel Services"           1 year FAIL (2027)  |
|  ... per-FY strip with 2027 highlighted red ...             |
+-------------------------------------------------------------+
| [ Reject candidate, show next ]   [ Lock entire APPN ]      |
+-------------------------------------------------------------+
```

Each group is an `st.expander`. The per-FY sum-diff strip is the gating-check view: every year that passes shows a green tick + diff%, every year that fails shows a red mark and is called out in the group header. Group-level "Lock" is enabled only if all 10 years pass (or if the analyst opts to force-lock — see Open Question 6).

### 2.4 Manual Group Editor

```
+-----------------------------------------------------------+
| Edit assignments — RED side                               |
|-----------------------------------------------------------|
| Category                       | Group  | $ K  | locked   |
| Travel - Airfare               | 1 v    | 4200 |   --     |
| Travel - Lodging               | 1 v    | 5100 |   --     |
| Fuel                           | 4 v    |  900 |   yes    |
| Engineering Tech Services      | 3 v    | 2800 |   --     |
|                                | New... |      |          |
+-----------------------------------------------------------+
|   [ Apply changes ]   [ Reset to candidate ]              |
+-----------------------------------------------------------+
```

A `st.data_editor` with one row per category and a categorical "Group" column. Same screen, separate tab, for green side.

### 2.5 Export / Save

```
+-----------------------------------------------------------+
| Export                                                    |
|  Locked APPNs: 2 / 11                                     |
|  [ Download groupings.xlsx ] [ Download groupings.json ]  |
|  [ Download full audit log .csv ]                         |
|  Warning: 9 APPNs still unlocked.                         |
+-----------------------------------------------------------+
```

## 3. Core Interactions

- **Move a category between groups:** `st.data_editor` with a categorical "Group" column (values 1, 2, 3, ..., "New group", "Unassigned"). One click changes the dropdown; analyst clicks "Apply." This beats `streamlit-sortables` (third-party, fragile) and double-multiselect (clunky for 29 items). It scales linearly with category count and gives a single canonical source of truth in `st.session_state["assignments"][(appn,fy)]`.
- **Lock/unlock a group:** one `st.button("Lock group")` per group; flips a flag in `st.session_state`. Locked groups render with a gray background and disabled `st.data_editor` rows.
- **Request next candidate:** `st.button("Next candidate")` cycles index `k` in `st.session_state["k_idx"][(appn,fy)]`. Display "Candidate k of K."
- **Adjust sum-tolerance:** `st.slider("Tolerance %", 0.0, 5.0, 0.5, step=0.1)` at the bucket level. Re-colors badges live.
- **Search/filter:** `st.text_input("Filter categories")` above the data_editor, substring match on category name. Plus sidebar filters on the overview table.

## 4. Visual Cues

| Signal | Render |
|---|---|
| High confidence | green pill, "HIGH" label, score >= 0.85 |
| Medium / Low | yellow / red pill |
| Sum-diff within tolerance | green check, "0.04% within" |
| Sum-diff over tolerance | red triangle, "0.32% OVER" |
| All years pass gate | green "10/10 years" badge in group header |
| Some years fail gate | yellow/red "N/10 years" badge with failing years listed |
| Per-FY strip cell (pass) | small green tick + diff% in monospace |
| Per-FY strip cell (fail) | red mark + diff% in monospace |
| Consumed category | strikethrough name + gray text |
| Available category | normal text |
| Semantic similarity | small inline number, 0.00–1.00 |
| Locked group | gray background, lock glyph in header |
| Draft group | yellow border |

Emoji used sparingly in badges only; everything else is text + color so it survives copy-paste to email.

## 5. Streamlit Patterns

- **Layout:** `st.sidebar` for navigation + filters; `st.tabs(["Red", "Green"])` for edit; `st.columns(2)` for side-by-side review; `st.expander` for each candidate group.
- **State:** one `st.session_state` dict keyed by `(appn, fy)` holding assignments, lock-flags, candidate index, slider values. Survives reruns.
- **Tables:** `st.dataframe` (read-only, with row selection) for the overview; `st.data_editor` (editable) for assignments; `st.metric` for sum totals.
- **Caching:** `@st.cache_data` on file parse + algorithm output, keyed by file hash.
- **No drag-and-drop:** Streamlit has none natively, and `streamlit-sortables` adds a custom-component dependency that breaks easily across versions. The `st.data_editor`-with-Group-column pattern is built-in, debuggable, and gives a clean diff against the algorithm's suggestion.

## 6. MVP vs Nice-to-Have

**Ships first (MVP):**
- Hard-coded file paths to the two synthetic Excels.
- Top-1 candidate per bucket only.
- Sum-only matching, no embeddings.
- `st.data_editor` group reassignment.
- Excel export.

**Cut for v1; revisit:**
- Top-K candidates with prev/next browsing.
- Semantic-similarity scores.
- Per-group tolerance slider.
- JSON export, audit log.
- Multi-user / auth.
- File upload widget (replace hardcoded paths).

## 7. Open Questions for the User

1. ~~**Data load mode:** hardcoded paths (fast MVP) or `st.file_uploader` (deployable demo)?~~ **RESOLVED 2026-06-09: hardcoded paths.**
2. **Algorithm contract:** can the algorithm return a JSON of candidate groupings, or must the app call into it live? Affects caching strategy.
3. ~~**Export format:** wide Excel or long (one row per red-green pair)?~~ **RESOLVED 2026-06-09: long.** Columns: `appn, fy, red_cat, green_bucket, red_sum, green_sum, diff_pct, locked, force_lock_note`.
4. **Auth:** is this a single-user local app or does it need login? Affects whether session state persists across browser closes.
5. **Persistence:** when the analyst quits mid-APPN, do we save to disk or lose work?
6. ~~**Acceptance rule for "locked":** must every group sum-balance for every year, or can analyst force-lock a group that fails some years (with a note)?~~ **RESOLVED 2026-06-09: force-lock allowed.** A "Force lock" button alongside the regular Lock button, requires a free-text note when used. Note is preserved in the audit log and the long-format export.
7. ~~**Tolerance default:** what %?~~ **RESOLVED 2026-06-09: 1.5%.** User can tighten or loosen via the sidebar slider (range 0.01–5.0).

Remaining open: (2), (4), (5). None block the MVP — all have safe defaults (call algorithm live, single-user, session-only state).