"""Streamlit MVP for budget reconciliation across red-side / green-side datasets.

Run:
    uv run streamlit run ui_reconciliation/app.py

Layout follows research_reconciliation_ui.md: Load -> Overview -> Reconcile ->
Export. Per the 2026-06-09 decisions: hardcoded data paths, long-format
export, force-lock allowed (with required note), default tolerance 1.5%.
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from reconciler import load_pivots, solve_assignment

REPO = Path(__file__).resolve().parents[1]
RED_PATH = REPO / "data" / "synthetic_data_red_side.xlsx"
GREEN_PATH = REPO / "data" / "synthetic_data_green_side.xlsx"

DEFAULT_TOLERANCE_PCT = 1.5  # per Q7 decision (2026-06-09)

st.set_page_config(page_title="Budget Reconciliation MVP", layout="wide")

# ---------------------------------------------------------------------------
# Session state setup
# ---------------------------------------------------------------------------
if "lock_state" not in st.session_state:
    # {appn_title: "locked" | "draft" | None}
    st.session_state["lock_state"] = {}
if "force_notes" not in st.session_state:
    # {appn_title: note_string} for force-locked APPNs
    st.session_state["force_notes"] = {}


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
phase = st.sidebar.radio("Phase", ["Load", "Overview", "Reconcile", "Export"], index=1)
st.sidebar.divider()
tolerance_pct = st.sidebar.slider(
    "Tolerance %", min_value=0.01, max_value=5.0, value=DEFAULT_TOLERANCE_PCT, step=0.01,
    help="Per (bucket, FY) sum-diff tolerance. Cells above this are flagged.",
)
similarity_weight = st.sidebar.slider(
    "Similarity weight", min_value=0, max_value=500, value=100, step=10,
    help="Higher = stronger Jaccard name-similarity tie-breaker.",
)
st.sidebar.caption(
    f"Locked APPNs: "
    f"{sum(1 for s in st.session_state['lock_state'].values() if s == 'locked')}"
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

    # --- Lock / Force-lock controls ---
    appn_all_ok = all(
        all(abs(p["diff_pct"]) <= tolerance_pct for p in g["per_fy"])
        for g in res["groups"]
    )
    current_state = st.session_state["lock_state"].get(selected)
    state_label = current_state or "unlocked"
    st.write(f"**APPN state:** `{state_label}`"
             + (f"  (force-lock note: _{st.session_state['force_notes'].get(selected, '')}_)"
                if current_state == "force_locked" else ""))

    col_a, col_b, col_c = st.columns([1, 1, 2])
    with col_a:
        if appn_all_ok:
            if st.button("Lock APPN", type="primary", use_container_width=True,
                         disabled=current_state in ("locked", "force_locked")):
                st.session_state["lock_state"][selected] = "locked"
                st.session_state["force_notes"].pop(selected, None)
                st.rerun()
        else:
            st.button("Lock APPN", disabled=True, use_container_width=True,
                     help="Disabled because at least one group is out of tolerance. Use Force lock with a note.")
    with col_b:
        force_label = "Force lock" if not appn_all_ok else "Lock anyway"
        if st.button(force_label, use_container_width=True,
                     disabled=current_state in ("locked", "force_locked")):
            st.session_state["__pending_force"] = selected
    with col_c:
        if current_state in ("locked", "force_locked"):
            if st.button("Unlock", use_container_width=True):
                st.session_state["lock_state"].pop(selected, None)
                st.session_state["force_notes"].pop(selected, None)
                st.rerun()

    # Force-lock note dialog (modal-ish via st.session_state)
    if st.session_state.get("__pending_force") == selected:
        with st.form(key="force_lock_form"):
            note = st.text_area(
                "Force-lock note (required) — explain why this APPN is being locked "
                "with groups outside tolerance:",
                value="",
                key="force_lock_note_input",
            )
            submitted = st.form_submit_button("Confirm force-lock")
            if submitted:
                if note.strip():
                    st.session_state["lock_state"][selected] = "force_locked"
                    st.session_state["force_notes"][selected] = note.strip()
                    st.session_state.pop("__pending_force", None)
                    st.rerun()
                else:
                    st.error("A non-empty note is required to force-lock.")

# ---------------------------------------------------------------------------
# Export phase
# ---------------------------------------------------------------------------
elif phase == "Export":
    st.header("Export reconciliation results")
    lock_state = st.session_state["lock_state"]
    force_notes = st.session_state["force_notes"]
    locked_titles = [a for a, s in lock_state.items() if s in ("locked", "force_locked")]
    st.caption(
        f"Locked APPNs: **{len(locked_titles)}** "
        f"(of which **{sum(1 for s in lock_state.values() if s == 'force_locked')}** are force-locked)."
    )

    only_locked = st.checkbox("Export only locked APPNs", value=True)
    if not only_locked:
        # Export everything that has been computed
        all_appns = appn_overview(tolerance_pct)["APPN Title"].tolist()
        titles_to_export = all_appns
    else:
        titles_to_export = locked_titles

    if not titles_to_export:
        st.info("Nothing to export. Lock at least one APPN on the Reconcile screen, or uncheck the filter above.")
        st.stop()

    # Build the long-format rows per Q3 decision
    rows = []
    red_df_full = load_red()
    appn_to_code = (
        red_df_full[["APPN", "APPN Title"]]
        .drop_duplicates()
        .set_index("APPN Title")["APPN"]
        .to_dict()
    )
    with st.status(f"Solving for {len(titles_to_export)} APPN(s)...", expanded=False) as status:
        for appn_title in titles_to_export:
            res = reconcile(appn_title, similarity_weight=similarity_weight)
            state = lock_state.get(appn_title) or "unlocked"
            note = force_notes.get(appn_title, "")
            for g in res["groups"]:
                green_bucket = g["green_bucket"]
                for red_cat in g["red_members"]:
                    for per_fy in g["per_fy"]:
                        fy = per_fy["fy"]
                        # red category's share of group sum in this FY
                        rows.append({
                            "appn": appn_to_code.get(appn_title, ""),
                            "appn_title": appn_title,
                            "fy": fy,
                            "red_cat": red_cat,
                            "green_bucket": green_bucket,
                            "red_group_sum": per_fy["red_sum"],
                            "green_sum": per_fy["green_sum"],
                            "diff_pct": per_fy["diff_pct"],
                            "within_tol": abs(per_fy["diff_pct"]) <= tolerance_pct,
                            "lock_state": state,
                            "force_lock_note": note,
                            "tolerance_pct": tolerance_pct,
                            "similarity_weight": similarity_weight,
                        })
        status.update(label=f"Built {len(rows):,} rows.", state="complete")

    export_df = pd.DataFrame(rows)
    st.subheader("Preview (first 20 rows)")
    st.dataframe(export_df.head(20), use_container_width=True, hide_index=True)
    st.metric("Total rows", f"{len(export_df):,}")

    # Download buttons
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="reconciliation")
    xlsx_bytes = buf.getvalue()

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "Download long-format CSV", data=csv_bytes,
            file_name="reconciliation_long.csv", mime="text/csv",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "Download long-format Excel", data=xlsx_bytes,
            file_name="reconciliation_long.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.caption(
        "Long format per Q3 decision (2026-06-09): one row per "
        "(red category, green bucket, fiscal year). Force-lock notes preserved in the "
        "`force_lock_note` column. Tolerance and similarity-weight settings used for the "
        "solve are stamped on every row."
    )
