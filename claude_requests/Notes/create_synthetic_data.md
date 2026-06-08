## Create Synthetic Data

We are going to do some iterative development on synthetic data creation, with this page to track decisions, todo items, and their status

### Background
I want to create synthetic data that mirror the structure of a sensitive data set, in terms of column names, and column data types, but almost completely with synthetic values, especially for the budget dollar amount.  

The original Excel spreadsheet contained budget spending amount for each fisical year for each line items. That's what I'm trying to replicate, so when you are trying to fill in numbers, fill in the numbers that make comman sense, for example, the fuel expenses for travel for training expenses should not be in billion dollars. 

I will write out what I took notes from the original spreadsheet and you can help me with data creation.

#### Column Names

Here are the column names in the order that was listed in the original spreadsheet
- AFPEC
- AFPEC Title
- APPN
- APPN Title
- BA
- BA Name
- GLI Category
- BSA
- BSA Title
- OSD APPN
- RFC
- BPAC
- BPAC Title
- Act Doc Date
- CCN
- CCN Title
- AFEEIC Cost Cat
- AFEEIC Cost Cat Title
- CE Title
- OP32 Code
- OP32 Sub Code
- OP32 Title
- RIC
- RIC Title
- AF
- Efficiency Title
- Fiscal Year
- Dollars (in $K)
- Dollars (in $M)
- End Strength
- OAC
- OAC Title
- SAG
- PE
- SAG Title
- PE Title
- SPC
- SPC Title
- Position
- AFP Category
- AFP Category Title
- SFI
- SFI Title
- OCO Ops
- OCO Ops Title
- WSC
- WSC Title
- OCO ISR
- OCO ISR Title


#### Column Characteritics 

The column names describe data in its hierarchical way.  For categorical data, typically the right columns are sub-category of the left columns

Fiscal Year had 2024 to 2033

Sample AFPEC values: 
* 35208A
* 35208B
* 35208C
* 35208D
* 35208R
* 35208G

AFPEC Title column contains Air Force Program names, use your imagination to create synthetic program names

APPN and APPN Title: 100% correlationed, 1 to 1 connection

`APPN` is alphanumeric identifier of `APPN Title`

`APPN Title` Sample values

- Medicare Retire Contribute - AF
- Medicare Retire Contribute - AFR
- Medicare Retire Contribute - ANG
- Military Personnel - AF
- National Guard Personnel - AF
- Operation and Maintenance - AF
- Operation and Maintenance - AFR
- Operation and Maintenance - ANG
- Other Procurement - AF
- RDT&E - AF
- Reserve Personnel - AF

`APPN Title` and `AFEEIC Cost Cat title` are hierachial 

Example: 
National Guard Peronnel - AF: 
* adm alert allowances
* adm - enl allowances
* adm - cloth / death gratuities
* adm - travel / allowances / base pay / school allowances/ base pay/ retired pay/ savings. 


Operational and Maintenance AF -> `AFEEIC Cost Category Title`, 
`AFEEIC Cost Category Title` Sample Values: 
* Engineering Technical Services
* Fuel
* IT Contracting Services
* Other Services
* Travel Expenses
* Other Services - Other General Training
* Other Services - Acquisitiong and Non-Acquisition Support
* Other Services - Chaplain Support
* Other Services - Education 
* Other Services - Tuition Assist
* Other Services - In Country Support Cost
* Other Services - Professional Education
* Other Serivces - Continued Education
* Postal
* Software Depot
* Travel - Airfare
* Travel - Train
* Travel - Rental Cars
* Travel - Mileage Reimbursement 
* Travel - Rideshare/Taxi 
* Travel - Fuel
* Travel - Lodging
* Travel - Lodging incidentals
* Travel - Meals
* Travel - Meal Tips
* Travel - Conference and Events
* Travel - Workshop and Training
* Travel - Communication
* Travel - Baggage Fees

