"""Reconcile O&M-AFR category groupings between red-side and green-side.

Implements the per-APPN reconciler described in
`claude_requests/Notes/research_reconciliation_algorithm.md`.

Problem statement for Operation and Maintenance - AFR (APPN 3740):
- Red side has 29 detailed AFEEIC Cost Cat Titles.
- Green side has 5 broader AFEEIC Cost Cat Titles.
- Find an assignment of each red category to exactly one green bucket
  (many-to-one: 29 -> 5) such that for EVERY fiscal year, the sum of
  red dollars assigned to bucket k matches the green bucket k dollars
  within tolerance.

Adds a name-similarity prior (Jaccard token overlap) used as a tie-breaker.

Usage:
    uv run python local_notebook/reconcile_om_afr.py [--tolerance 0.5]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
APPN_TITLE = "Operation and Maintenance - AFR"
DOLLAR_COL = "Dollars (in $K)"

# Token stopwords for Jaccard name-similarity.
STOPWORDS = {"and", "the", "of", "for", "to", "in", "a", "-", "&"}


def tokens(name: str) -> set[str]:
    s = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return {t for t in s.split() if t and t not in STOPWORDS}


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def load_pivots(red_path: Path, green_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (red_pivot, green_pivot): rows=categories, cols=fiscal years, values=$K."""
    red_df = pd.read_excel(red_path, sheet_name="Data")
    green_df = pd.read_excel(green_path, sheet_name="Data")
    red_df = red_df[red_df["APPN Title"] == APPN_TITLE]
    green_df = green_df[green_df["APPN Title"] == APPN_TITLE]
    red = red_df.pivot_table(
        index="AFEEIC Cost Cat Title", columns="Fiscal Year",
        values=DOLLAR_COL, aggfunc="sum", fill_value=0.0,
    )
    green = green_df.pivot_table(
        index="AFEEIC Cost Cat Title", columns="Fiscal Year",
        values=DOLLAR_COL, aggfunc="sum", fill_value=0.0,
    )
    # Make sure both have the same FY columns.
    fys = sorted(set(red.columns) | set(green.columns))
    return red.reindex(columns=fys, fill_value=0.0), green.reindex(columns=fys, fill_value=0.0)


def solve_assignment(
    red: pd.DataFrame, green: pd.DataFrame, tolerance_pct: float,
    time_limit_s: int = 30, similarity_weight: float = 100,
) -> dict:
    """Solve the many-to-one assignment ILP.

    Each red category i is assigned to exactly one green bucket k. The
    objective minimizes the SUM of absolute per-(bucket, FY) sum-diffs,
    with a tie-breaker reward for high name-similarity matches. This is
    always feasible; `tolerance_pct` is reported in the result as a
    target but does not gate the solve.
    """
    red_cats = list(red.index)
    green_cats = list(green.index)
    fys = list(red.columns)
    N, M, F = len(red_cats), len(green_cats), len(fys)

    red_arr = red.values.astype(float)     # shape (N, F)
    green_arr = green.values.astype(float) # shape (M, F)

    # Similarity matrix S[i,j] in [0,1]
    sim_mat = np.array([[jaccard(r, g) for g in green_cats] for r in red_cats])

    rng = np.random.default_rng(7)

    def per_fy_diff(assign: np.ndarray) -> np.ndarray:
        """Given assign[i] = k, return |red_sum - green| matrix shape (M, F)."""
        out = np.zeros((M, F))
        for k in range(M):
            mask = assign == k
            red_sum = red_arr[mask].sum(axis=0) if mask.any() else np.zeros(F)
            out[k] = np.abs(red_sum - green_arr[k])
        return out

    def total_cost(assign: np.ndarray) -> float:
        diff_cost = per_fy_diff(assign).sum()
        sim_bonus = sim_mat[np.arange(N), assign].sum() * similarity_weight
        return diff_cost - sim_bonus

    # Initial assignment: each red to its highest-similarity green bucket
    # (with ties broken randomly).
    sim_jittered = sim_mat + rng.uniform(0, 1e-6, sim_mat.shape)
    assign = sim_jittered.argmax(axis=1)

    # Pairwise-swap local search until no improvement (or time budget).
    import time as _time
    t0 = _time.time()
    cur_cost = total_cost(assign)
    improved = True
    iters = 0
    while improved and (_time.time() - t0) < time_limit_s:
        improved = False
        iters += 1
        # Try every (i, k) move (assign red i to bucket k != current)
        for i in range(N):
            cur_k = int(assign[i])
            for k in range(M):
                if k == cur_k:
                    continue
                assign[i] = k
                new_cost = total_cost(assign)
                if new_cost < cur_cost - 1e-9:
                    cur_cost = new_cost
                    improved = True
                    cur_k = k
                else:
                    assign[i] = cur_k

    # Random-restart: try a handful of random initializations + same local search
    best_assign = assign.copy()
    best_cost = cur_cost
    for restart in range(20):
        if _time.time() - t0 > time_limit_s:
            break
        cand = rng.integers(0, M, size=N)
        cost = total_cost(cand)
        improved = True
        while improved and (_time.time() - t0) < time_limit_s:
            improved = False
            for i in range(N):
                cur_k = int(cand[i])
                for k in range(M):
                    if k == cur_k:
                        continue
                    cand[i] = k
                    new_cost = total_cost(cand)
                    if new_cost < cost - 1e-9:
                        cost = new_cost
                        improved = True
                        cur_k = k
                    else:
                        cand[i] = cur_k
        if cost < best_cost:
            best_cost = cost
            best_assign = cand.copy()

    wall_time = _time.time() - t0
    status_name = "OPTIMAL_HEURISTIC"
    assignment = {red_cats[i]: green_cats[int(best_assign[i])] for i in range(N)}

    # Build per-bucket per-FY diagnostic
    groups = []
    for k, green_name in enumerate(green_cats):
        red_in_group = [r for r in red_cats if assignment[r] == green_name]
        per_fy = []
        all_within = True
        max_diff_pct = 0.0
        for f_idx, fy in enumerate(fys):
            red_sum = float(sum(red.loc[r, fy] for r in red_in_group))
            green_amt = float(green.loc[green_name, fy])
            diff = red_sum - green_amt
            diff_pct = (diff / green_amt * 100.0) if green_amt else 0.0
            per_fy.append({
                "fy": int(fy),
                "red_sum": round(red_sum, 2),
                "green_sum": round(green_amt, 2),
                "diff_abs": round(diff, 2),
                "diff_pct": round(diff_pct, 4),
            })
            if abs(diff_pct) > tolerance_pct:
                all_within = False
            max_diff_pct = max(max_diff_pct, abs(diff_pct))
        avg_sim = (
            sum(jaccard(r, green_name) for r in red_in_group) / max(1, len(red_in_group))
        )
        groups.append({
            "green_bucket": green_name,
            "red_members": red_in_group,
            "per_fy": per_fy,
            "all_within_tol": all_within,
            "max_diff_pct": round(max_diff_pct, 4),
            "avg_similarity": round(avg_sim, 3),
        })

    return {
        "status": status_name,
        "tolerance_pct": tolerance_pct,
        "appn_title": APPN_TITLE,
        "fiscal_years": [int(fy) for fy in fys],
        "n_red_cats": N,
        "n_green_cats": M,
        "assignment": assignment,
        "groups": groups,
        "objective_value": best_cost,
        "wall_time_s": round(wall_time, 3),
        "iterations": iters,
    }


