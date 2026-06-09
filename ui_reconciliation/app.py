"""Streamlit MVP for budget reconciliation across red-side / green-side datasets.

Run:
    uv run streamlit run ui_reconciliation/app.py

Layout follows research_reconciliation_ui.md: Load -> Overview -> Reconcile.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from reconciler import load_pivots, solve_assignment

REPO = Path(__file__).resolve().parents[1]
RED_PATH = REPO / "data" / "synthetic_data_red_side.xlsx"
GREEN_PATH = REPO / "data" / "synthetic_data_green_side.xlsx"

st.set_page_config(page_title="Budget Reconciliation MVP", layout="wide")


@st.cache_data(show_spinner="Loading red-side dataset...")
def load_red() -> pd.DataFrame:
    return pd.read_excel(RED_PATH, sheet_name="Data")


@st.cache_data(show_spinner="Loading green-side dataset...")
def load_green() -> pd.DataFrame:
    return pd.read_excel(GREEN_PATH, sheet_name="Data")


@st.cache_data(show_spinner="Running reconciliation for selected APPN...")
def reconcile(appn_title: str, similarity_weight: float) -> dict:
    red, green = load_pivots(RED_PATH, GREEN_PATH, appn_title)
    return solve_assignment(red, green, similarity_weight=similarity_weight, time_limit_s=10)


@st.cache_data(show_spinner="Building APPN overview...")
def appn_overview(tolerance_pct: float) -> pd.DataFrame:
    red = load_red()
    green = load_green()
    appns = (
        red.groupby(["APPN", "APPN Title"])
        .size()
        .reset_index()
        .drop(columns=0)
    )
    rows = []
    for _, r in appns.iterrows():
        appn_title = r["APPN Title"]
        red_om = red[red["APPN Title"] == appn_title]
        green_om = green[green["APPN Title"] == appn_title]
        n_red_cats = red_om["AFEEIC Cost Cat Title"].nunique()
        n_green_cats = green_om["AFEEIC Cost Cat Title"].nunique()
        avg_red_k = red_om["Dollars (in $K)"].sum() / 10
        # Solve to compute "years within tolerance"
        try:
            res = reconcile(appn_title, similarity_weight=100)
            n_years = len(res["fiscal_years"])
            # For each FY: every group must be within tol for that FY to count
            years_pass = 0
            for f_idx in range(n_years):
                ok = True
                for g in res["groups"]:
                    if abs(g["per_fy"][f_idx]["diff_pct"]) > tolerance_pct:
                        ok = False
                        break
                if ok:
                    years_pass += 1
            rows.append({
                "APPN": r["APPN"],
                "APPN Title": appn_title,
                "Red cats": n_red_cats,
                "Green cats": n_green_cats,
                "Avg $K/yr": round(avg_red_k, 0),
                "Years passing": f"{years_pass}/{n_years}",
                "_years_pass": years_pass,
                "_years_total": n_years,
            })
        except Exception as e:
            rows.append({
                "APPN": r["APPN"],
                "APPN Title": appn_title,
                "Red cats": n_red_cats,
                "Green cats": n_green_cats,
                "Avg $K/yr": round(avg_red_k, 0),
                "Years passing": f"err: {type(e).__name__}",
                "_years_pass": 0,
                "_years_total": 10,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sidebar nav
# ---------------------------------------------------------------------------
st.sidebar.title("Budget Reconciliation")
phase = st.sidebar.radio("Phase", ["Load", "Overview", "Reconcile"], index=1)
st.sidebar.divider()
tolerance_pct = st.sidebar.slider(
    "Tolerance %", min_value=0.01, max_value=5.0, value=0.5, step=0.01,
    help="Per (bucket, FY) sum-diff tolerance. Cells above this are flagged.",
)
similarity_weight = st.sidebar.slider(
    "Similarity weight", min_value=0, max_value=500, value=100, step=10,
    help="Higher = stronger Jaccard name-similarity tie-breaker.",
)


# ---------------------------------------------------------------------------
# Load phase
# ---------------------------------------------------------------------------
if phase == "Load":
    st.header("Load datasets")
    st.write(f"**Red side (granular):** `{RED_PATH.relative_to(REPO)}`")
    st.write(f"**Green side (rolled-up):** `{GREEN_PATH.relative_to(REPO)}`")
    if RED_PATH.exists() and GREEN_PATH.exists():
        red = load_red()
        green = load_green()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Red rows", f"{len(red):,}")
            st.metric("Red AFEEIC categories (across all APPNs)",
                      red["AFEEIC Cost Cat Title"].nunique())
        with col2:
            st.metric("Green rows", f"{len(green):,}")
            st.metric("Green AFEEIC categories (across all APPNs)",
                      green["AFEEIC Cost Cat Title"].nunique())
        st.success("Datasets loaded. Switch to **Overview** in the sidebar to see per-APPN status.")
    else:
        st.error("One of the data files is missing.")

# ---------------------------------------------------------------------------
# Overview phase
# ---------------------------------------------------------------------------
elif phase == "Overview":
    st.header("APPN overview")
    st.caption(
        "Each row is one APPN. The reconciler is run on each APPN and the "
        "number of fiscal years passing the tolerance gate is reported. "
        "Click an APPN below to drill into its grouping."
    )
    df = appn_overview(tolerance_pct)
    st.dataframe(
        df.drop(columns=["_years_pass", "_years_total"]),
        use_container_width=True, hide_index=True,
    )
    appn_choices = df["APPN Title"].tolist()
    selected = st.selectbox("Drill into APPN:", ["—"] + appn_choices)
    if selected != "—":
        st.session_state["selected_appn"] = selected
        st.info(f"Selected **{selected}** — switch to **Reconcile** to view groupings.")

# ---------------------------------------------------------------------------
# Reconcile phase
# ---------------------------------------------------------------------------
elif phase == "Reconcile":
    selected = st.session_state.get("selected_appn")
    if not selected:
        st.warning("No APPN selected. Go to **Overview** and pick one.")
        st.stop()

    st.header(f"Reconcile: {selected}")
    res = reconcile(selected, similarity_weight=similarity_weight)

    n_pass = sum(
        1 for g in res["groups"]
        if all(abs(p["diff_pct"]) <= tolerance_pct for p in g["per_fy"])
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Red categories", res["n_red_cats"])
    col2.metric("Green buckets", res["n_green_cats"])
    col3.metric("Buckets within tol", f"{n_pass}/{res['n_green_cats']}")
    overall_max = max(g["max_diff_pct"] for g in res["groups"])
    col4.metric("Overall max |diff%|", f"{overall_max:.4f}%")
    st.caption(
        f"Heuristic solver: {res['iterations']} restarts, "
        f"wall {res['wall_time_s']}s, objective {res['objective_value']:.1f}"
    )

    for g in res["groups"]:
        all_ok = all(abs(p["diff_pct"]) <= tolerance_pct for p in g["per_fy"])
        badge = "PASS" if all_ok else "FAIL"
        color = "green" if all_ok else "red"
        with st.expander(
            f":{color}[{badge}]  **{g['green_bucket']}**   "
            f"({len(g['red_members'])} red members, max |diff%| {g['max_diff_pct']:.4f}%, "
            f"avg sim {g['avg_similarity']:.3f})",
            expanded=not all_ok,
        ):
            left, right = st.columns([2, 3])
            with left:
                st.write("**Red members:**")
                for r in sorted(g["red_members"]):
                    st.write(f"- {r}")
            with right:
                fy_df = pd.DataFrame(g["per_fy"])
                fy_df["pass"] = fy_df["diff_pct"].abs() <= tolerance_pct
                st.dataframe(
                    fy_df[["fy", "red_sum", "green_sum", "diff_abs", "diff_pct", "pass"]],
                    use_container_width=True, hide_index=True,
                )

    st.divider()
    st.caption(
        "MVP scaffold — no editing affordances yet. Edit + lock affordances "
        "land in v1 per `claude_requests/Notes/research_reconciliation_ui.md`."
    )