`AFEIC` Sample Values
* A& AS IT Studies
* active AF officers
* adc Alert
* adm - enl allow
* adm - enl base pay
* adm - enl base pay
* adm - enl cloth
* adm - enl death gratuities
* adm - enl other pay
* adm - enl ret pay
* adm - enl ret pay cc
* adm - enl off base
* AF - enlisted
* AF - officers
* Architect Engineering Services
* Cyber Ops
* Postal
* Other Services - Other General Training
* Other Services - Acquition and Non-Acquisition
* Travel - AFRC Mandatory Support
* Travel - ANG Mandatory Support
* Travel - Civilian PCS
* Travel - Conference Travel Expenses
* Travel - Emergency Leave - Member
* Travel - Emergency Leave - Dependent
* Travel - Mission Special Projects
* Travel - Mission Support
* Travel - Schools and Training
* Travel - Conference Travel Expenses
### Tasks

1. Create an Excel spreadsheet in [data](../../data) with right column headings

2. Create two CSV files that has the same columns and same logic as the Excel spreadsheet, but different dollar amounts, I want to use these as simulated database pulls 

3. This next part is going to require some imagination and creative thinking on your part.  I need to simulate a budget line item reconciliation problem.  It's something like this: 
   * Budget spending on trapped on 2 different systems, one on air-gapped side, and one in a publicly available cloud system.  So these tools don't talk to each other, however, they are tracking the spending activities of the same organization, so at some level of aggregation, for example total spending for FY2025 has to be equal, or within a tiny discrepancy of each other.  
   * The 2 system also track line items differently at different categorization.  I can give you a contrived example, for you to follow: 
     * Say you are tracking budget of the food services for FY2025.  The air-gapped system could break down the costs at the meal level `Other Services - Breakfast`, `Other Services - Lunch`, and `Other Services - Dinner`, where as the open system would track it as at a food supplier/ingredient level `Dining Services - Dairy`, `Dining Services - Meat`, `Dining Services - Vegatables`, `Dining Services - Misc`.  You can't easily match line to line, but when summed together as dinning services on a per year basis, you can see that these lines match
   * You've already created synthetic data in [synthetic_data_red_side.xlsx](../../data/synthetic_data_red_side.xlsx), let's call that synthetic data that corresponds to the air-gapped system. 
   * Now I need you to create the synthetic data set that corresponds to the open system, keep in mind the point I mentioned earlier about different ways of categorization and how the money amount differ, but still remember that when aggregated, the result shouldn't differ by more than .01%.  Start with playing with `AFEEIC Cost Category Title` column and corresponding costs first.  
   * Show me what categorization you've made to reconcile between the 2 systems in Status
   * Can you also tell me which columns, when sum-aggregated, should be consistent between the 2 datasets? 
     

### Status

#### Task 1 — DONE
`data/synthetic_data_red_side.xlsx` — 25,000 rows × 49 columns. Generator: `local_notebook/create_synthetic_data.py`.

#### Task 2 — DONE
`data/db_pull_1.csv` and `data/db_pull_2.csv` — both 25,000 rows × 49 columns, different seeds (70001, 70002), same schema and categorical logic as the Excel, different dollar amounts. Same generator with `--db-pulls` flag.

#### Task 3 — DONE
`data/synthetic_data_green_side.xlsx` — 4,678 rows × 49 columns. Generator: `local_notebook/create_open_system_data.py`.

**Reconciliation grain:** `(APPN, Fiscal Year)`. Per-bucket diff ≤ 0.005%, max overall diff -0.00064%. All 110 buckets reconcile within the 0.01% tolerance. Jitter (±0.005%) is applied per bucket so the two systems don't tie exactly.

**Categorization mapping** — air-gapped → open system, by APPN. AFEEIC Cost Cat Title is the column being remapped; everything else (APPN/APPN Title/Fiscal Year) is preserved so the join key for reconciliation is `(APPN, Fiscal Year)`.

