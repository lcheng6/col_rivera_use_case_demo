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
    seed: int = 7, n_restarts: int = 60,
) -> dict:
    """Find a many-to-one assignment of red->green that minimizes total |diff|
    summed across all (bucket, FY) cells, with Jaccard token similarity as
    tie-breaker.

    Heuristic: greedy/random seed → 1-move local search → 2-opt pair-swap →
    repeat to fixpoint, with multiple restarts. Returns a dict with
    assignment, groups, per-FY diagnostics, and timing info."""
    red_cats = list(red.index)
    green_cats = list(green.index)
    fys = list(red.columns)
    N, M, F = len(red_cats), len(green_cats), len(fys)

    red_arr = red.values.astype(float)
    green_arr = green.values.astype(float)

    sim_mat = np.array([[jaccard(r, g) for g in green_cats] for r in red_cats])
    rng = np.random.default_rng(seed)

    def bucket_sums(assign: np.ndarray) -> np.ndarray:
        """Vectorized: rows = M buckets, cols = F fys, values = sum of red[i,fy] for i in bucket."""
        # Use np.add.at for grouped sum
        out = np.zeros((M, F))
        np.add.at(out, assign, red_arr)
        return out

    def total_cost_from_sums(sums: np.ndarray, assign: np.ndarray) -> float:
        return np.abs(sums - green_arr).sum() - sim_mat[np.arange(N), assign].sum() * similarity_weight

    def total_cost(assign: np.ndarray) -> float:
        return total_cost_from_sums(bucket_sums(assign), assign)

    def one_move_pass(assign: np.ndarray) -> bool:
        """Try reassigning each red i to a different bucket; commit best.
        Returns True if any improvement was made."""
        sums = bucket_sums(assign)
        cost = total_cost_from_sums(sums, assign)
        improved_any = False
        for i in range(N):
            cur_k = int(assign[i])
            # try each alternative k
            best_k = cur_k
            best_new_cost = cost
            for k in range(M):
                if k == cur_k:
                    continue
                # incremental sums update: remove red_arr[i] from cur_k, add to k
                new_sums_cur_k = sums[cur_k] - red_arr[i]
                new_sums_k = sums[k] + red_arr[i]
                # delta in |diff|:
                delta = (
                    np.abs(new_sums_cur_k - green_arr[cur_k]).sum()
                    - np.abs(sums[cur_k] - green_arr[cur_k]).sum()
                    + np.abs(new_sums_k - green_arr[k]).sum()
                    - np.abs(sums[k] - green_arr[k]).sum()
                )
                # delta in similarity (we subtract similarity * weight in cost)
                sim_delta = -similarity_weight * (sim_mat[i, k] - sim_mat[i, cur_k])
                new_cost = cost + delta + sim_delta
                if new_cost < best_new_cost - 1e-9:
                    best_new_cost = new_cost
                    best_k = k
            if best_k != cur_k:
                # commit
                sums[cur_k] -= red_arr[i]
                sums[best_k] += red_arr[i]
                assign[i] = best_k
                cost = best_new_cost
                improved_any = True
        return improved_any

    def two_opt_swap_pass(assign: np.ndarray) -> bool:
        """Try swapping the bucket assignment of pairs (i, j) where i and j
        are in different buckets. This escapes local minima the 1-move pass
        can't, because a single move forces the bucket sums to jump by red_arr[i]
        but a swap keeps the change small (delta = red[i] - red[j])."""
        sums = bucket_sums(assign)
        cost = total_cost_from_sums(sums, assign)
        improved_any = False
        # Iterate over (i, j) with i < j, only if assign[i] != assign[j]
        for i in range(N):
            ki = int(assign[i])
            for j in range(i + 1, N):
                kj = int(assign[j])
                if ki == kj:
                    continue
                # After swap: i goes to kj, j goes to ki
                new_sums_ki = sums[ki] - red_arr[i] + red_arr[j]
                new_sums_kj = sums[kj] - red_arr[j] + red_arr[i]
                delta = (
                    np.abs(new_sums_ki - green_arr[ki]).sum()
                    - np.abs(sums[ki] - green_arr[ki]).sum()
                    + np.abs(new_sums_kj - green_arr[kj]).sum()
                    - np.abs(sums[kj] - green_arr[kj]).sum()
                )
                sim_delta = -similarity_weight * (
                    sim_mat[i, kj] - sim_mat[i, ki]
                    + sim_mat[j, ki] - sim_mat[j, kj]
                )
                new_cost = cost + delta + sim_delta
                if new_cost < cost - 1e-9:
                    sums[ki] = new_sums_ki
                    sums[kj] = new_sums_kj
                    assign[i] = kj
                    assign[j] = ki
                    ki = kj  # i's new bucket
                    cost = new_cost
                    improved_any = True
        return improved_any

    def three_opt_rotation_pass(assign: np.ndarray) -> bool:
        """Try rotating triples (i, j, l) where each is in a different bucket.
        Two rotations possible per triple: (i->kj, j->kl, l->ki) and (i->kl, j->ki, l->kj).
        Catches the case where 1-move and 2-opt are stuck in a local minimum
        that requires reshuffling three items simultaneously."""
        sums = bucket_sums(assign)
        cost = total_cost_from_sums(sums, assign)
        improved_any = False
        for i in range(N):
            ki = int(assign[i])
            for j in range(i + 1, N):
                kj = int(assign[j])
                if kj == ki:
                    continue
                for l in range(j + 1, N):
                    kl = int(assign[l])
                    if kl == ki or kl == kj:
                        continue
                    # Rotation A: i->kj, j->kl, l->ki
                    sa_ki = sums[ki] - red_arr[i] + red_arr[l]
                    sa_kj = sums[kj] - red_arr[j] + red_arr[i]
                    sa_kl = sums[kl] - red_arr[l] + red_arr[j]
                    delta_a = (
                        np.abs(sa_ki - green_arr[ki]).sum() - np.abs(sums[ki] - green_arr[ki]).sum()
                        + np.abs(sa_kj - green_arr[kj]).sum() - np.abs(sums[kj] - green_arr[kj]).sum()
                        + np.abs(sa_kl - green_arr[kl]).sum() - np.abs(sums[kl] - green_arr[kl]).sum()
                    )
                    sim_delta_a = -similarity_weight * (
                        sim_mat[i, kj] - sim_mat[i, ki]
                        + sim_mat[j, kl] - sim_mat[j, kj]
                        + sim_mat[l, ki] - sim_mat[l, kl]
                    )
                    # Rotation B: i->kl, j->ki, l->kj
                    sb_ki = sums[ki] - red_arr[i] + red_arr[j]
                    sb_kj = sums[kj] - red_arr[j] + red_arr[l]
                    sb_kl = sums[kl] - red_arr[l] + red_arr[i]
                    delta_b = (
                        np.abs(sb_ki - green_arr[ki]).sum() - np.abs(sums[ki] - green_arr[ki]).sum()
                        + np.abs(sb_kj - green_arr[kj]).sum() - np.abs(sums[kj] - green_arr[kj]).sum()
                        + np.abs(sb_kl - green_arr[kl]).sum() - np.abs(sums[kl] - green_arr[kl]).sum()
                    )
                    sim_delta_b = -similarity_weight * (
                        sim_mat[i, kl] - sim_mat[i, ki]
                        + sim_mat[j, ki] - sim_mat[j, kj]
                        + sim_mat[l, kj] - sim_mat[l, kl]
                    )
                    new_cost_a = cost + delta_a + sim_delta_a
                    new_cost_b = cost + delta_b + sim_delta_b
                    if new_cost_a < cost - 1e-9 and new_cost_a <= new_cost_b:
                        sums[ki], sums[kj], sums[kl] = sa_ki, sa_kj, sa_kl
                        assign[i], assign[j], assign[l] = kj, kl, ki
                        ki, kj, kl = kj, kl, ki
                        cost = new_cost_a
                        improved_any = True
                    elif new_cost_b < cost - 1e-9:
                        sums[ki], sums[kj], sums[kl] = sb_ki, sb_kj, sb_kl
                        assign[i], assign[j], assign[l] = kl, ki, kj
                        ki, kj, kl = kl, ki, kj
                        cost = new_cost_b
                        improved_any = True
        return improved_any

    def local_search(assign: np.ndarray, deadline: float) -> tuple[np.ndarray, float]:
        # Alternate 1-move, 2-opt, and (occasionally) 3-opt until none improve.
        # 3-opt is O(N^3) so we only run it when 1-move and 2-opt have stalled.
        while time.time() < deadline:
            moved = one_move_pass(assign)
            if time.time() >= deadline:
                break
            swapped = two_opt_swap_pass(assign)
            if time.time() >= deadline:
                break
            if not moved and not swapped:
                # try the heavier 3-opt to escape
                rotated = three_opt_rotation_pass(assign)
                if not rotated:
                    break
        return assign, total_cost(assign)

    def kick_and_search(start_assign: np.ndarray, deadline: float, kicks: int = 10) -> tuple[np.ndarray, float]:
        """LKH-style diversification: from a local optimum, randomly reassign
        K items and re-run local search. Repeat until no further improvement
        or out of kicks/time."""
        cur, cur_cost = local_search(start_assign.copy(), deadline)
        best_cur = cur.copy()
        best_cur_cost = cur_cost
        for _ in range(kicks):
            if time.time() >= deadline:
                break
            # Perturb: reassign ~25% of items to random buckets (or all of them when N is tiny)
            n_perturb = min(N, max(2, N // 4))
            perturb_idx = rng.choice(N, size=n_perturb, replace=False)
            cand = best_cur.copy()
            cand[perturb_idx] = rng.integers(0, M, size=n_perturb)
            cand, cand_cost = local_search(cand, deadline)
            if cand_cost < best_cur_cost - 1e-9:
                best_cur = cand
                best_cur_cost = cand_cost
        return best_cur, best_cur_cost

    deadline = time.time() + time_limit_s

    # Greedy seed: each red to argmax-sim green (tie-broken with tiny jitter).
    sim_jit = sim_mat + rng.uniform(0, 1e-6, sim_mat.shape)
    best_assign, best_cost = kick_and_search(sim_jit.argmax(axis=1), deadline, kicks=15)
    seed_assign = best_assign.copy()

    iters = 1
    for _ in range(n_restarts):
        if time.time() >= deadline:
            break
        cand = rng.integers(0, M, size=N)
        cand, cost = kick_and_search(cand, deadline, kicks=5)
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
