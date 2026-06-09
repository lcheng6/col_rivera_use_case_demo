# Design Memo — Budget Category Reconciliation Across Two Schemes

> Research output from subagent run on 2026-06-09. Recommends the algorithm/logic for the reconciliation MVP. Not yet implemented.
>
> **Revision 2 (2026-06-09):** the problem grain is now **per-APPN with per-year sum-balance constraints**, not per-(APPN, Fiscal Year). The user added the gating requirement that a candidate grouping should sum-reconcile *for every fiscal year* in which both systems have data. A grouping that passes only one year but fails the others is a false positive.

## 1. Problem class

This is a **balanced set-partitioning problem with multi-year sum-equality constraints and a semantic-affinity objective** — a **partition-matching** or **two-sided clustering** problem. For each APPN the red side gives a vector of N category totals *per fiscal year* and the green side gives a vector of M category totals *per fiscal year*; for each year `sum(red) ≈ sum(green)` by construction. We must find a single common refinement of the two category sets — one partition of red into K groups and one partition of green into K groups — such that, for **every fiscal year**, group-wise sums match within tolerance and K is as large as possible (finer groups are more informative).

The multi-year requirement is the gating quality check: if a grouping reconciles in FY2024 but blows the tolerance in FY2025, it has overfit to one year's noise and is not a real categorical correspondence.

The closest textbook formulation is the **Generalized Assignment / Set-Partitioning ILP** (Garfinkel & Nemhauser, 1972; Wolsey, *Integer Programming*, 1998, ch. 13). The "match two partitions of equal-mass measures" framing is also a discrete **Optimal Transport** problem (Peyré & Cuturi, *Computational Optimal Transport*, 2019, §2–§4), where the transport plan, after thresholding, induces the bipartite grouping. The "find fewest groups whose sums match" sub-problem is **multiple subset-sum** (Caprara, Kellerer, Pferschy 2000), which is weakly NP-hard but trivially small at N, M ≤ 30.

## 2. Recommended approach for MVP

**Recommendation: a single ILP per APPN, solved with OR-Tools CP-SAT**, with the objective lexicographically ordered as (i) maximize number of groups K, (ii) minimize total absolute sum-mismatch summed across all FYs, (iii) maximize aggregate name-embedding similarity.

**Input:** per APPN, two dataframes — `red[name, fy] = dollars`, `green[name, fy] = dollars` — plus a pre-computed `S[i,j]` cosine-similarity matrix from sentence embeddings (see §4). The FY axis has up to 10 years (2024–2033).

**Decision variables** (for a fixed upper bound K_max = min(N, M)):
- `x[i,k] ∈ {0,1}` — red category i belongs to group k
- `y[j,k] ∈ {0,1}` — green category j belongs to group k
- `z[k] ∈ {0,1}` — group k is active
- Each row of x and y sums to exactly 1 (every category assigned); `z[k] ≥ x[i,k]`, `z[k] ≥ y[j,k]`.

Note that x and y do **not** depend on FY — the grouping is shared across years.

**Constraints:** for **each fiscal year `fy`** and **each active group `k`**:
`| Σ red[i,fy]·x[i,k] − Σ green[j,fy]·y[j,k] | ≤ tol · max(Σ red[·,fy], Σ green[·,fy])`
(tolerance default 0.005 — looser than the per-bucket 0.0001 to absorb the jitter in the data generator; user-configurable).

This adds 10 sum-balance constraints per active group instead of 1, which is the gating-check formulation the user asked for: a grouping that fails any single year's constraint is infeasible.

**Objective (weighted, with weights chosen so terms are lexicographic in practice):**
`maximize  1000·Σ z[k]  −  Σ_fy Σ_k |mismatch_{k,fy}|  +  0.1·Σ S[i,j]·x[i,k]·y[j,k]`
The cross-term is linearized by introducing `w[i,j,k] = x[i,k]·y[j,k]` with standard McCormick constraints.

**Output shape:** list of groups for the APPN, each a `(red_set, green_set, per_fy_diagnostic, avg_diff_pct, max_diff_pct, sim)` tuple. The `per_fy_diagnostic` is a list of `(fy, red_sum, green_sum, diff_pct)` — surfaces every year's status so the UI can flag the failing years.