| APPN | APPN Title | Air-gapped AFEEIC Cost Cat Titles (granular) | Open-system AFEEIC Cost Cat Titles (rolled-up / different axis) |
|---|---|---|---|
| 3400 | Operation and Maintenance - AF | 29 detailed: Engineering Technical Services; Fuel; IT Contracting Services; Other Services; Travel Expenses; Other Services - Other General Training; Other Services - Acquisition and Non-Acquisition Support; Other Services - Chaplain Support; Other Services - Education; Other Services - Tuition Assistance; Other Services - In Country Support Cost; Other Services - Professional Education; Other Services - Continued Education; Postal; Software Depot; Travel - Airfare; Travel - Train; Travel - Rental Cars; Travel - Mileage Reimbursement; Travel - Rideshare/Taxi; Travel - Fuel; Travel - Lodging; Travel - Lodging Incidentals; Travel - Meals; Travel - Meal Tips; Travel - Conference and Events; Travel - Workshop and Training; Travel - Communication; Travel - Baggage Fees | 7 broad: Personnel Services; Travel Services; Mission Support Contracts; Facilities and Logistics; Education and Training; IT and Communications; General Services |
| 3740 | Operation and Maintenance - AFR | (same 29 as above) | 5 broad: Personnel Services; Travel Services; Mission Support Contracts; Facilities and Logistics; General Services |
| 3840 | Operation and Maintenance - ANG | (same 29 as above) | 5 broad: Personnel Services; Travel Services; Mission Support Contracts; Facilities and Logistics; General Services |
| 3500 | Military Personnel - AF | 6: Officer Pay & Allowances; Enlisted Pay & Allowances; Cadet Pay & Allowances; Subsistence; PCS Travel; Special Pays | 5: Basic Compensation; Allowances and Special Pay; Member Sustenance; Permanent Change of Station; Retirement Accrual |
| 3700 | Reserve Personnel - AF | 3: Reserve Pay - Drill; Reserve Pay - Active Duty Training; Reserve Special Pays | 3: Drill Compensation; Active Duty Training Compensation; Allowances and Special Pay |
| 3830 | National Guard Personnel - AF | 5: adm - alert allowances; adm - enl allowances; adm - cloth / death gratuities; adm - travel / allowances / base pay / school allowances; adm - retired pay / savings | 4: Drill Compensation; Active Duty Training Compensation; Allowances and Special Pay; Travel and Retirement |
| 3080 | Other Procurement - AF | 5: Vehicles; Electronics Equipment; Communications Equipment; Base Support Equipment; Spares and Repair Parts | 4: Mobility Equipment; Communications and IT Equipment; Installation Support Gear; Spares and Sustainment |
| 3600 | RDT&E - AF | 6: Basic Research Contracts; Applied Research Contracts; Advanced Tech Dev Contracts; Prototype Development; System Test and Evaluation; RDT&E Civilian Personnel | 4: Research Contracts; Prototype Programs; Test and Evaluation; RDT&E Workforce |
| 0540 | Medicare Retire Contribute - AF | 1: MERHCF Accrual - Active | 1: Healthcare Accrual - Active |
| 0540F | Medicare Retire Contribute - AFR | 1: MERHCF Accrual - Reserve | 1: Healthcare Accrual - Reserve |
| 0540G | Medicare Retire Contribute - ANG | 1: MERHCF Accrual - Guard | 1: Healthcare Accrual - Guard |

**Zero label overlap** between the two systems on the AFEEIC Cost Cat Title column — verified at generation time. To reconcile, sum `Dollars (in $K)` grouped by `(APPN, Fiscal Year)` in each file; the two totals should agree within 0.01%.

