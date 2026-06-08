"""Empirically verify which columns sum-reconcile between air-gapped and open."""
from pathlib import Path

import pandas as pd

repo = Path(__file__).resolve().parents[1]
ag = pd.read_excel(repo / "data" / "synthetic_data_red_side.xlsx", sheet_name="Data")
op = pd.read_excel(repo / "data" / "synthetic_data_green_side.xlsx", sheet_name="Data")

DOLLARS = "Dollars (in $K)"


def reconcile(col):
    a = ag.groupby(col)[DOLLARS].sum()
    o = op.groupby(col)[DOLLARS].sum()
    merged = pd.concat([a, o], axis=1, keys=["ag", "open"]).fillna(0)
    nonzero = merged["ag"] != 0
    pct = ((merged.loc[nonzero, "open"] - merged.loc[nonzero, "ag"]) / merged.loc[nonzero, "ag"] * 100).abs()
    return pct.max() if len(pct) else 0.0, len(merged)


tests = [
    ("APPN", "APPN"),
    ("APPN Title", "APPN Title"),
    ("OSD APPN", "OSD APPN"),
    ("AF", "AF"),
    ("AFP Category", "AFP Category"),
    ("AFP Category Title", "AFP Category Title"),
    ("Fiscal Year", "Fiscal Year"),
    ("(APPN, Fiscal Year)", ["APPN", "Fiscal Year"]),
    ("(AFP Category, Fiscal Year)", ["AFP Category", "Fiscal Year"]),
    ("(OSD APPN, AF)", ["OSD APPN", "AF"]),
]
print("=== EXPECTED-TO-RECONCILE COLUMNS (within 0.01%) ===")
for name, col in tests:
    max_pct, n = reconcile(col)
    status = "OK" if max_pct < 0.01 else "FAIL"
    print(f"  {name:40s}  max|pct|={max_pct:.5f}%  groups={n}  -> {status}")

print()
print("=== EXPECTED-TO-NOT-RECONCILE COLUMNS ===")
for col in ["BA Name", "OAC", "AFPEC", "WSC", "GLI Category", "AFEEIC Cost Cat Title"]:
    max_pct, n = reconcile(col)
    status = "reconciles!" if max_pct < 0.01 else "differs (expected)"
    print(f"  {col:40s}  max|pct|={max_pct:>12.2f}%  groups={n}  -> {status}")