**Complexity / runtime:** the model has O(K_max·(N+M)) binary vars and O(K_max·N·M) linearization vars; FY only adds linear constraints, not variables. For N=29, M=7, K_max=7 (O&M-AF) that's ~250 binaries plus ~1.5k linearization vars and ~70 sum-balance constraints (7 groups × 10 FY). CP-SAT solves this in well under a second. The worst plausible APPN (N=M=30) yields ~27k binaries and ~300 constraints — still 1–5 s with 8-thread search. We cap solver time at 10 s per APPN and accept the best feasible solution.

**Why CP-SAT over PuLP/CBC or python-mip:** CP-SAT handles the disjunctive structure ("either group k is active or no one is in it") and the lexicographic objective natively via search hints and `AddDecisionStrategy`, and its parallel portfolio is meaningfully faster than CBC on this size.

**Data-generator caveat:** the current synthetic data generator (`create_open_system_data.py`) distributes the per-(APPN, FY) air-gapped total across open categories using **an independent Dirichlet draw per year**. That means even the "true" categorical correspondence does not sum-reconcile across years above bucket noise — so on the current synthetic data, no fine-grained grouping will pass the all-year gate. Recommended fix: regenerate the green-side data using the explicit per-row rollup described in `claude_requests/Notes/solution_notes_for_reconciliation.md`, which gives year-stable group-to-group correspondence and makes the all-year gate meaningful.

## 3. Alternative approaches

**(a) Greedy "subset-sum within slack" heuristic.** Sort red and green categories by dollars descending. Repeatedly take the largest unassigned green category G_j and find the smallest red subset whose sum lands within tolerance of G_j (bounded enumeration, depth ≤ 4). Tie-break by name-embedding similarity. Complexity O(N⁴) per bucket. Trade-off: <50 ms per bucket; no global guarantee — it will lock in a coarse rollup early and miss a finer partition that requires recombining earlier picks. Good as a fallback and as a warm-start for the ILP.

**(b) Entropic Optimal Transport (Sinkhorn) + thresholded clustering.** Treat each side as a discrete measure (mass = dollars). Compute the OT plan with `ot.sinkhorn` (POT library) using cost `C[i,j] = 1 − S[i,j]`. Threshold the plan matrix, take connected components of the resulting bipartite graph as groups. Trade-off: O(NM) per iteration, ~50 ms; produces soft, fractional matches that you then have to round; loses the explicit "group sums match within tol" guarantee. Best when many-to-many splits dominate and tolerance is loose.

**(c) Pure-similarity bipartite matching (Hungarian).** `scipy.optimize.linear_sum_assignment` on `−S`, then merge red items mapped to the same green into groups. Trade-off: forces 1-to-1 at the category level which is wrong here — Travel has 15 red items mapping to one green "Travel Services", which Hungarian can't express without auxiliary structure.

The ILP dominates (a) on optimality and (b)/(c) on respecting the hard sum-balance constraint, at a runtime cost that's negligible at this problem size.

## 4. Using semantic similarity

**Model: `sentence-transformers/all-MiniLM-L6-v2`** (384-d, 80 MB, MIT-licensed, runs on CPU at ~2k sentences/sec). Justification: the corpus is a few hundred short category labels — embedding quality differences between MiniLM and `text-embedding-3-small` are negligible at this scale, and MiniLM removes the OpenAI API dependency (relevant given one side is "air-gapped"). Embeddings are cached on disk by label string.

**Pre-processing:** strip the common prefix ("Travel - ", "Other Services - ") into a structured token so "Travel - Airfare" and "Travel Services" share a strong base-token signal. Embed the cleaned label, then `S[i,j] = cosine(emb_i, emb_j)` clipped to [0, 1].

**Combination with sum-balance:** the objective in §2 is a **lexicographic-by-weight** scheme — group count dominates, then mismatch, then similarity as a tie-breaker. This matters because there are typically many feasible partitions within tolerance and similarity is what picks "Travel-Airfare → Travel Services" over "Travel-Airfare → General Services" when both happen to sum-balance. Avoid making similarity a hard constraint (a minimum-S threshold) — it overfits on label phrasing and can make buckets infeasible.

## 5. Output format

