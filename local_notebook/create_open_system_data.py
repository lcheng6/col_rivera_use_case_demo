"""Generate the 'open system' synthetic dataset.

Treats data/synthetic_data_red_side.xlsx as the air-gapped side and produces an
open-system counterpart with:

- The same APPN <-> APPN Title pairs, the same Fiscal Year range, the same
  column set.
- A DIFFERENT AFEEIC Cost Cat Title categorization (broader / different axis).
- Line-item dollar amounts that DO NOT match air-gapped row-by-row, but
  reconcile within 0.01% at the (APPN, Fiscal Year) aggregation grain.

Reuses the shared lookup tables from create_synthetic_data.py so AFPEC/BA/
BPAC/OAC/etc. fields stay structurally consistent with the air-gapped data.
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd

import create_synthetic_data as ag  # air-gapped generator + shared tables

SEED = 91230608
N_ROWS_TARGET = 15_000      # roughly; actual count depends on bucket sizing
JITTER_PCT = 0.005          # +-0.005% jitter per (APPN, FY) total -> within 0.01%

# ---------------------------------------------------------------------------
# Open-system AFEEIC Cost Cat Title taxonomy (different axis from air-gapped)
# ---------------------------------------------------------------------------
# Air-gapped breaks O&M into 29 detailed categories (Fuel, Travel - Airfare,
# Travel - Meals, Other Services - Chaplain Support, ...). The open system
# uses a broader functional rollup that still aggregates to the same APPN
# total. NGP/RP/MilPers/Procurement/RDT&E/MERHCF likewise get an alternative
# breakdown so the two systems don't share row-level categories.

OPEN_AFEEIC_BY_APPN = {
    "Operation and Maintenance - AF": [
        ("OG01", "Personnel Services"),
        ("OG02", "Travel Services"),
        ("OG03", "Mission Support Contracts"),
        ("OG04", "Facilities and Logistics"),
        ("OG05", "Education and Training"),
        ("OG06", "IT and Communications"),
        ("OG07", "General Services"),
    ],
    "Operation and Maintenance - AFR": [
        ("OR01", "Personnel Services"),
        ("OR02", "Travel Services"),
        ("OR03", "Mission Support Contracts"),
        ("OR04", "Facilities and Logistics"),
        ("OR05", "General Services"),
    ],
    "Operation and Maintenance - ANG": [
        ("ON01", "Personnel Services"),
        ("ON02", "Travel Services"),
        ("ON03", "Mission Support Contracts"),
        ("ON04", "Facilities and Logistics"),
        ("ON05", "General Services"),
    ],
    "Military Personnel - AF": [
        ("MA01", "Basic Compensation"),
        ("MA02", "Allowances and Special Pay"),
        ("MA03", "Member Sustenance"),
        ("MA04", "Permanent Change of Station"),
        ("MA05", "Retirement Accrual"),
    ],
    "Reserve Personnel - AF": [
        ("PA01", "Drill Compensation"),
        ("PA02", "Active Duty Training Compensation"),
        ("PA03", "Allowances and Special Pay"),
    ],
    "National Guard Personnel - AF": [
        ("GA01", "Drill Compensation"),
        ("GA02", "Active Duty Training Compensation"),
        ("GA03", "Allowances and Special Pay"),
        ("GA04", "Travel and Retirement"),
    ],
    "Other Procurement - AF": [
        ("PR01", "Mobility Equipment"),
        ("PR02", "Communications and IT Equipment"),
        ("PR03", "Installation Support Gear"),
        ("PR04", "Spares and Sustainment"),
    ],
    "RDT&E - AF": [
        ("RE01", "Research Contracts"),
        ("RE02", "Prototype Programs"),
        ("RE03", "Test and Evaluation"),
        ("RE04", "RDT&E Workforce"),
    ],
    "Medicare Retire Contribute - AF":  [("HC01", "Healthcare Accrual - Active")],
    "Medicare Retire Contribute - AFR": [("HC02", "Healthcare Accrual - Reserve")],
    "Medicare Retire Contribute - ANG": [("HC03", "Healthcare Accrual - Guard")],
}

# Open-system CE Titles per open AFEEIC Cost Cat Title (intentionally
# different wording from the air-gapped CE Titles).
OPEN_CE_BY_AFEEIC = {
    # O&M
    "Personnel Services":            ["Civilian Salaries (Open)", "Civilian Benefits (Open)", "Overtime - Open"],
    "Travel Services":               ["Travel - Transport (Open)", "Travel - Lodging (Open)", "Travel - Per Diem (Open)", "Travel - Misc (Open)"],
    "Mission Support Contracts":     ["A&AS Mission Support", "Engineering Services Contract", "Studies and Analysis Contract"],
    "Facilities and Logistics":      ["Facility Sustainment", "Fuel Distribution", "Postal Operations", "Software Operations"],
    "Education and Training":        ["Tuition - Open", "Professional Education - Open", "General Training - Open"],
    "IT and Communications":         ["Cloud Operations", "Software Licensing", "Long Haul Comms", "Cyber Operations"],
    "General Services":              ["Chaplain Operations", "In-Country Support", "Other General Services"],
    # MilPers
    "Basic Compensation":            ["Officer Basic Pay - Open", "Enlisted Basic Pay - Open"],
    "Allowances and Special Pay":    ["BAH - Open", "Special Pay - Open"],
    "Member Sustenance":             ["Subsistence-in-Kind - Open", "BAS - Open"],
    "Permanent Change of Station":   ["PCS - Accession", "PCS - Rotational", "PCS - Separation"],
    "Retirement Accrual":            ["Retired Pay Accrual - Open"],
    # Reserve / Guard
    "Drill Compensation":            ["IDT Pay - Open", "Drill Allowances - Open"],
    "Active Duty Training Compensation": ["ADT Pay - Open", "ADT Allowances - Open"],
    "Travel and Retirement":         ["Guard Travel - Open", "Guard Retired Pay - Open"],
    # Procurement
    "Mobility Equipment":            ["Vehicles - Open", "Material Handling - Open"],
    "Communications and IT Equipment": ["Radios - Open", "Network Equipment - Open", "Sensors - Open"],
    "Installation Support Gear":     ["Generators - Open", "Fire/Medical Equipment - Open"],
    "Spares and Sustainment":        ["Initial Spares - Open", "Replenishment Spares - Open"],
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


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def _component_for(appn_title: str) -> str:
    if "AFR" in appn_title or appn_title == "Reserve Personnel - AF":
        return "AFR"
    if "ANG" in appn_title or appn_title == "National Guard Personnel - AF":
        return "ANG"
    return "AF"


def build_open_rows(air_gapped: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    # Aggregate air-gapped to (APPN, APPN Title, Fiscal Year) totals.
    bucket_totals = (
        air_gapped.groupby(["APPN", "APPN Title", "Fiscal Year"])["Dollars (in $K)"]
        .sum()
        .reset_index()
    )

    rows = []
    for _, bucket in bucket_totals.iterrows():
        appn_code = bucket["APPN"]
        appn_title = bucket["APPN Title"]
        fy = int(bucket["Fiscal Year"])
        # Apply tiny jitter so the two systems don't exactly tie.
        jitter = np_rng.uniform(-JITTER_PCT, JITTER_PCT) / 100.0
        total_k = float(bucket["Dollars (in $K)"]) * (1.0 + jitter)

        open_cats = OPEN_AFEEIC_BY_APPN[appn_title]
        # Distribute total across the open AFEEIC categories with Dirichlet.
        cat_weights = np_rng.dirichlet(np.ones(len(open_cats)) * 2.0)
        cat_dollars = total_k * cat_weights

        appn_meta = ag.APPN_TABLE[appn_title]
        afp_cat = appn_meta["afp_cat"]
        component = _component_for(appn_title)
        ba_options = ag.BA_TABLE[appn_title]

        for (afeeic_code, afeeic_title), cat_total in zip(open_cats, cat_dollars):
            # Number of line-item rows within this (APPN, FY, AFEEIC) bucket.
            # Smaller buckets get fewer rows; larger get more.
            n_rows = max(2, min(15, int(np.round(np.sqrt(cat_total / 200.0)))))
            line_weights = np_rng.dirichlet(np.ones(n_rows) * 1.5)
            line_dollars = cat_total * line_weights

            ce_options = OPEN_CE_BY_AFEEIC.get(afeeic_title, [afeeic_title])

            for line_k in line_dollars:
                ba_code, ba_name = rng.choice(ba_options)
                bsa_options = ag.BSA_TABLE.get(ba_name, [(ba_code + "0", ba_name + " - General")])
                bsa_code, bsa_title = rng.choice(bsa_options)
                sag_code, sag_title = bsa_code, bsa_title

                bpac_seq = rng.randint(1, 99)
                bpac_code = f"{appn_code[:4]}{bsa_code}{bpac_seq:02d}"
                bpac_modifier = rng.choice(["Operations", "Sustainment", "Modernization", "Support", "Readiness"])
                bpac_title = f"{bsa_title} - {bpac_modifier}"

                ce_title = rng.choice(ce_options)

                # OP-32 only meaningful for O&M
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
                oco_ops_code, oco_ops_title = rng.choices(
                    ag.OCO_OPS_TABLE, weights=[80, 5, 5, 5, 5], k=1
                )[0]
                oco_isr_code, oco_isr_title = rng.choices(
                    ag.OCO_ISR_TABLE, weights=[85, 5, 5, 5], k=1
                )[0]
                ric_code, ric_title = rng.choice(ag.RIC_TABLE)
                sfi_code, sfi_title = rng.choices(
                    ag.SFI_TABLE, weights=[70, 6, 6, 6, 6, 6], k=1
                )[0]

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
                    "AFPEC": afpec,
                    "AFPEC Title": afpec_program,
                    "APPN": appn_code,
                    "APPN Title": appn_title,
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
                    "AFEEIC Cost Cat Title": afeeic_title,
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
                    "End Strength": end_strength,
                    "OAC": oac_code,
                    "OAC Title": oac_title,
                    "SAG": sag_code,
                    "PE": pe_code,
                    "SAG Title": sag_title,
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


def reconcile_report(air_gapped: pd.DataFrame, open_sys: pd.DataFrame) -> pd.DataFrame:
    ag_totals = (
        air_gapped.groupby(["APPN", "APPN Title", "Fiscal Year"])["Dollars (in $K)"]
        .sum()
        .reset_index(name="ag_K")
    )
    open_totals = (
        open_sys.groupby(["APPN", "APPN Title", "Fiscal Year"])["Dollars (in $K)"]
        .sum()
        .reset_index(name="open_K")
    )
    merged = ag_totals.merge(open_totals, on=["APPN", "APPN Title", "Fiscal Year"], how="outer")
    merged["diff_K"] = merged["open_K"] - merged["ag_K"]
    merged["pct_diff"] = (merged["diff_K"] / merged["ag_K"] * 100.0).round(4)
    return merged


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    ag_path = repo / "data" / "synthetic_data_red_side.xlsx"
    out_path = repo / "data" / "synthetic_data_green_side.xlsx"

    print(f"Reading air-gapped data from {ag_path} ...")
    air_gapped = pd.read_excel(ag_path)

    print(f"Generating open-system rows (seed={SEED}) ...")
    open_sys = build_open_rows(air_gapped, SEED)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    open_sys.to_excel(out_path, index=False, sheet_name="Data")
    print(f"Wrote {out_path}: {len(open_sys):,} rows x {len(open_sys.columns)} cols")

    rec = reconcile_report(air_gapped, open_sys)
    max_abs_pct = rec["pct_diff"].abs().max()
    print()
    print("Reconciliation (per APPN, Fiscal Year):")
    print(rec.to_string(index=False))
    print()
    print(f"Max |pct diff| across all (APPN, FY) buckets: {max_abs_pct:.5f}%")
    print(f"Air-gapped total: ${air_gapped['Dollars (in $K)'].sum():,.0f}K")
    print(f"Open system total: ${open_sys['Dollars (in $K)'].sum():,.0f}K")
    overall_pct = (open_sys["Dollars (in $K)"].sum() - air_gapped["Dollars (in $K)"].sum()) / air_gapped["Dollars (in $K)"].sum() * 100
    print(f"Overall pct diff: {overall_pct:+.5f}%")
    assert max_abs_pct < 0.01, f"Reconciliation tolerance exceeded: {max_abs_pct}%"
    print("OK: all (APPN, FY) buckets reconcile within 0.01%")


if __name__ == "__main__":
    main()