def print_report(result: dict) -> None:
    if result["status"] not in ("OPTIMAL", "FEASIBLE", "OPTIMAL_HEURISTIC"):
        print(f"Solver status: {result['status']} at tolerance {result['tolerance_pct']:.2f}%")
        return

    print(f"=== Reconciliation Result for {result['appn_title']} ===")
    print(f"Solver: {result['status']}   wall time: {result['wall_time_s']}s   iters: {result.get('iterations', '?')}")
    print(f"Reporting tolerance: {result['tolerance_pct']:.2f}%   "
          f"Red categories: {result['n_red_cats']}   Green buckets: {result['n_green_cats']}")
    print(f"Objective (sum |diff| in $K, minus similarity*weight): {result['objective_value']:.1f}")
    print()

    fys = result["fiscal_years"]
    for group in result["groups"]:
        flag = "PASS" if group["all_within_tol"] else "FAIL"
        print(f"--- Green bucket: {group['green_bucket']}   [{flag}]")
        print(f"    {len(group['red_members'])} red categories assigned")
        print(f"    avg similarity: {group['avg_similarity']:.3f}   "
              f"max |diff%|: {group['max_diff_pct']:.4f}%")
        print(f"    Red members:")
        for r in sorted(group["red_members"]):
            print(f"      - {r}")
        print(f"    Per-FY sum-diff:")
        print(f"      {'FY':>6} {'red $K':>14} {'green $K':>14} {'diff $K':>12} {'diff %':>10}")
        for row in group["per_fy"]:
            status_mark = "OK" if abs(row["diff_pct"]) <= result["tolerance_pct"] else "OVER"
            print(f"      {row['fy']:>6} {row['red_sum']:>14,.1f} {row['green_sum']:>14,.1f} "
                  f"{row['diff_abs']:>12,.1f} {row['diff_pct']:>9.4f}%  {status_mark}")
        print()

    total_pass = sum(1 for g in result["groups"] if g["all_within_tol"])
    print(f"Buckets fully within tolerance: {total_pass}/{len(result['groups'])}")
    overall_max = max(g["max_diff_pct"] for g in result["groups"])
    print(f"Overall max |diff%| across all (bucket, FY): {overall_max:.4f}%")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tolerance", type=float, default=0.5,
                        help="Reporting tolerance percent (default 0.5). Buckets/years exceeding this are flagged in the report; the solver always returns the assignment that minimizes total |diff|.")
    parser.add_argument("--time-limit", type=int, default=30)
    parser.add_argument("--similarity-weight", type=float, default=100,
                        help="Weight of name-similarity in the objective (default 100). 0 = pure sum-balance.")
    args = parser.parse_args()

    red, green = load_pivots(
        REPO / "data" / "synthetic_data_red_side.xlsx",
        REPO / "data" / "synthetic_data_green_side.xlsx",
    )

    print(f"=== Solving for {APPN_TITLE} ===")
    print(f"  red categories: {len(red)}   green categories: {len(green)}   FYs: {len(red.columns)}")
    result = solve_assignment(
        red, green, args.tolerance,
        time_limit_s=args.time_limit,
        similarity_weight=args.similarity_weight,
    )
    print()
    print_report(result)


if __name__ == "__main__":
    main()
