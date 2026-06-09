"""Regenerate ONLY the O&M-AFR rows on the green-side dataset using an explicit
per-row rollup from air-gapped AFEEIC Cost Cat Titles to the 5 open-system
buckets. This makes the (open-bucket, FY) sums year-stable so the
reconciliation algorithm has a defensible target to recover.

Per `claude_requests/Notes/solution_notes_for_reconciliation.md` table.
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd

import create_synthetic_data as ag  # for shared lookup tables

REPO = Path(__file__).resolve().parents[1]
APPN_TITLE = "Operation and Maintenance - AFR"
SEED = 314159
JITTER_PCT = 0.005  # ±0.005% per (open-bucket, FY) so values don't tie exactly

# Air-gapped AFEEIC Cost Cat Title -> open-system bucket (5 buckets for O&M-AFR)
OM_AFR_ROLLUP = {
    # Personnel Services (5 items - education/development costs)
    "Other Services - Other General Training":            "Personnel Services",
    "Other Services - Education":                         "Personnel Services",
    "Other Services - Tuition Assistance":                "Personnel Services",
    "Other Services - Professional Education":            "Personnel Services",
    "Other Services - Continued Education":               "Personnel Services",
    # Travel Services (15 items - all travel)
    "Travel Expenses":                                    "Travel Services",
    "Travel - Airfare":                                   "Travel Services",
    "Travel - Train":                                     "Travel Services",
    "Travel - Rental Cars":                               "Travel Services",
    "Travel - Mileage Reimbursement":                     "Travel Services",
    "Travel - Rideshare/Taxi":                            "Travel Services",
    "Travel - Fuel":                                      "Travel Services",
    "Travel - Lodging":                                   "Travel Services",
    "Travel - Lodging Incidentals":                       "Travel Services",
    "Travel - Meals":                                     "Travel Services",
    "Travel - Meal Tips":                                 "Travel Services",
    "Travel - Conference and Events":                     "Travel Services",
    "Travel - Workshop and Training":                     "Travel Services",
    "Travel - Communication":                             "Travel Services",
    "Travel - Baggage Fees":                              "Travel Services",
    # Mission Support Contracts (3 items)
    "Engineering Technical Services":                          "Mission Support Contracts",
    "IT Contracting Services":                                 "Mission Support Contracts",
    "Other Services - Acquisition and Non-Acquisition Support":"Mission Support Contracts",
    # Facilities and Logistics (3 items)
    "Fuel":                                               "Facilities and Logistics",
    "Postal":                                             "Facilities and Logistics",
    "Software Depot":                                     "Facilities and Logistics",
    # General Services (3 items)
    "Other Services":                                     "General Services",
    "Other Services - Chaplain Support":                  "General Services",
    "Other Services - In Country Support Cost":           "General Services",
}

# AFEEIC codes for the 5 open buckets (match create_open_system_data.py).
OPEN_BUCKET_CODES = {
    "Personnel Services":        "OR01",
    "Travel Services":           "OR02",
    "Mission Support Contracts": "OR03",
    "Facilities and Logistics":  "OR04",
    "General Services":          "OR05",
}

OPEN_CE_BY_AFEEIC = {
    "Personnel Services":        ["Civilian Salaries (Open)", "Civilian Benefits (Open)", "Overtime - Open"],
    "Travel Services":           ["Travel - Transport (Open)", "Travel - Lodging (Open)", "Travel - Per Diem (Open)", "Travel - Misc (Open)"],
    "Mission Support Contracts": ["A&AS Mission Support", "Engineering Services Contract", "Studies and Analysis Contract"],
    "Facilities and Logistics":  ["Facility Sustainment", "Fuel Distribution", "Postal Operations", "Software Operations"],
    "General Services":          ["Chaplain Operations", "In-Country Support", "Other General Services"],
}


def regenerate_om_afr_rows(red_path: Path, seed: int) -> pd.DataFrame:
    """Read red-side O&M-AFR, roll up to open buckets per (bucket, FY) totals
    with tiny jitter, and emit line-item rows for the green side."""
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    red = pd.read_excel(red_path, sheet_name="Data")
    om_red = red[red["APPN Title"] == APPN_TITLE].copy()
    if om_red.empty:
        raise RuntimeError(f"No rows for APPN Title = {APPN_TITLE!r} in {red_path}")

    # Verify every air-gapped AFEEIC label is covered by the rollup
    red_cats = set(om_red["AFEEIC Cost Cat Title"].unique())
    missing = red_cats - set(OM_AFR_ROLLUP)
    if missing:
        raise RuntimeError(f"Rollup missing for: {sorted(missing)}")

    om_red["open_bucket"] = om_red["AFEEIC Cost Cat Title"].map(OM_AFR_ROLLUP)
    bucket_fy_totals = (
        om_red.groupby(["open_bucket", "Fiscal Year"])["Dollars (in $K)"]
        .sum()
        .reset_index()
    )

    # Apply small jitter so green doesn't tie air-gapped exactly
    bucket_fy_totals["jittered_K"] = bucket_fy_totals["Dollars (in $K)"] * (
        1.0 + np_rng.uniform(-JITTER_PCT, JITTER_PCT, size=len(bucket_fy_totals)) / 100.0
    )

    appn_meta = ag.APPN_TABLE[APPN_TITLE]
    appn_code = appn_meta["appn"]
    afp_cat = appn_meta["afp_cat"]
    component = "AFR"

    ba_options = ag.BA_TABLE[APPN_TITLE]

    rows = []
    for _, b in bucket_fy_totals.iterrows():
        bucket = b["open_bucket"]
        fy = int(b["Fiscal Year"])
        bucket_total_k = float(b["jittered_K"])
        afeeic_code = OPEN_BUCKET_CODES[bucket]
        ce_options = OPEN_CE_BY_AFEEIC[bucket]

        # Split the bucket-FY total across a handful of line items via Dirichlet.
        # Number of lines scales with sqrt of total.
        n_lines = max(2, min(10, int(np.round(np.sqrt(bucket_total_k / 250.0)))))
        weights = np_rng.dirichlet(np.ones(n_lines) * 1.5)
        line_dollars = bucket_total_k * weights

        for line_k in line_dollars:
            ba_code, ba_name = rng.choice(ba_options)
            bsa_options = ag.BSA_TABLE.get(ba_name, [(ba_code + "0", ba_name + " - General")])
            bsa_code, bsa_title = rng.choice(bsa_options)

            bpac_seq = rng.randint(1, 99)
            bpac_code = f"{appn_code[:4]}{bsa_code}{bpac_seq:02d}"
            bpac_modifier = rng.choice(["Operations", "Sustainment", "Modernization", "Support", "Readiness"])
            bpac_title = f"{bsa_title} - {bpac_modifier}"
            ce_title = rng.choice(ce_options)

            # O&M -> OP-32 lines apply
            op32_code, op32_sub, op32_title, _ = rng.choice(ag.OP32_TABLE)

            afpec_base, afpec_program = rng.choice(ag.AFPEC_BASES)
            afpec = f"{afpec_base}R"

            oac_code = rng.choice(ag.OAC_BY_COMPONENT[component])
            oac_title = dict(ag.OAC_TABLE)[oac_code]
            wsc_code, wsc_title = rng.choice(ag.WSC_TABLE)
            oco_ops_code, oco_ops_title = rng.choices(
                ag.OCO_OPS_TABLE, weights=[80, 5, 5, 5, 5], k=1
            )[0]
            oco_isr_code, oco_isr_title = rng.choices(
                ag.OCO_ISR_TABLE, weights=[85, 5, 5, 5], k=1
            )[0]
            ric_code, ric_title = rng.choice(ag.RIC_TABLE)
            sfi_code, sfi_title = rng.choices(ag.SFI_TABLE, weights=[70, 6, 6, 6, 6, 6], k=1)[0]
            efficiency_title = rng.choices(
                ag.EFFICIENCY_TITLES,
                weights=[85] + [15 / (len(ag.EFFICIENCY_TITLES) - 1)] * (len(ag.EFFICIENCY_TITLES) - 1),
                k=1,
            )[0]
            position = rng.choices(
                ag.POSITION_TITLES,
                weights=[60] + [40 / (len(ag.POSITION_TITLES) - 1)] * (len(ag.POSITION_TITLES) - 1),
                k=1,
            )[0]

            month = rng.randint(1, 12)
            day = rng.randint(1, 28)
            cal_year = fy if month <= 9 else fy - 1
            act_doc_date = f"{cal_year:04d}-{month:02d}-{day:02d}"

            ccn = f"{appn_code[:4]}-{rng.randint(10000, 99999)}-{rng.choice('ABCDEFGH')}"
            ccn_title = f"{bpac_modifier} - {ce_title}"
            spc = f"S{rng.randint(100, 999)}"
            spc_title = f"{afpec_program} - {bpac_modifier}"

            dollars_k = round(float(line_k), 2)
            dollars_m = round(dollars_k / 1000.0, 5)

            rows.append({
                "AFPEC": afpec,
                "AFPEC Title": afpec_program,
                "APPN": appn_code,
                "APPN Title": APPN_TITLE,
                "BA": ba_code,
                "BA Name": ba_name,
                "GLI Category": rng.choices(ag.GLI_CATEGORIES, weights=[80, 12, 4, 4], k=1)[0],
                "BSA": bsa_code,
                "BSA Title": bsa_title,
                "OSD APPN": appn_meta["osd"],
                "RFC": f"R{rng.randint(100, 999)}",
                "BPAC": bpac_code,
                "BPAC Title": bpac_title,
                "Act Doc Date": act_doc_date,
                "CCN": ccn,
                "CCN Title": ccn_title,
                "AFEEIC Cost Cat": afeeic_code,
                "AFEEIC Cost Cat Title": bucket,
                "CE Title": ce_title,
                "OP32 Code": op32_code,
                "OP32 Sub Code": op32_sub,
                "OP32 Title": op32_title,
                "RIC": ric_code,
                "RIC Title": ric_title,
                "AF": component,
                "Efficiency Title": efficiency_title,
                "Fiscal Year": fy,
                "Dollars (in $K)": dollars_k,
                "Dollars (in $M)": dollars_m,
                "End Strength": 0,
                "OAC": oac_code,
                "OAC Title": oac_title,
                "SAG": bsa_code,
                "PE": afpec_base,
                "SAG Title": bsa_title,
                "PE Title": afpec_program,
                "SPC": spc,
                "SPC Title": spc_title,
                "Position": position,
                "AFP Category": afp_cat,
                "AFP Category Title": ag.AFP_CATEGORY_TITLES[afp_cat],
                "SFI": sfi_code,
                "SFI Title": sfi_title,
                "OCO Ops": oco_ops_code,
                "OCO Ops Title": oco_ops_title,
                "WSC": wsc_code,
                "WSC Title": wsc_title,
                "OCO ISR": oco_isr_code,
                "OCO ISR Title": oco_isr_title,
            })

    return pd.DataFrame(rows, columns=ag.COLUMNS)


def main():
    red_path = REPO / "data" / "synthetic_data_red_side.xlsx"
    green_path = REPO / "data" / "synthetic_data_green_side.xlsx"

    print(f"Reading red-side {APPN_TITLE} rows from {red_path} ...")
    new_om_afr = regenerate_om_afr_rows(red_path, SEED)
    print(f"  generated {len(new_om_afr):,} new green-side rows for {APPN_TITLE}")

    print(f"Loading existing green-side from {green_path} ...")
    existing = pd.read_excel(green_path, sheet_name="Data")
    non_om_afr = existing[existing["APPN Title"] != APPN_TITLE]
    print(f"  preserving {len(non_om_afr):,} rows for other APPNs")

    combined = pd.concat([non_om_afr, new_om_afr], ignore_index=True)
    print(f"  total: {len(combined):,} rows")

    combined.to_excel(green_path, index=False, sheet_name="Data")
    print(f"Wrote {green_path}")

    # Sanity: verify (APPN, FY) totals still reconcile within tolerance
    red = pd.read_excel(red_path, sheet_name="Data")
    red_tot = red[red["APPN Title"] == APPN_TITLE].groupby("Fiscal Year")["Dollars (in $K)"].sum()
    green_tot = new_om_afr.groupby("Fiscal Year")["Dollars (in $K)"].sum()
    diff_pct = ((green_tot - red_tot) / red_tot * 100).round(5)
    print()
    print("Per-FY (APPN, FY) reconciliation after regen:")
    print(pd.DataFrame({"red_K": red_tot.round(1), "green_K": green_tot.round(1), "pct_diff": diff_pct}))


if __name__ == "__main__":
    main()
