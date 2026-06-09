"""Regenerate the entire green-side dataset using explicit per-row rollups.

Each row in the air-gapped (red-side) dataset is rolled up into ONE
open-system (green-side) AFEEIC Cost Cat Title bucket via the per-APPN
mapping defined here. This makes (open-bucket, FY) sums year-stable so the
reconciliation algorithm can recover the rollups at tight tolerance.

Replaces `data/synthetic_data_green_side.xlsx` entirely. Each green bucket
gets the same shape of accompanying columns (BPAC, OAC, OP-32, ...) as the
original generator emitted, but the row count is much smaller because the
per-(bucket, FY) total is the rolled-up sum rather than independent draws.
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd

import create_synthetic_data as ag  # for shared lookup tables

REPO = Path(__file__).resolve().parents[1]
SEED = 271828
JITTER_PCT = 0.005  # ±0.005% per (bucket, FY) so green doesn't tie red exactly

# ---------------------------------------------------------------------------
# Per-APPN rollup: air-gapped AFEEIC Cost Cat Title -> open-system bucket
# ---------------------------------------------------------------------------

# Operation and Maintenance: 29 red categories shared across AF / AFR / ANG.
# The bucket sets differ slightly by component (AF has Education and Training
# and IT and Communications as separate buckets; AFR/ANG roll those into
# Personnel Services / General Services).

_OM_TRAVEL_REDS = [
    "Travel Expenses",
    "Travel - Airfare",
    "Travel - Train",
    "Travel - Rental Cars",
    "Travel - Mileage Reimbursement",
    "Travel - Rideshare/Taxi",
    "Travel - Fuel",
    "Travel - Lodging",
    "Travel - Lodging Incidentals",
    "Travel - Meals",
    "Travel - Meal Tips",
    "Travel - Conference and Events",
    "Travel - Workshop and Training",
    "Travel - Communication",
    "Travel - Baggage Fees",
]
_OM_EDU_REDS = [
    "Other Services - Other General Training",
    "Other Services - Education",
    "Other Services - Tuition Assistance",
    "Other Services - Professional Education",
    "Other Services - Continued Education",
]

# O&M - AF: 6 green buckets (we dropped "Personnel Services" which had no
# direct source on the 29 red side; kept Education and Training and IT and
# Communications as separate buckets).
_OM_AF_ROLLUP: dict[str, str] = {}
_OM_AF_ROLLUP.update({r: "Travel Services" for r in _OM_TRAVEL_REDS})
_OM_AF_ROLLUP.update({r: "Education and Training" for r in _OM_EDU_REDS})
_OM_AF_ROLLUP.update({
    "Engineering Technical Services":                          "Mission Support Contracts",
    "Other Services - Acquisition and Non-Acquisition Support":"Mission Support Contracts",
    "Fuel":                                                    "Facilities and Logistics",
    "Postal":                                                  "Facilities and Logistics",
    "Software Depot":                                          "Facilities and Logistics",
    "IT Contracting Services":                                 "IT and Communications",
    "Other Services":                                          "General Services",
    "Other Services - Chaplain Support":                       "General Services",
    "Other Services - In Country Support Cost":                "General Services",
})
_OM_AF_BUCKETS = [
    ("OG02", "Travel Services"),
    ("OG03", "Mission Support Contracts"),
    ("OG04", "Facilities and Logistics"),
    ("OG05", "Education and Training"),
    ("OG06", "IT and Communications"),
    ("OG07", "General Services"),
]

# O&M - AFR / ANG: 5 green buckets, education items roll into Personnel
# Services (the existing OR01 / ON01 bucket).
_OM_AFR_ROLLUP: dict[str, str] = {}
_OM_AFR_ROLLUP.update({r: "Travel Services" for r in _OM_TRAVEL_REDS})
_OM_AFR_ROLLUP.update({r: "Personnel Services" for r in _OM_EDU_REDS})
_OM_AFR_ROLLUP.update({
    "Engineering Technical Services":                          "Mission Support Contracts",
    "IT Contracting Services":                                 "Mission Support Contracts",
    "Other Services - Acquisition and Non-Acquisition Support":"Mission Support Contracts",
    "Fuel":                                                    "Facilities and Logistics",
    "Postal":                                                  "Facilities and Logistics",
    "Software Depot":                                          "Facilities and Logistics",
    "Other Services":                                          "General Services",
    "Other Services - Chaplain Support":                       "General Services",
    "Other Services - In Country Support Cost":                "General Services",
})
_OM_AFR_BUCKETS = [
    ("OR01", "Personnel Services"),
    ("OR02", "Travel Services"),
    ("OR03", "Mission Support Contracts"),
    ("OR04", "Facilities and Logistics"),
    ("OR05", "General Services"),
]
_OM_ANG_BUCKETS = [
    ("ON01", "Personnel Services"),
    ("ON02", "Travel Services"),
    ("ON03", "Mission Support Contracts"),
    ("ON04", "Facilities and Logistics"),
    ("ON05", "General Services"),
]

# Military Personnel - AF: 6 red -> 4 green (dropped "Retirement Accrual"
# which has no direct red source).
_MILPERS_ROLLUP = {
    "Officer Pay & Allowances":   "Basic Compensation",
    "Enlisted Pay & Allowances":  "Basic Compensation",
    "Cadet Pay & Allowances":     "Basic Compensation",
    "Special Pays":               "Allowances and Special Pay",
    "Subsistence":                "Member Sustenance",
    "PCS Travel":                 "Permanent Change of Station",
}
_MILPERS_BUCKETS = [
    ("MA01", "Basic Compensation"),
    ("MA02", "Allowances and Special Pay"),
    ("MA03", "Member Sustenance"),
    ("MA04", "Permanent Change of Station"),
]

# Reserve Personnel - AF: 3 red -> 3 green (1:1).
_RP_ROLLUP = {
    "Reserve Pay - Drill":                "Drill Compensation",
    "Reserve Pay - Active Duty Training": "Active Duty Training Compensation",
    "Reserve Special Pays":               "Allowances and Special Pay",
}
_RP_BUCKETS = [
    ("PA01", "Drill Compensation"),
    ("PA02", "Active Duty Training Compensation"),
    ("PA03", "Allowances and Special Pay"),
]

# National Guard Personnel - AF: 5 red -> 4 green.
_NGP_ROLLUP = {
    "adm - alert allowances":                                    "Drill Compensation",
    "adm - enl allowances":                                      "Active Duty Training Compensation",
    "adm - cloth / death gratuities":                            "Allowances and Special Pay",
    "adm - travel / allowances / base pay / school allowances":  "Travel and Retirement",
    "adm - retired pay / savings":                               "Travel and Retirement",
}
_NGP_BUCKETS = [
    ("GA01", "Drill Compensation"),
    ("GA02", "Active Duty Training Compensation"),
    ("GA03", "Allowances and Special Pay"),
    ("GA04", "Travel and Retirement"),
]

# Other Procurement - AF: 5 red -> 4 green.
_PROC_ROLLUP = {
    "Vehicles":                  "Mobility Equipment",
    "Electronics Equipment":     "Communications and IT Equipment",
    "Communications Equipment":  "Communications and IT Equipment",
    "Base Support Equipment":    "Installation Support Gear",
    "Spares and Repair Parts":   "Spares and Sustainment",
}
_PROC_BUCKETS = [
    ("PR01", "Mobility Equipment"),
    ("PR02", "Communications and IT Equipment"),
    ("PR03", "Installation Support Gear"),
    ("PR04", "Spares and Sustainment"),
]

# RDT&E - AF: 6 red -> 4 green.
_RDTE_ROLLUP = {
    "Basic Research Contracts":     "Research Contracts",
    "Applied Research Contracts":   "Research Contracts",
    "Advanced Tech Dev Contracts":  "Research Contracts",
    "Prototype Development":        "Prototype Programs",
    "System Test and Evaluation":   "Test and Evaluation",
    "RDT&E Civilian Personnel":     "RDT&E Workforce",
}
_RDTE_BUCKETS = [
    ("RE01", "Research Contracts"),
    ("RE02", "Prototype Programs"),
    ("RE03", "Test and Evaluation"),
    ("RE04", "RDT&E Workforce"),
]

# MERHCF: 1 red -> 1 green (rename only).
_MERHCF_AF_ROLLUP  = {"MERHCF Accrual - Active":  "Healthcare Accrual - Active"}
_MERHCF_AFR_ROLLUP = {"MERHCF Accrual - Reserve": "Healthcare Accrual - Reserve"}
_MERHCF_ANG_ROLLUP = {"MERHCF Accrual - Guard":   "Healthcare Accrual - Guard"}
_MERHCF_AF_BUCKETS  = [("HC01", "Healthcare Accrual - Active")]
_MERHCF_AFR_BUCKETS = [("HC02", "Healthcare Accrual - Reserve")]
_MERHCF_ANG_BUCKETS = [("HC03", "Healthcare Accrual - Guard")]

ROLLUPS: dict[str, tuple[dict[str, str], list[tuple[str, str]]]] = {
    "Operation and Maintenance - AF":   (_OM_AF_ROLLUP,   _OM_AF_BUCKETS),
    "Operation and Maintenance - AFR":  (_OM_AFR_ROLLUP,  _OM_AFR_BUCKETS),
    "Operation and Maintenance - ANG":  (_OM_AFR_ROLLUP,  _OM_ANG_BUCKETS),
    "Military Personnel - AF":          (_MILPERS_ROLLUP, _MILPERS_BUCKETS),
    "Reserve Personnel - AF":           (_RP_ROLLUP,      _RP_BUCKETS),
    "National Guard Personnel - AF":    (_NGP_ROLLUP,     _NGP_BUCKETS),
    "Other Procurement - AF":           (_PROC_ROLLUP,    _PROC_BUCKETS),
    "RDT&E - AF":                       (_RDTE_ROLLUP,    _RDTE_BUCKETS),
    "Medicare Retire Contribute - AF":  (_MERHCF_AF_ROLLUP,  _MERHCF_AF_BUCKETS),
    "Medicare Retire Contribute - AFR": (_MERHCF_AFR_ROLLUP, _MERHCF_AFR_BUCKETS),
    "Medicare Retire Contribute - ANG": (_MERHCF_ANG_ROLLUP, _MERHCF_ANG_BUCKETS),
}

# Per-bucket CE Title vocabularies (reused from create_open_system_data.py
# where they make sense; new buckets get plausible defaults).
CE_TITLES_BY_BUCKET = {
    # O&M
    "Travel Services":               ["Travel - Transport (Open)", "Travel - Lodging (Open)", "Travel - Per Diem (Open)", "Travel - Misc (Open)"],
    "Mission Support Contracts":     ["A&AS Mission Support", "Engineering Services Contract", "Studies and Analysis Contract"],
    "Facilities and Logistics":      ["Facility Sustainment", "Fuel Distribution", "Postal Operations", "Software Operations"],
    "Education and Training":        ["Tuition - Open", "Professional Education - Open", "General Training - Open"],
    "IT and Communications":         ["Cloud Operations", "Software Licensing", "Long Haul Comms", "Cyber Operations"],
    "Personnel Services":            ["Civilian Salaries (Open)", "Civilian Benefits (Open)", "Overtime - Open"],
    "General Services":              ["Chaplain Operations", "In-Country Support", "Other General Services"],
    # MilPers
    "Basic Compensation":            ["Officer Basic Pay - Open", "Enlisted Basic Pay - Open"],
    "Allowances and Special Pay":    ["BAH - Open", "Special Pay - Open"],
    "Member Sustenance":             ["Subsistence-in-Kind - Open", "BAS - Open"],
    "Permanent Change of Station":   ["PCS - Accession", "PCS - Rotational", "PCS - Separation"],
    # Reserve / Guard
    "Drill Compensation":                ["IDT Pay - Open", "Drill Allowances - Open"],
    "Active Duty Training Compensation": ["ADT Pay - Open", "ADT Allowances - Open"],
    "Travel and Retirement":             ["Guard Travel - Open", "Guard Retired Pay - Open"],
    # Procurement
    "Mobility Equipment":               ["Vehicles - Open", "Material Handling - Open"],
    "Communications and IT Equipment":  ["Radios - Open", "Network Equipment - Open", "Sensors - Open"],
    "Installation Support Gear":        ["Generators - Open", "Fire/Medical Equipment - Open"],
    "Spares and Sustainment":           ["Initial Spares - Open", "Replenishment Spares - Open"],
    # RDT&E
    "Research Contracts":            ["Basic Research - Open", "Applied Research - Open"],
    "Prototype Programs":            ["Prototype - Open"],
    "Test and Evaluation":           ["T&E Operations - Open"],
    "RDT&E Workforce":               ["RDT&E Civilian - Open"],
    # MERHCF
    "Healthcare Accrual - Active":   ["MERHCF Active Accrual - Open"],
    "Healthcare Accrual - Reserve":  ["MERHCF Reserve Accrual - Open"],
    "Healthcare Accrual - Guard":    ["MERHCF Guard Accrual - Open"],
}


def _component_for(appn_title: str) -> str:
    if "AFR" in appn_title or appn_title == "Reserve Personnel - AF":
        return "AFR"
    if "ANG" in appn_title or appn_title == "National Guard Personnel - AF":
        return "ANG"
    return "AF"


def regenerate_green_for_appn(
    red_df: pd.DataFrame, appn_title: str, seed: int,
) -> pd.DataFrame:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    rollup, bucket_specs = ROLLUPS[appn_title]
    appn_red = red_df[red_df["APPN Title"] == appn_title].copy()
    if appn_red.empty:
        return pd.DataFrame(columns=ag.COLUMNS)

    red_cats = set(appn_red["AFEEIC Cost Cat Title"].unique())
    missing = red_cats - set(rollup)
    if missing:
        raise RuntimeError(f"[{appn_title}] rollup missing for: {sorted(missing)}")

    appn_red["open_bucket"] = appn_red["AFEEIC Cost Cat Title"].map(rollup)
    bucket_fy = (
        appn_red.groupby(["open_bucket", "Fiscal Year"])["Dollars (in $K)"]
        .sum()
        .reset_index()
    )
    bucket_fy["jittered_K"] = bucket_fy["Dollars (in $K)"] * (
        1.0 + np_rng.uniform(-JITTER_PCT, JITTER_PCT, size=len(bucket_fy)) / 100.0
    )

    appn_meta = ag.APPN_TABLE[appn_title]
    appn_code = appn_meta["appn"]
    afp_cat = appn_meta["afp_cat"]
    component = _component_for(appn_title)
    ba_options = ag.BA_TABLE[appn_title]
    code_for_bucket = {title: code for code, title in bucket_specs}

    rows = []
    for _, b in bucket_fy.iterrows():
        bucket = b["open_bucket"]
        fy = int(b["Fiscal Year"])
        bucket_total_k = float(b["jittered_K"])
        afeeic_code = code_for_bucket[bucket]
        ce_options = CE_TITLES_BY_BUCKET.get(bucket, [bucket])

        n_lines = max(2, min(12, int(np.round(np.sqrt(max(bucket_total_k, 1.0) / 250.0)))))
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

            if afp_cat == "OM":
                op32 = rng.choice(ag.OP32_TABLE)
                op32_code, op32_sub, op32_title = op32[0], op32[1], op32[2]
            else:
                op32_code = op32_sub = op32_title = ""

            afpec_base, afpec_program = rng.choice(ag.AFPEC_BASES)
            afpec_suffix = rng.choice(ag.AFPEC_SUFFIX_BY_APPN[appn_title])
            afpec = f"{afpec_base}{afpec_suffix}"
            pe_code = afpec_base

            oac_code = rng.choice(ag.OAC_BY_COMPONENT[component])
            oac_title = dict(ag.OAC_TABLE)[oac_code]
            wsc_code, wsc_title = rng.choice(ag.WSC_TABLE)
            oco_ops_code, oco_ops_title = rng.choices(ag.OCO_OPS_TABLE, weights=[80, 5, 5, 5, 5], k=1)[0]
            oco_isr_code, oco_isr_title = rng.choices(ag.OCO_ISR_TABLE, weights=[85, 5, 5, 5], k=1)[0]
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

            if afp_cat == "MILPERS":
                end_strength = int(np_rng.lognormal(mean=np.log(150), sigma=1.0))
                end_strength = int(np.clip(end_strength, 1, 5000))
            else:
                end_strength = 0

            rows.append({
                "AFPEC": afpec, "AFPEC Title": afpec_program,
                "APPN": appn_code, "APPN Title": appn_title,
                "BA": ba_code, "BA Name": ba_name,
                "GLI Category": rng.choices(ag.GLI_CATEGORIES, weights=[80, 12, 4, 4], k=1)[0],
                "BSA": bsa_code, "BSA Title": bsa_title,
                "OSD APPN": appn_meta["osd"],
                "RFC": f"R{rng.randint(100, 999)}",
                "BPAC": bpac_code, "BPAC Title": bpac_title,
                "Act Doc Date": act_doc_date,
                "CCN": ccn, "CCN Title": ccn_title,
                "AFEEIC Cost Cat": afeeic_code, "AFEEIC Cost Cat Title": bucket,
                "CE Title": ce_title,
                "OP32 Code": op32_code, "OP32 Sub Code": op32_sub, "OP32 Title": op32_title,
                "RIC": ric_code, "RIC Title": ric_title,
                "AF": component, "Efficiency Title": efficiency_title,
                "Fiscal Year": fy,
                "Dollars (in $K)": dollars_k, "Dollars (in $M)": dollars_m,
                "End Strength": end_strength,
                "OAC": oac_code, "OAC Title": oac_title,
                "SAG": bsa_code, "PE": pe_code,
                "SAG Title": bsa_title, "PE Title": afpec_program,
                "SPC": spc, "SPC Title": spc_title,
                "Position": position,
                "AFP Category": afp_cat, "AFP Category Title": ag.AFP_CATEGORY_TITLES[afp_cat],
                "SFI": sfi_code, "SFI Title": sfi_title,
                "OCO Ops": oco_ops_code, "OCO Ops Title": oco_ops_title,
                "WSC": wsc_code, "WSC Title": wsc_title,
                "OCO ISR": oco_isr_code, "OCO ISR Title": oco_isr_title,
            })
    return pd.DataFrame(rows, columns=ag.COLUMNS)


def main() -> None:
    red_path = REPO / "data" / "synthetic_data_red_side.xlsx"
    green_path = REPO / "data" / "synthetic_data_green_side.xlsx"

    print(f"Reading red-side data from {red_path} ...")
    red_df = pd.read_excel(red_path, sheet_name="Data")
    print(f"  loaded {len(red_df):,} rows")

    appns_in_red = red_df["APPN Title"].unique()
    print(f"  APPNs in red: {len(appns_in_red)}")

    new_green_dfs = []
    for appn_title in ROLLUPS:
        df = regenerate_green_for_appn(red_df, appn_title, SEED + abs(hash(appn_title)) % 1000)
        print(f"  {appn_title}: {len(df)} green rows generated")
        new_green_dfs.append(df)

    combined = pd.concat(new_green_dfs, ignore_index=True)
    combined.to_excel(green_path, index=False, sheet_name="Data")
    print()
    print(f"Wrote {green_path}: {len(combined):,} total rows")

    # Reconciliation sanity per APPN
    print()
    print("Per-(APPN, FY) reconciliation sanity (should be < 0.01%):")
    rows = []
    for appn_title in ROLLUPS:
        red_tot = red_df[red_df["APPN Title"] == appn_title].groupby("Fiscal Year")["Dollars (in $K)"].sum()
        new = combined[combined["APPN Title"] == appn_title]
        green_tot = new.groupby("Fiscal Year")["Dollars (in $K)"].sum()
        # align
        all_fy = sorted(set(red_tot.index) | set(green_tot.index))
        max_pct = 0.0
        for fy in all_fy:
            r = red_tot.get(fy, 0)
            g = green_tot.get(fy, 0)
            if r:
                pct = abs((g - r) / r * 100.0)
                max_pct = max(max_pct, pct)
        rows.append({
            "APPN Title": appn_title,
            "max_pct_diff": round(max_pct, 5),
            "ok": max_pct < 0.01,
        })
    summary = pd.DataFrame(rows)
    print(summary.to_string(index=False))
    bad = summary[~summary["ok"]]
    if not bad.empty:
        print()
        print("WARNING: the following APPNs exceeded 0.01% per-FY tolerance:")
        print(bad.to_string(index=False))


if __name__ == "__main__":
    main()
