# Design Memo: Streamlit MVP for Budget Reconciliation Tool

> Research output from subagent run on 2026-06-09. Companion to `research_reconciliation_algorithm.md`. Not yet implemented.

**Audience:** Budget analysts at COL Rivera's organization
**Goal:** Let one analyst load two budget datasets, walk through algorithm-proposed groupings per `(APPN, Fiscal Year)`, edit them, lock them, and export.

## 1. User Flow

The analyst lives in a single Streamlit app with four logical phases, navigated by a left sidebar:

1. **Load** — landing page. Analyst points at the two Excel files (default: `data/synthetic_data_red_side.xlsx` and `data/synthetic_data_green_side.xlsx`). App parses, validates `(APPN, Fiscal Year)` pairs, runs the reconciliation algorithm in the background, caches candidate solutions in `st.session_state`.
2. **Overview** — bucket-status table showing all `(APPN, FY)` pairs and their current state (Unstarted / Draft / Locked). Click a row to drill in.
3. **Reconcile** — the workhorse screen. For the selected bucket, show algorithm's top-K candidates, let analyst edit, lock individual groups, request next candidate, then "Lock bucket" overall.
4. **Export** — once N buckets are locked, download as Excel + JSON.

Transitions: Load → Overview (auto on parse success) → Reconcile (click row) → Overview (back button, state persists) → Export (sidebar). The analyst typically loops Overview ↔ Reconcile 110 times (one per bucket).

## 2. Key Screens

### 2.1 Landing / Data Load

```
+--------------------------------------------------------+
| Budget Reconciliation Tool                  v0.1 (MVP) |
+--------------------------------------------------------+
| Red-side  (granular)     [ data/synthetic_red.xlsx  v] |
| Green-side (rolled-up)   [ data/synthetic_green.xlsx v]|
|                                                        |
| [  Load & Run Reconciliation Algorithm  ]              |
|                                                        |
| Status: idle                                           |
+--------------------------------------------------------+
```

After click: progress bar (`st.status`) shows "Parsing red (25,000 rows)... Parsing green (4,678 rows)... Building 110 candidate sets... Done."

### 2.2 Bucket-Status Overview

```
+----------------------------------------------------------+
| Overview — 110 buckets        Locked: 12 | Draft: 3 | -- |
+----------------------------------------------------------+
| APPN  | APPN Title                | FY   | Red$K | State|
| 3400  | Operation & Maintenance-AF | 2024 |  4.2M | LOCK |
| 3400  | Operation & Maintenance-AF | 2025 |  4.1M | DRAFT|
| 3740  | O&M - AFR                  | 2024 |   52K | --   |
| 3500  | Military Personnel - AF    | 2024 |   ... | --   |
+----------------------------------------------------------+
   [ Filter: APPN v ] [ FY v ] [ State v ] [ Search ___ ]
```

Color: green row = locked, yellow = draft, gray = untouched. Click any row → Reconcile screen for that bucket.

### 2.3 Candidate-Grouping Review (the core screen)

```
+-----------------------------------------------------------+
| Bucket: 3740 / O&M-AFR / FY2024                           |
| Candidate 1 of 5   [< Prev] [Next >]   Confidence: HIGH   |
| Total red: $52,151K   Total green: $52,148K   diff: 0.006%|
+-----------------------------------------------------------+
| Group 1: "Travel Services"        sum-diff: 0.04% within  |
|----------------------------|------------------------------|
| RED (15)                   | GREEN (1)                    |
|  [x] Travel - Airfare      |  [x] Travel Services         |
|  [x] Travel - Lodging      |                              |
|  [x] Travel - Meals  ...   |                              |
|  Red $:  21,400K           |  Green $: 21,408K            |
|  [ Lock group ]  [ Edit v ]  similarity: 0.94             |
|-----------------------------------------------------------|
| Group 2: "Personnel Services"     sum-diff: 0.32% OVER    |
| ...                                                       |
+-----------------------------------------------------------+
| [ Reject candidate, show next ]   [ Lock entire bucket ]  |
+-----------------------------------------------------------+
```

Each group is an `st.expander`, headed by a colored badge: green tick if within tolerance, red warning if over. Two columns side-by-side (`st.columns(2)`) show red and green members.

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
|  Locked buckets: 12 / 110                                 |
|  [ Download groupings.xlsx ] [ Download groupings.json ]  |
|  [ Download full audit log .csv ]                         |
|  Warning: 98 buckets still unlocked.                      |
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

1. **Data load mode:** hardcoded paths (fast MVP) or `st.file_uploader` (deployable demo)?
2. **Algorithm contract:** can the algorithm return a JSON of candidate groupings, or must the app call into it live? Affects caching strategy.
3. **Export format:** wide Excel (one row per red category with its assigned green bucket) or long (one row per red-green pair)?
4. **Auth:** is this a single-user local app or does it need login? Affects whether session state persists across browser closes.
5. **Persistence:** when the analyst quits mid-bucket, do we save to disk or lose work?
6. **Acceptance rule for "locked":** must sum-diff be within tolerance, or can analyst force-lock an out-of-tolerance group with a note?

Answers to (1), (3), and (6) are blocking for week-1 implementation.
