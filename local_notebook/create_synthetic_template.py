import pandas as pd
from pathlib import Path

COLUMNS = [
    "AFPEC",
    "AFPEC Title",
    "APPN",
    "APPN Title",
    "BA",
    "BA Name",
    "GLI Category",
    "BSA",
    "BSA Title",
    "OSD APPN",
    "RFC",
    "BPAC",
    "BPAC Title",
    "Act Doc Date",
    "CCN",
    "CCN Title",
    "AFEEIC Cost Cat",
    "AFEEIC Cost Cat Title",
    "CE Title",
    "OP32 Code",
    "OP32 Sub Code",
    "OP32 Title",
    "RIC",
    "RIC Title",
    "AF",
    "Efficiency Title",
    "Fiscal Year",
    "Dollars (in $K)",
    "Dollars (in $M)",
    "End Strength",
    "OAC",
    "OAC Title",
    "SAG",
    "PE",
    "SAG Title",
    "PE Title",
    "SPC",
    "SPC Title",
    "Position",
    "AFP Category",
    "AFP Category Title",
    "SFI",
    "SFI Title",
    "OCO Ops",
    "OCO Ops Title",
    "WSC",
    "WSC Title",
    "OCO ISR",
    "OCO ISR Title",
]

out_path = Path(__file__).resolve().parents[1] / "data" / "synthetic_data_red_side.xlsx"
out_path.parent.mkdir(parents=True, exist_ok=True)

df = pd.DataFrame(columns=COLUMNS)
df.to_excel(out_path, index=False, sheet_name="Data")
print(f"Wrote {out_path} with {len(COLUMNS)} columns")