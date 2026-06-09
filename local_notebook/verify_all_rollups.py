"""Run the heuristic reconciler against every APPN and report whether the
recovered assignment matches the ground-truth rollup defined in
`regenerate_all_green.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ui_reconciliation"))

from reconciler import load_pivots, solve_assignment  # noqa: E402

from regenerate_all_green import ROLLUPS  # noqa: E402


def verify_one(appn_title: str, tolerance_pct: float = 0.01) -> dict:
    red, green = load_pivots(
        REPO / "data" / "synthetic_data_red_side.xlsx",
        REPO / "data" / "synthetic_data_green_side.xlsx",
        appn_title,
    )
    if red.empty or green.empty:
        return {"appn": appn_title, "ok": False, "reason": "empty pivot"}

    res = solve_assignment(red, green, similarity_weight=100, time_limit_s=10)
    overall_max = max(g["max_diff_pct"] for g in res["groups"])
    all_within = overall_max <= tolerance_pct

    # Compare recovered assignment to ground truth
    truth, _ = ROLLUPS[appn_title]
    recovered = res["assignment"]
    matches = sum(1 for r, gold in truth.items() if recovered.get(r) == gold)
    total = len(truth)

    return {
        "appn": appn_title,
        "red_n": res["n_red_cats"],
        "green_n": res["n_green_cats"],
        "max_diff_pct": round(overall_max, 5),
        "within_tol": all_within,
        "assignment_correct": f"{matches}/{total}",
        "fully_correct": matches == total,
        "wall_s": res["wall_time_s"],
    }


def main():
    rows = []
    for appn in ROLLUPS:
        rows.append(verify_one(appn))
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print()
    fully = df["fully_correct"].sum()
    within = df["within_tol"].sum()
    print(f"Fully-correct rollups: {fully}/{len(df)}")
    print(f"Within 0.01% tolerance: {within}/{len(df)}")


if __name__ == "__main__":
    main()
