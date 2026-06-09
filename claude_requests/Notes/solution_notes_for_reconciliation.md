## Reconciliation — what the generator actually does vs. what Status implies

Question: based on your code, how are `Operation and Maintenance - AFR`'s 29 different AFEEIC Cost Cat Titles grouped into Open-system's AFEEIC Cost Cat Titles?  
Honest answer: my code does **NOT** actually group air-gapped line items into open-system buckets at the line-item level. The Status table I wrote shows a conceptual rollup, but the generator doesn't implement that mapping.

### What the code actually does

`local_notebook/create_open_system_data.py`, function `build_open_rows`:

```python
# Aggregate air-gapped to (APPN, APPN Title, Fiscal Year) totals.
bucket_totals = (
    air_gapped.groupby(["APPN", "APPN Title", "Fiscal Year"])["Dollars (in $K)"]
    .sum()
    .reset_index()
)
...
open_cats = OPEN_AFEEIC_BY_APPN[appn_title]
# Distribute total across the open AFEEIC categories with Dirichlet.
cat_weights = np_rng.dirichlet(np.ones(len(open_cats)) * 2.0)
cat_dollars = total_k * cat_weights
```

So for **O&M-AFR**:

1. Code sums **all** air-gapped O&M-AFR rows for each FY into one dollar total per `(APPN=3740, FY)`.
2. Takes that total and splits it across the 5 open-system categories (Personnel Services / Travel Services / Mission Support Contracts / Facilities and Logistics / General Services) via a Dirichlet draw with α=2 — i.e. roughly equal split with some noise.
3. **No reference** to which air-gapped category contributed which dollars.

**Concrete consequence:** for FY2024 O&M-AFR, the air-gapped total is $52,151K. The code splits that randomly into ~$10K each across the 5 open buckets. There's no rule that says "Fuel" dollars end up in "Facilities and Logistics" — they just get tossed into the aggregate and re-sliced.

That's a real flaw in the implementation versus what the Status section implies.

### Proposed explicit per-row rollup (O&M-AFR, 29 → 5)

If we want a defensible line-item rollup, here's the mapping to implement:

| Open-system bucket | Air-gapped items rolled in |
|---|---|
| **Personnel Services** | Other Services - Other General Training; Other Services - Education; Other Services - Tuition Assistance; Other Services - Professional Education; Other Services - Continued Education (5 items — education / development costs) |
| **Travel Services** | All 15 Travel items: Travel Expenses; Travel - Airfare; Travel - Train; Travel - Rental Cars; Travel - Mileage Reimbursement; Travel - Rideshare/Taxi; Travel - Fuel; Travel - Lodging; Travel - Lodging Incidentals; Travel - Meals; Travel - Meal Tips; Travel - Conference and Events; Travel - Workshop and Training; Travel - Communication; Travel - Baggage Fees |
| **Mission Support Contracts** | Engineering Technical Services; IT Contracting Services; Other Services - Acquisition and Non-Acquisition Support (3 items) |
| **Facilities and Logistics** | Fuel; Postal; Software Depot (3 items) |
| **General Services** | Other Services (catch-all); Other Services - Chaplain Support; Other Services - In Country Support Cost (3 items) |

**Coverage check:** 5 + 15 + 3 + 3 + 3 = 29 ✓ — all air-gapped categories accounted for.

### What a refactor would change

- Sum air-gapped dollars per `(APPN, FY, open-bucket)` instead of per `(APPN, FY)`.
- Make the Status section truthful — `Personnel Services` would only contain dollars from the 5 education items, etc.
- Preserve the `(APPN, FY)` total reconciliation (with the same jitter knob).
- Let you reconcile at the `(APPN, FY, open-bucket)` grain instead of just `(APPN, FY)`.

### Next steps

Say the word and I'll do it for O&M-AFR + the parallel mappings for O&M-AF / O&M-ANG, MilPers, NGP, Reserve Personnel, Other Procurement, RDT&E, and MERHCF.
