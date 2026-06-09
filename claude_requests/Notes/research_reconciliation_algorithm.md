# Design Memo — Budget Category Reconciliation Across Two Schemes

> Research output from subagent run on 2026-06-09. Recommends the algorithm/logic for the reconciliation MVP. Not yet implemented.

## 1. Problem class

This is a **balanced set-partitioning problem with a sum-equality constraint and a semantic-affinity objective** — equivalently, a **partition-matching** or **two-sided clustering** problem. Within a single `(APPN, Fiscal Year)` bucket the red side gives a vector of N category totals and the green side gives a vector of M category totals with `sum(red) ≈ sum(green)`. We must find a common refinement: an integer K and an assignment of each red category to one of K groups and each green category to one of K groups such that group-wise sums match within tolerance and K is as large as possible (finer groups are more informative).

The closest textbook formulation is the **Generalized Assignment / Set-Partitioning ILP** (Garfinkel & Nemhauser, 1972; Wolsey, *Integer Programming*, 1998, ch. 13). The "match two partitions of equal-mass measures" framing is also a discrete **Optimal Transport** problem (Peyré & Cuturi, *Computational Optimal Transport*, 2019, §2–§4), where the transport plan, after thresholding, induces the bipartite grouping. The "find fewest groups whose sums match" sub-problem is **multiple subset-sum** (Caprara, Kellerer, Pferschy 2000), which is weakly NP-hard but trivially small at N, M ≤ 30.

## 2. Recommended approach for MVP

**Recommendation: a single ILP solved with OR-Tools CP-SAT**, with the objective lexicographically ordered as (i) maximize number of groups K, (ii) minimize total absolute sum-mismatch, (iii) maximize aggregate name-embedding similarity.

**Input:** per `(APPN, FY)`, two pandas Series — `red[name] = dollars`, `green[name] = dollars` — plus a pre-computed `S[i,j]` cosine-similarity matrix from sentence embeddings (see §4).

**Decision variables** (for a fixed upper bound K_max = min(N, M)):
- `x[i,k] ∈ {0,1}` — red category i belongs to group k
- `y[j,k] ∈ {0,1}` — green category j belongs to group k
- `z[k] ∈ {0,1}` — group k is active
- Each row of x and y sums to exactly 1 (every category assigned); `z[k] ≥ x[i,k]`, `z[k] ≥ y[j,k]`.

**Constraints:** for each active group k, `| Σ red[i]·x[i,k] − Σ green[j]·y[j,k] | ≤ tol · max(Σred, Σgreen)` (tolerance default 0.0001).

**Objective (weighted, with weights chosen so terms are lexicographic in practice):**
`maximize  1000·Σ z[k]  −  Σ |mismatch_k|  +  0.1·Σ S[i,j]·x[i,k]·y[j,k]`
The cross-term is linearized by introducing `w[i,j,k] = x[i,k]·y[j,k]` with standard McCormick constraints.

**Output shape:** list of groups, each a `(red_set, green_set, red_sum, green_sum, diff_pct, sim)` tuple.

**Complexity / runtime:** the model has O(K_max·(N+M)) binary vars and O(K_max·N·M) linearization vars. For N=M=30, K_max=30 that's ~27k binaries — well inside CP-SAT's comfort zone. Empirically CP-SAT solves O&M-AF (N=29, M=7) in well under a second; the worst plausible bucket (N=M=30) should finish in 1–5 s with an 8-thread search. We cap solver time at 10 s per bucket and accept the best feasible solution.

**Why CP-SAT over PuLP/CBC or python-mip:** CP-SAT handles the disjunctive structure ("either group k is active or no one is in it") and the lexicographic objective natively via search hints and `AddDecisionStrategy`, and its parallel portfolio is meaningfully faster than CBC on this size.

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
  "fiscal_year": 2025,
  "tolerance": 0.0001,
  "candidates": [
    {
      "rank": 1,
      "groups": [
        {
          "red_group": ["Travel - Airfare", "Travel - Lodging", "..."],
          "green_group": ["Travel Services"],
          "red_sum": 1234567.0,
          "green_sum": 1234580.0,
          "diff_abs": 13.0,
          "diff_pct": 0.0000105,
          "avg_similarity": 0.71,
          "min_similarity": 0.52,
          "confidence": 0.86,
          "match_type": "many-to-one"
        }
      ],
      "unmatched_red": [],
      "unmatched_green": [],
      "objective": {"k_groups": 5, "total_mismatch": 41.0, "sum_similarity": 4.12},
      "solver_status": "OPTIMAL"
    }
  ]
}
```

`confidence` is a derived scalar in [0,1]: `0.5·(1 − diff_pct/tol) + 0.4·avg_similarity + 0.1·(min_similarity > 0.3)`. Top-K candidates are produced by repeatedly re-solving the ILP with a no-good cut excluding previously found partitions (CP-SAT solution-enumeration mode), capped at K=5.

## 6. Edge cases

- **Unmatchable categories.** Relax "every category assigned" to allow an explicit `unmatched` group with a large objective penalty. Anything that lands there at optimum is surfaced in `unmatched_red` / `unmatched_green` for the user.
- **Ties between equally-valid partitions.** The lexicographic objective resolves most ties; remaining ties are surfaced as additional candidates with identical objective and different group structure (`rank` ties).
- **Disjoint optimal solutions.** Top-K enumeration with no-good cuts naturally produces these.
- **`Other Services` catch-alls.** Flag any red label matching `^Other Services$` (no suffix) as a "residual" category and add a soft preference (small objective bonus) for sending it to a green "General Services"-like residual. Do not hard-code the mapping.
- **K=1 degenerate solution.** Always feasible (the totals reconcile by construction); the K-maximization term ensures the solver only falls back to it when no finer partition is sum-feasible.

## 7. MVP scope vs full

**MVP cut (one week of work):**
- One `(APPN, FY)` at a time, user-selected in the sidebar.
- Top-1 candidate only, no enumeration.
- **No embeddings** — use a deterministic Jaccard score over tokenized labels as the similarity prior. This drops the heaviest dependency and produces respectable matches because the red/green labels share many tokens ("Travel", "Services", "Personnel").
- CP-SAT with a 5 s timeout, 0.01% tolerance, lexicographic (K, mismatch) objective.
- Render the output JSON as a two-column Streamlit table with per-group expanders.

**Natural next steps, in priority order:**
1. Swap Jaccard → MiniLM embeddings (one afternoon, biggest quality lift).
2. Top-K enumeration with no-good cuts, ranked candidate UI.
3. Batch mode: solve all `(APPN, FY)` pairs and produce a reconciliation workbook export.
4. Confidence calibration on a labeled subset, surface low-confidence buckets for human review.
5. Persist user overrides ("force Travel-Fuel to Travel Services") as constraints on the next solve — the ILP framework absorbs this without code restructuring.

The decisive call: **ILP via OR-Tools CP-SAT with lexicographic (max-K, min-mismatch, max-similarity) objective**. At N, M ≤ 30 it is fast, exact, and the only formulation that natively expresses "as fine-grained a partition as the sums allow."