```json
{
  "appn": "3400",
  "appn_title": "Operation and Maintenance - AF",
  "fiscal_years": [2024, 2025, 2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033],
  "tolerance": 0.005,
  "candidates": [
    {
      "rank": 1,
      "groups": [
        {
          "red_group": ["Travel - Airfare", "Travel - Lodging", "..."],
          "green_group": ["Travel Services"],
          "per_fy": [
            {"fy": 2024, "red_sum": 1234567.0, "green_sum": 1234580.0, "diff_pct": 0.0000105},
            {"fy": 2025, "red_sum": 1289011.0, "green_sum": 1289220.0, "diff_pct": 0.0000162},
            ...
          ],
          "all_years_within_tol": true,
          "avg_diff_pct": 0.0000128,
          "max_diff_pct": 0.0000201,
          "avg_similarity": 0.71,
          "min_similarity": 0.52,
          "confidence": 0.86,
          "match_type": "many-to-one"
        }
      ],
      "unmatched_red": [],
      "unmatched_green": [],
      "objective": {"k_groups": 5, "total_mismatch_all_fy": 412.0, "sum_similarity": 4.12},
      "all_years_pass": true,
      "years_failing": [],
      "solver_status": "OPTIMAL"
    }
  ]
}
```

`confidence` is a derived scalar in [0,1]: `0.5·(1 − max_diff_pct/tol) + 0.4·avg_similarity + 0.1·all_years_within_tol`. Top-K candidates are produced by repeatedly re-solving the ILP with a no-good cut excluding previously found partitions (CP-SAT solution-enumeration mode), capped at K=5. The `years_failing` list at the candidate level surfaces any FY that exceeded tolerance for any group — empty means the candidate passes the all-years gate.

## 6. Edge cases

- **Unmatchable categories.** Relax "every category assigned" to allow an explicit `unmatched` group with a large objective penalty. Anything that lands there at optimum is surfaced in `unmatched_red` / `unmatched_green` for the user.
- **Ties between equally-valid partitions.** The lexicographic objective resolves most ties; remaining ties are surfaced as additional candidates with identical objective and different group structure (`rank` ties).
- **Disjoint optimal solutions.** Top-K enumeration with no-good cuts naturally produces these.
- **`Other Services` catch-alls.** Flag any red label matching `^Other Services$` (no suffix) as a "residual" category and add a soft preference (small objective bonus) for sending it to a green "General Services"-like residual. Do not hard-code the mapping.
- **K=1 degenerate solution.** Always feasible (the totals reconcile by construction); the K-maximization term ensures the solver only falls back to it when no finer partition is sum-feasible.

## 7. MVP scope vs full

**MVP cut (one week of work):**
- One **APPN** at a time, user-selected in the sidebar. Year diagnostics shown as a strip inside the bucket-review screen.
- Top-1 candidate only, no enumeration.
- **No embeddings** — use a deterministic Jaccard score over tokenized labels as the similarity prior. This drops the heaviest dependency and produces respectable matches because the red/green labels share many tokens ("Travel", "Services", "Personnel").
- CP-SAT with a 5 s timeout per APPN, 0.5% tolerance (loose, to absorb the current generator's per-year jitter), lexicographic (K, mismatch-summed-over-FY) objective.
- Render the output JSON as a two-column Streamlit table with per-group expanders that include a per-FY sum-diff strip.

**Natural next steps, in priority order:**
1. Regenerate green-side data with the explicit per-row rollup so the all-year gate is meaningful at tight tolerance.
2. Swap Jaccard → MiniLM embeddings (one afternoon, biggest quality lift).
3. Top-K enumeration with no-good cuts, ranked candidate UI.
4. Batch mode: solve all APPNs and produce a reconciliation workbook export.
5. Confidence calibration on a labeled subset, surface low-confidence APPNs for human review.
6. Persist user overrides ("force Travel-Fuel to Travel Services") as constraints on the next solve — the ILP framework absorbs this without code restructuring.

The decisive call: **ILP via OR-Tools CP-SAT, per-APPN, with per-FY sum-balance constraints and a lexicographic (max-K, min-mismatch-summed-over-FY, max-similarity) objective**. At N, M ≤ 30 it is fast, exact, and the only formulation that natively expresses "as fine-grained a partition as the sums allow, gated on holding across all years."