**Conceptual axis difference** (per APPN):
- **O&M**: air-gapped breaks down by cost-type (Fuel vs IT vs each travel sub-category); open system breaks down by function (Personnel vs Travel vs Mission Support vs Facilities). The 29 air-gapped travel/services line types roll up into 7 functional buckets in the open system.
- **MilPers**: air-gapped breaks down by member type (Officer / Enlisted / Cadet) and benefit type; open system breaks down by pay component (Basic / Allowances / Sustenance / PCS / Retirement). Pay for both officers and enlisted ends up in "Basic Compensation" on the open side.
- **National Guard Personnel**: air-gapped uses legacy "adm - ..." accounting line names; open system uses modernized functional names (Drill / ADT / Allowances / Travel-and-Retirement).
- **Other Procurement**: air-gapped breaks down by hardware type (Vehicles / Electronics / Comms / Base Support); open system regroups around mission role (Mobility / Comms-and-IT / Installation Support / Spares).
- **RDT&E**: air-gapped distinguishes basic vs applied vs advanced research as separate buckets; open system collapses them into one "Research Contracts" bucket and renames Prototype Development → Prototype Programs.
- **MERHCF**: same single-bucket structure on both sides; labels differ only in naming (MERHCF Accrual vs Healthcare Accrual).

**Which columns sum-reconcile between the two datasets** (when used as a `groupby` key on `Dollars (in $K)` or `Dollars (in $M)`):

The open-system generator preserves the `(APPN, APPN Title, Fiscal Year)` totals from air-gapped (with ±0.005% jitter). Everything below that grain is independently re-sampled, so only columns derivable from those three (or coarser) reconcile.

| Group-by column(s) | Reconciles? | Why |
|---|---|---|
| **Grand total** (no grouping) | ✅ Yes (≤ 0.01%) | Sum of all (APPN, FY) buckets |
| **Fiscal Year** | ✅ Yes | Aggregation of all APPNs within each FY |
| **APPN** | ✅ Yes | Aggregation of all FYs within each APPN |
| **APPN Title** | ✅ Yes | 1:1 with APPN |
| **OSD APPN** | ✅ Yes | Function of APPN (MILPERS / OM / PROC / RDTE / MERHCF), aggregates multiple APPNs |
| **AF** (component: AF / AFR / ANG) | ✅ Yes | Function of APPN Title |
| **AFP Category** | ✅ Yes | Function of APPN |
| **AFP Category Title** | ✅ Yes | 1:1 with AFP Category |
| Any combination of the above (e.g. `(APPN, Fiscal Year)`, `(AFP Category, Fiscal Year)`, `(OSD APPN, AF)`) | ✅ Yes | All derived from the reconciliation grain |
| **AFEEIC Cost Cat / AFEEIC Cost Cat Title** | ❌ No | Different category sets per system (this IS the difference) |
| **CE Title** | ❌ No | Open system uses different cost element labels |
| **BA / BA Name / BSA / BSA Title** | ❌ No | Within-APPN BA distribution is independently sampled |
| **BPAC / BPAC Title** | ❌ No | Synthesized per row, no cross-system correspondence |
| **AFPEC / AFPEC Title / PE / PE Title** | ❌ No | Randomly assigned per row in both systems |
| **OAC / OAC Title** | ❌ No | Random MAJCOM assignment per row |
| **SAG / SAG Title / SPC / SPC Title / CCN / CCN Title / RFC** | ❌ No | Random per row |
| **WSC / WSC Title** | ❌ No | Random weapon system assignment |
| **OP32 Code / OP32 Sub Code / OP32 Title** | ❌ No | Random per row (and only populated for O&M rows) |
| **OCO Ops / OCO Ops Title / OCO ISR / OCO ISR Title / SFI / SFI Title** | ❌ No | Random per row |
| **RIC / RIC Title** | ❌ No | Random per row |
| **Efficiency Title / Position / GLI Category / Act Doc Date** | ❌ No | Random per row |
| **End Strength** | ❌ No | Independently generated per row (and it's a count, not dollars) |

Practical implication: the reconciliation join key in any matching/audit workflow should be a subset of `{APPN, APPN Title, OSD APPN, AF, AFP Category, AFP Category Title, Fiscal Year}`. Trying to reconcile at the BA / BPAC / OAC / AFEEIC level will not match — those are exactly the dimensions where the two systems intentionally diverge.