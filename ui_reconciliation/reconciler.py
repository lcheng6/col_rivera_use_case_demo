"""Library version of the O&M-AFR reconciler, reusable from the Streamlit app
and from other APPNs.

Public API:
    load_pivots(red_path, green_path, appn_title) -> (red_pivot, green_pivot)
    solve_assignment(red, green, similarity_weight=100, time_limit_s=10, seed=7)
        -> dict (see reconcile_om_afr.py for the schema)
    jaccard(a, b) -> float
"""
from __future__ import annotations

import random
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

DOLLAR_COL = "Dollars (in $K)"
STOPWORDS = {"and", "the", "of", "for", "to", "in", "a", "-", "&"}


def tokens(name: str) -> set[str]:
    s = re.sub(r"[^a-z0-9]+", " ", str(name).lower())
    return {t for t in s.split() if t and t not in STOPWORDS}


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def load_pivots(
    red_path: Path | str, green_path: Path | str, appn_title: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (red_pivot, green_pivot): rows=AFEEIC titles, cols=FYs, values=$K."""
    red_df = pd.read_excel(red_path, sheet_name="Data")
    green_df = pd.read_excel(green_path, sheet_name="Data")
    red_df = red_df[red_df["APPN Title"] == appn_title]
    green_df = green_df[green_df["APPN Title"] == appn_title]
    red = red_df.pivot_table(
        index="AFEEIC Cost Cat Title", columns="Fiscal Year",
        values=DOLLAR_COL, aggfunc="sum", fill_value=0.0,
    )
    green = green_df.pivot_table(
        index="AFEEIC Cost Cat Title", columns="Fiscal Year",
        values=DOLLAR_COL, aggfunc="sum", fill_value=0.0,
    )
    fys = sorted(set(red.columns) | set(green.columns))
    return red.reindex(columns=fys, fill_value=0.0), green.reindex(columns=fys, fill_value=0.0)


def solve_assignment(
    red: pd.DataFrame, green: pd.DataFrame,
    similarity_weight: float = 100, time_limit_s: int = 10,
    seed: int = 7, n_restarts: int = 20,
) -> dict:
    """Find a many-to-one assignment of red->green that minimizes total |diff|
    summed across all (bucket, FY) cells, with Jaccard token similarity as
    tie-breaker. Heuristic: greedy seed + pairwise-swap local search +
    random restarts. Returns a dict with assignment, groups, per-FY
    diagnostics, and timing info."""
    red_cats = list(red.index)
    green_cats = list(green.index)
    fys = list(red.columns)
    N, M, F = len(red_cats), len(green_cats), len(fys)

    red_arr = red.values.astype(float)
    green_arr = green.values.astype(float)

    sim_mat = np.array([[jaccard(r, g) for g in green_cats] for r in red_cats])
    rng = np.random.default_rng(seed)

    def per_fy_diff(assign: np.ndarray) -> np.ndarray:
        out = np.zeros((M, F))
        for k in range(M):
            mask = assign == k
            red_sum = red_arr[mask].sum(axis=0) if mask.any() else np.zeros(F)
            out[k] = np.abs(red_sum - green_arr[k])
        return out

    def total_cost(assign: np.ndarray) -> float:
        return per_fy_diff(assign).sum() - sim_mat[np.arange(N), assign].sum() * similarity_weight

    def local_search(assign: np.ndarray, deadline: float) -> tuple[np.ndarray, float]:
        cost = total_cost(assign)
        improved = True
        while improved and time.time() < deadline:
            improved = False
            for i in range(N):
                cur_k = int(assign[i])
                for k in range(M):
                    if k == cur_k:
                        continue
                    assign[i] = k
                    new_cost = total_cost(assign)
                    if new_cost < cost - 1e-9:
                        cost = new_cost
                        improved = True
                        cur_k = k
                    else:
                        assign[i] = cur_k
        return assign, cost

    deadline = time.time() + time_limit_s

    # Greedy seed: each red to argmax-sim green (tie-broken with tiny jitter).
    sim_jit = sim_mat + rng.uniform(0, 1e-6, sim_mat.shape)
    best_assign = sim_jit.argmax(axis=1)
    best_assign, best_cost = local_search(best_assign.copy(), deadline)
    seed_assign = best_assign.copy()

    iters = 1
    for _ in range(n_restarts):
        if time.time() >= deadline:
            break
        cand = rng.integers(0, M, size=N)
        cand, cost = local_search(cand, deadline)
        iters += 1
        if cost < best_cost:
            best_cost = cost
            best_assign = cand

    assignment = {red_cats[i]: green_cats[int(best_assign[i])] for i in range(N)}
    seed_assignment = {red_cats[i]: green_cats[int(seed_assign[i])] for i in range(N)}

    groups = []
    for k, green_name in enumerate(green_cats):
        red_in_group = [r for r in red_cats if assignment[r] == green_name]
        per_fy = []
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
            max_diff_pct = max(max_diff_pct, abs(diff_pct))
        avg_sim = sum(jaccard(r, green_name) for r in red_in_group) / max(1, len(red_in_group))
        groups.append({
            "green_bucket": green_name,
            "red_members": red_in_group,
            "per_fy": per_fy,
            "max_diff_pct": round(max_diff_pct, 4),
            "avg_similarity": round(avg_sim, 3),
        })

    return {
        "fiscal_years": [int(fy) for fy in fys],
        "n_red_cats": N,
        "n_green_cats": M,
        "assignment": assignment,
        "seed_assignment": seed_assignment,
        "groups": groups,
        "objective_value": best_cost,
        "wall_time_s": round(time.time() - (deadline - time_limit_s), 3),
        "iterations": iters,
    }
