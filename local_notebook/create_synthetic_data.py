"""Generate a synthetic Air Force budget dataset.

Uses real DoD appropriation codes, Budget Activity structure, and OP-32 line
numbers to keep the shape realistic; dollar amounts and detailed line text are
fabricated.

Default invocation writes the canonical Excel file:
    uv run python local_notebook/create_synthetic_data.py

To write a single output file with a custom seed and row count:
    uv run python local_notebook/create_synthetic_data.py \
        --seed 12345 --rows 25000 --out data/db_pull_1.csv

To produce both simulated database-pull CSVs in one invocation:
    uv run python local_notebook/create_synthetic_data.py --db-pulls
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260608
N_ROWS = 25_000
FY_RANGE = list(range(2024, 2034))

COLUMNS = [
    "AFPEC", "AFPEC Title", "APPN", "APPN Title", "BA", "BA Name",
    "GLI Category", "BSA", "BSA Title", "OSD APPN", "RFC", "BPAC",
    "BPAC Title", "Act Doc Date", "CCN", "CCN Title", "AFEEIC Cost Cat",
    "AFEEIC Cost Cat Title", "CE Title", "OP32 Code", "OP32 Sub Code",
    "OP32 Title", "RIC", "RIC Title", "AF", "Efficiency Title", "Fiscal Year",
    "Dollars (in $K)", "Dollars (in $M)", "End Strength", "OAC", "OAC Title",
    "SAG", "PE", "SAG Title", "PE Title", "SPC", "SPC Title", "Position",
    "AFP Category", "AFP Category Title", "SFI", "SFI Title", "OCO Ops",
    "OCO Ops Title", "WSC", "WSC Title", "OCO ISR", "OCO ISR Title",
]

# ---------------------------------------------------------------------------
# Hierarchies and lookup tables
# ---------------------------------------------------------------------------

# Real DoD appropriation account symbols for Air Force.
# APPN Title -> (APPN code, OSD APPN family, AFP Category)
APPN_TABLE = {
    "Medicare Retire Contribute - AF":  {"appn": "0540", "osd": "MERHCF", "afp_cat": "MERHCF"},
    "Medicare Retire Contribute - AFR": {"appn": "0540F", "osd": "MERHCF", "afp_cat": "MERHCF"},
    "Medicare Retire Contribute - ANG": {"appn": "0540G", "osd": "MERHCF", "afp_cat": "MERHCF"},
    "Military Personnel - AF":          {"appn": "3500", "osd": "MILPERS", "afp_cat": "MILPERS"},
    "National Guard Personnel - AF":    {"appn": "3830", "osd": "MILPERS", "afp_cat": "MILPERS"},
    "Operation and Maintenance - AF":   {"appn": "3400", "osd": "OM",      "afp_cat": "OM"},
    "Operation and Maintenance - AFR":  {"appn": "3740", "osd": "OM",      "afp_cat": "OM"},
    "Operation and Maintenance - ANG":  {"appn": "3840", "osd": "OM",      "afp_cat": "OM"},
    "Other Procurement - AF":           {"appn": "3080", "osd": "PROC",    "afp_cat": "PROC"},
    "RDT&E - AF":                       {"appn": "3600", "osd": "RDTE",    "afp_cat": "RDTE"},
    "Reserve Personnel - AF":           {"appn": "3700", "osd": "MILPERS", "afp_cat": "MILPERS"},
}

AFP_CATEGORY_TITLES = {
    "MILPERS": "Military Personnel",
    "OM":      "Operation and Maintenance",
    "PROC":    "Procurement",
    "RDTE":    "Research, Development, Test and Evaluation",
    "MERHCF":  "Medicare-Eligible Retiree Health Care Fund Contribution",
}

# Budget Activities by APPN Title. Codes/names follow DoD budget structure.
BA_TABLE = {
    "Military Personnel - AF": [
        ("01", "Pay and Allowances of Officers"),
        ("02", "Pay and Allowances of Enlisted Personnel"),
        ("03", "Pay and Allowances of Cadets"),
        ("04", "Subsistence of Enlisted Personnel"),
        ("05", "Permanent Change of Station Travel"),
        ("06", "Other Military Personnel Costs"),
    ],
    "Reserve Personnel - AF": [
        ("01", "Reserve Component Training and Support"),
    ],
    "National Guard Personnel - AF": [
        ("01", "National Guard Training and Support"),
    ],
    "Operation and Maintenance - AF": [
        ("01", "Operating Forces"),
        ("02", "Mobilization"),
        ("03", "Training and Recruiting"),
        ("04", "Administration and Servicewide Activities"),
    ],
    "Operation and Maintenance - AFR": [
        ("01", "Operating Forces"),
        ("04", "Administration and Servicewide Activities"),
    ],
    "Operation and Maintenance - ANG": [
        ("01", "Operating Forces"),
    ],
    "Other Procurement - AF": [
        ("01", "Aircraft Equipment"),
        ("02", "Vehicular Equipment"),
        ("03", "Electronics and Telecommunications Equipment"),
        ("04", "Other Base Maintenance and Support Equipment"),
        ("05", "Spares and Repair Parts"),
    ],
    "RDT&E - AF": [
        ("01", "Basic Research"),
        ("02", "Applied Research"),
        ("03", "Advanced Technology Development"),
        ("04", "Advanced Component Development and Prototypes"),
        ("05", "System Development and Demonstration"),
        ("06", "RDT&E Management Support"),
        ("07", "Operational System Development"),
    ],
    "Medicare Retire Contribute - AF":  [("01", "MERHCF Contribution - Active")],
    "Medicare Retire Contribute - AFR": [("01", "MERHCF Contribution - Reserve")],
    "Medicare Retire Contribute - ANG": [("01", "MERHCF Contribution - Guard")],
}

# Budget Sub-Activity (BSA) options per BA name (kept compact; sampler picks).
BSA_TABLE = {
    "Operating Forces": [
        ("011", "Primary Combat Forces"),
        ("011A", "Combatant Commanders Direct Mission Support"),
        ("011D", "Facilities Sustainment, Restoration and Modernization"),
        ("011M", "Depot Maintenance"),
        ("011R", "Facilities Operations"),
        ("011W", "Base Support"),
    ],
    "Mobilization": [
        ("012", "Airlift Operations"),
        ("012A", "Mobility Operations"),
        ("012C", "Payments to Transportation Working Capital Fund"),
    ],
    "Training and Recruiting": [
        ("013", "Officer Acquisition"),
        ("013A", "Recruit Training"),
        ("013B", "Reserve Officer Training Corps"),
        ("013C", "Specialized Skill Training"),
        ("013D", "Flight Training"),
        ("013E", "Professional Development Education"),
    ],
    "Administration and Servicewide Activities": [
        ("014", "Logistics Operations"),
        ("014A", "Servicewide Communications"),
        ("014B", "Administration"),
        ("014C", "Servicewide Support Activities"),
        ("014D", "Security Programs"),
    ],
    "Pay and Allowances of Officers": [
        ("101", "Basic Pay"),
        ("102", "Retired Pay Accrual"),
        ("103", "Basic Allowance for Housing"),
        ("104", "Basic Allowance for Subsistence"),
        ("105", "Incentive Pays"),
        ("106", "Special Pays"),
        ("107", "Allowances"),
        ("108", "Separation Payments"),
        ("109", "Social Security Tax"),
    ],
    "Pay and Allowances of Enlisted Personnel": [
        ("201", "Basic Pay"),
        ("202", "Retired Pay Accrual"),
        ("203", "Basic Allowance for Housing"),
        ("204", "Basic Allowance for Subsistence"),
        ("205", "Incentive Pays"),
        ("206", "Special Pays"),
        ("207", "Allowances"),
        ("208", "Separation Payments"),
        ("209", "Social Security Tax"),
    ],
    "Pay and Allowances of Cadets": [
        ("301", "Academy Cadets"),
    ],
    "Subsistence of Enlisted Personnel": [
        ("401", "Subsistence-in-Kind"),
        ("402", "Subsistence Allowance"),
    ],
    "Permanent Change of Station Travel": [
        ("501", "Accession Travel"),
        ("502", "Training Travel"),
        ("503", "Operational Travel"),
        ("504", "Rotational Travel"),
        ("505", "Separation Travel"),
    ],
    "Other Military Personnel Costs": [
        ("601", "Apprehension of Deserters"),
        ("602", "Reserve Officers Training Corps"),
        ("603", "Adoption Expenses"),
        ("604", "Transportation Subsidy"),
    ],
    "Reserve Component Training and Support": [
        ("011", "Unit and Individual Training"),
        ("012", "Reserve Operations Support"),
        ("013", "Administration"),
    ],
    "National Guard Training and Support": [
        ("011", "Unit and Individual Training"),
        ("012", "Guard Operations Support"),
        ("013", "Administration"),
    ],
    "Aircraft Equipment": [
        ("AC01", "Aircraft Modifications"),
        ("AC02", "Aircraft Support Equipment"),
    ],
    "Vehicular Equipment": [
        ("VE01", "Passenger Carrying Vehicles"),
        ("VE02", "Cargo and Utility Vehicles"),
        ("VE03", "Special Purpose Vehicles"),
        ("VE04", "Fire Fighting Equipment"),
        ("VE05", "Material Handling Equipment"),
    ],
    "Electronics and Telecommunications Equipment": [
        ("ET01", "Comm Security Equipment"),
        ("ET02", "Intelligence Programs"),
        ("ET03", "Information Technology"),
        ("ET04", "Long-Haul Communications"),
        ("ET05", "Base Communications Infrastructure"),
    ],
    "Other Base Maintenance and Support Equipment": [
        ("BS01", "Medical/Dental Equipment"),
        ("BS02", "Air Base Operability Equipment"),
        ("BS03", "Photographic Equipment"),
        ("BS04", "Training Equipment"),
        ("BS05", "Mobility Equipment"),
    ],
    "Spares and Repair Parts": [
        ("SR01", "Initial Spares"),
        ("SR02", "Replenishment Spares"),
    ],
    "Basic Research": [
        ("BR01", "Defense Research Sciences"),
        ("BR02", "University Research Initiatives"),
    ],
    "Applied Research": [
        ("AR01", "Materials"),
        ("AR02", "Aerospace Vehicle Technologies"),
        ("AR03", "Human Effectiveness Applied Research"),
        ("AR04", "Sensors and Electronic Combat"),
    ],
    "Advanced Technology Development": [
        ("AT01", "Advanced Materials"),
        ("AT02", "Aerospace Propulsion"),
        ("AT03", "Aerospace Sensors"),
    ],
    "Advanced Component Development and Prototypes": [
        ("AC01", "Long Range Strike"),
        ("AC02", "Hypersonics Prototyping"),
        ("AC03", "Space Control Technology"),
    ],
    "System Development and Demonstration": [
        ("SD01", "Next Gen Air Dominance"),
        ("SD02", "Combat Rescue Helicopter"),
        ("SD03", "B-21 Raider"),
    ],
    "RDT&E Management Support": [
        ("MS01", "Facilities"),
        ("MS02", "Test and Evaluation Support"),
    ],
    "Operational System Development": [
        ("OS01", "F-35 Squadrons"),
        ("OS02", "F-15 EPAW"),
        ("OS03", "B-52 Squadrons"),
        ("OS04", "C-17A Squadrons"),
        ("OS05", "KC-46A Tanker"),
    ],
    "MERHCF Contribution - Active":  [("MR01", "Active Component MERHCF Accrual")],
    "MERHCF Contribution - Reserve": [("MR01", "Reserve Component MERHCF Accrual")],
    "MERHCF Contribution - Guard":   [("MR01", "Guard Component MERHCF Accrual")],
}

# OP-32 categories (used primarily by O&M rows). Codes are real DoD OP-32 lines.
OP32_TABLE = [
    ("101", "00", "Exec, Gen, & Spec Schedules", "CIVPERS"),
    ("103", "00", "Wage Board", "CIVPERS"),
    ("104", "00", "Foreign National Direct Hire", "CIVPERS"),
    ("106", "00", "Benefits to Former Employees", "CIVPERS"),
    ("308", "00", "Travel of Persons", "TRAVEL"),
    ("308", "01", "Travel - Airfare", "TRAVEL"),
    ("308", "02", "Travel - Lodging", "TRAVEL"),
    ("308", "03", "Travel - Meals & Incidentals", "TRAVEL"),
    ("308", "04", "Travel - Rental Cars", "TRAVEL"),
    ("308", "05", "Travel - Mileage Reimbursement", "TRAVEL"),
    ("308", "06", "Travel - Baggage Fees", "TRAVEL"),
    ("401", "00", "DLA Energy (Fuel Products)", "FUEL"),
    ("411", "00", "Army Managed Supplies & Materials", "SUPPLIES"),
    ("414", "00", "Air Force Managed Supplies & Materials", "SUPPLIES"),
    ("415", "00", "DLA Managed Supplies & Materials", "SUPPLIES"),
    ("416", "00", "GSA Managed Supplies & Materials", "SUPPLIES"),
    ("417", "00", "Locally Procured Supplies & Materials", "SUPPLIES"),
    ("424", "00", "Air Force Managed Equipment", "EQUIP"),
    ("502", "00", "Army Industrial Operations", "DWCF"),
    ("506", "00", "DLA Distribution Depot Maintenance", "DWCF"),
    ("507", "00", "GSA Managed Equipment", "EQUIP"),
    ("671", "00", "Communications Services (DISA)", "COMMS"),
    ("673", "00", "Defense Finance and Accounting Service", "DWCF"),
    ("912", "00", "GSA Standard Level User Charges", "RENTS"),
    ("913", "00", "Purchased Utilities (Non-Fund)", "UTIL"),
    ("914", "00", "Purchased Communications (Non-Fund)", "COMMS"),
    ("915", "00", "Rents (Non-GSA)", "RENTS"),
    ("917", "00", "Postal Services (USPS)", "OTHER_SVC"),
    ("920", "00", "Supplies & Materials (Non-Fund)", "SUPPLIES"),
    ("921", "00", "Printing & Reproduction", "OTHER_SVC"),
    ("922", "00", "Equipment Maintenance by Contract", "CONTRACT"),
    ("923", "00", "Facility Maintenance by Contract", "CONTRACT"),
    ("925", "00", "Equipment Purchases (Non-Fund)", "EQUIP"),
    ("932", "00", "Mgmt and Professional Support Services", "CONTRACT"),
    ("933", "00", "Studies, Analyses, and Evaluations", "CONTRACT"),
    ("934", "00", "Engineering and Technical Services", "CONTRACT"),
    ("957", "00", "Land and Structures", "EQUIP"),
    ("985", "00", "Research and Development Contracts", "CONTRACT"),
    ("986", "00", "Medical/Dental Supplies & Equipment", "SUPPLIES"),
    ("987", "00", "Other Intra-Government Purchases", "OTHER_SVC"),
    ("989", "00", "Other Contracts", "CONTRACT"),
    ("990", "00", "IT Contract Services", "CONTRACT"),
    ("998", "00", "Other Costs (Other Purchases)", "OTHER_SVC"),
]

# AFEEIC cost categories per APPN Title. Values for O&M and National Guard
# Personnel come straight from the user's notes; others are kept synthetic but
# follow the same naming style.
_OM_AFEEIC = [
    ("OM01", "Engineering Technical Services"),
    ("OM02", "Fuel"),
    ("OM03", "IT Contracting Services"),
    ("OM04", "Other Services"),
    ("OM05", "Travel Expenses"),
    ("OM06", "Other Services - Other General Training"),
    ("OM07", "Other Services - Acquisition and Non-Acquisition Support"),
    ("OM08", "Other Services - Chaplain Support"),
    ("OM09", "Other Services - Education"),
    ("OM10", "Other Services - Tuition Assistance"),
    ("OM11", "Other Services - In Country Support Cost"),
    ("OM12", "Other Services - Professional Education"),
    ("OM13", "Other Services - Continued Education"),
    ("OM14", "Postal"),
    ("OM15", "Software Depot"),
    ("OM16", "Travel - Airfare"),
    ("OM17", "Travel - Train"),
    ("OM18", "Travel - Rental Cars"),
    ("OM19", "Travel - Mileage Reimbursement"),
    ("OM20", "Travel - Rideshare/Taxi"),
    ("OM21", "Travel - Fuel"),
    ("OM22", "Travel - Lodging"),
    ("OM23", "Travel - Lodging Incidentals"),
    ("OM24", "Travel - Meals"),
    ("OM25", "Travel - Meal Tips"),
    ("OM26", "Travel - Conference and Events"),
    ("OM27", "Travel - Workshop and Training"),
    ("OM28", "Travel - Communication"),
    ("OM29", "Travel - Baggage Fees"),
]

_NGP_AFEEIC = [
    ("NG01", "adm - alert allowances"),
    ("NG02", "adm - enl allowances"),
    ("NG03", "adm - cloth / death gratuities"),
    ("NG04", "adm - travel / allowances / base pay / school allowances"),
    ("NG05", "adm - retired pay / savings"),
]

AFEEIC_BY_APPN = {
    "Military Personnel - AF": [
        ("MP01", "Officer Pay & Allowances"),
        ("MP02", "Enlisted Pay & Allowances"),
        ("MP03", "Cadet Pay & Allowances"),
        ("MP04", "Subsistence"),
        ("MP05", "PCS Travel"),
        ("MP06", "Special Pays"),
    ],
    "Reserve Personnel - AF": [
        ("RP01", "Reserve Pay - Drill"),
        ("RP02", "Reserve Pay - Active Duty Training"),
        ("RP03", "Reserve Special Pays"),
    ],
    "National Guard Personnel - AF": _NGP_AFEEIC,
    "Operation and Maintenance - AF":  _OM_AFEEIC,
    "Operation and Maintenance - AFR": _OM_AFEEIC,
    "Operation and Maintenance - ANG": _OM_AFEEIC,
    "Other Procurement - AF": [
        ("OP01", "Vehicles"),
        ("OP02", "Electronics Equipment"),
        ("OP03", "Communications Equipment"),
        ("OP04", "Base Support Equipment"),
        ("OP05", "Spares and Repair Parts"),
    ],
    "RDT&E - AF": [
        ("RD01", "Basic Research Contracts"),
        ("RD02", "Applied Research Contracts"),
        ("RD03", "Advanced Tech Dev Contracts"),
        ("RD04", "Prototype Development"),
        ("RD05", "System Test and Evaluation"),
        ("RD06", "RDT&E Civilian Personnel"),
    ],
    "Medicare Retire Contribute - AF":  [("MR01", "MERHCF Accrual - Active")],
    "Medicare Retire Contribute - AFR": [("MR02", "MERHCF Accrual - Reserve")],
    "Medicare Retire Contribute - ANG": [("MR03", "MERHCF Accrual - Guard")],
}

# Cost Element (CE Title) values per AFEEIC Cost Cat Title. The AFEIC sample
# list from the user's notes is folded in here where it fits.
CE_TITLES_BY_AFEEIC = {
    # MilPers
    "Officer Pay & Allowances":  ["AF - officers", "active AF officers", "Basic Pay - Officers", "BAH - Officers", "BAS - Officers"],
    "Enlisted Pay & Allowances": ["AF - enlisted", "Basic Pay - Enlisted", "BAH - Enlisted", "BAS - Enlisted", "Reenlistment Bonus"],
    "Cadet Pay & Allowances":    ["USAFA Cadet Pay"],
    "Subsistence":               ["Subsistence-in-Kind", "BAS - Enlisted"],
    "PCS Travel":                ["Travel - Civilian PCS", "Accession Travel", "Rotational Travel", "Separation Travel"],
    "Special Pays":              ["Aviator Continuation Pay", "Hostile Fire Pay", "Hazardous Duty Pay"],
    # Reserve / Guard pay
    "Reserve Pay - Drill":                ["adm - enl allow", "Inactive Duty Training Pay", "Annual Tour Pay"],
    "Reserve Pay - Active Duty Training": ["adm - enl base pay", "ADT Pay", "ADT Allowances"],
    "Reserve Special Pays":               ["Reserve Flight Pay"],
    # National Guard Personnel CE Titles (user-listed style)
    "adm - alert allowances":                                    ["adc Alert", "adm - enl allow"],
    "adm - enl allowances":                                      ["adm - enl allow", "adm - enl other pay"],
    "adm - cloth / death gratuities":                            ["adm - enl cloth", "adm - enl death gratuities"],
    "adm - travel / allowances / base pay / school allowances":  ["adm - enl base pay", "adm - enl off base"],
    "adm - retired pay / savings":                               ["adm - enl ret pay", "adm - enl ret pay cc"],
    # O&M
    "Engineering Technical Services":                                  ["Architect Engineering Services", "Engineering Tech Services"],
    "Fuel":                                                            ["Jet Fuel JP-8", "Vehicle Gasoline", "Diesel"],
    "IT Contracting Services":                                         ["A& AS IT Studies", "Cloud Services", "Software Licenses", "Cybersecurity Services"],
    "Other Services":                                                  ["Other Services - Acquisition and Non-Acquisition", "Cyber Ops"],
    "Travel Expenses":                                                 ["TDY Travel - Airfare", "TDY Travel - Lodging", "TDY Travel - Per Diem"],
    "Other Services - Other General Training":                         ["Other Services - Other General Training"],
    "Other Services - Acquisition and Non-Acquisition Support":        ["Other Services - Acquisition and Non-Acquisition"],
    "Other Services - Chaplain Support":                               ["Chaplain Services"],
    "Other Services - Education":                                      ["General Education Services"],
    "Other Services - Tuition Assistance":                             ["Tuition Assistance Program"],
    "Other Services - In Country Support Cost":                        ["In Country Support Services"],
    "Other Services - Professional Education":                         ["Other Services - Other General Training", "Professional Education Services"],
    "Other Services - Continued Education":                            ["Continued Education Services"],
    "Postal":                                                          ["Postal"],
    "Software Depot":                                                  ["Software Depot Services"],
    "Travel - Airfare":                                                ["Travel - Conference Travel Expenses", "Travel - Mission Support"],
    "Travel - Train":                                                  ["Rail Transport - TDY"],
    "Travel - Rental Cars":                                            ["Rental Car - TDY"],
    "Travel - Mileage Reimbursement":                                  ["POV Mileage Reimbursement"],
    "Travel - Rideshare/Taxi":                                         ["Rideshare/Taxi - TDY"],
    "Travel - Fuel":                                                   ["TDY Vehicle Fuel"],
    "Travel - Lodging":                                                ["Travel - AFRC Mandatory Support", "Travel - ANG Mandatory Support", "Lodging - CONUS", "Lodging - OCONUS"],
    "Travel - Lodging Incidentals":                                    ["Lodging Incidentals"],
    "Travel - Meals":                                                  ["Per Diem - Meals"],
    "Travel - Meal Tips":                                              ["Per Diem - Meal Tips"],
    "Travel - Conference and Events":                                  ["Travel - Conference Travel Expenses"],
    "Travel - Workshop and Training":                                  ["Travel - Schools and Training"],
    "Travel - Communication":                                          ["TDY Communications"],
    "Travel - Baggage Fees":                                           ["Excess Baggage Fees"],
    # Procurement
    "Vehicles":                  ["Passenger Vehicles", "Cargo Trucks", "Material Handling Equipment"],
    "Electronics Equipment":     ["Radar Systems", "Sensors", "Test Equipment"],
    "Communications Equipment":  ["Radios", "Satcom Terminals", "Network Switches"],
    "Base Support Equipment":    ["Generators", "Fire Trucks", "Medical Equipment"],
    "Spares and Repair Parts":   ["Initial Spares", "Replenishment Spares"],
    # RDT&E
    "Basic Research Contracts":     ["University Research Awards", "Defense Research Sciences"],
    "Applied Research Contracts":   ["Materials Research", "Aerospace Sciences"],
    "Advanced Tech Dev Contracts":  ["Hypersonics Tech", "Directed Energy"],
    "Prototype Development":        ["NGAD Prototype", "Hypersonics Prototype"],
    "System Test and Evaluation":   ["Flight Test", "Range Operations"],
    "RDT&E Civilian Personnel":     ["RDT&E Civilian Salaries"],
    # MERHCF
    "MERHCF Accrual - Active":  ["MERHCF Active Accrual"],
    "MERHCF Accrual - Reserve": ["MERHCF Reserve Accrual"],
    "MERHCF Accrual - Guard":   ["MERHCF Guard Accrual"],
}

# AFPEC: real AF PEC numbers (Program Element Codes) with suffix letter
# A=Active, B=Backup, C=Combined, D=Develop, R=Reserve, G=Guard.
AFPEC_BASES = [
    ("11212", "F-15 Squadrons"),
    ("11213", "F-22 Squadrons"),
    ("11214", "F-35 Squadrons"),
    ("11227", "Combat Rescue Squadrons"),
    ("11314", "B-1B Squadrons"),
    ("11315", "B-52 Squadrons"),
    ("12410", "Air Operations Center"),
    ("21111", "Strategic Mission Support"),
    ("27431", "Cyberspace Operations"),
    ("28030", "Space Control"),
    ("31111", "C-17A Squadrons"),
    ("31112", "KC-46A Tanker Squadrons"),
    ("31113", "C-130 Airlift"),
    ("35208", "Mission Support Operations"),
    ("41119", "Specialized Skill Training"),
    ("41318", "Flight Training"),
    ("42500", "Recruiting Activities"),
    ("65xxx", "Acquisition Workforce"),
    ("72207", "Servicewide Communications"),
    ("84751", "Test and Evaluation Support"),
    ("87890", "Defense Health Program Support"),
]
AFPEC_SUFFIX_BY_APPN = {
    "Military Personnel - AF":          ["A"],
    "Reserve Personnel - AF":           ["R"],
    "National Guard Personnel - AF":    ["G"],
    "Operation and Maintenance - AF":   ["A", "B"],
    "Operation and Maintenance - AFR":  ["R"],
    "Operation and Maintenance - ANG":  ["G"],
    "Other Procurement - AF":           ["A", "B"],
    "RDT&E - AF":                       ["D"],
    "Medicare Retire Contribute - AF":  ["A"],
    "Medicare Retire Contribute - AFR": ["R"],
    "Medicare Retire Contribute - ANG": ["G"],
}

# Operating Agency Codes (AF MAJCOM short codes).
OAC_TABLE = [
    ("AFGSC", "Air Force Global Strike Command"),
    ("AMC",   "Air Mobility Command"),
    ("ACC",   "Air Combat Command"),
    ("AETC",  "Air Education and Training Command"),
    ("AFMC",  "Air Force Materiel Command"),
    ("AFSOC", "Air Force Special Operations Command"),
    ("PACAF", "Pacific Air Forces"),
    ("USAFE", "US Air Forces in Europe"),
    ("AFRC",  "Air Force Reserve Command"),
    ("ANG",   "Air National Guard"),
    ("SAF",   "Office of the Secretary of the Air Force"),
    ("AFDW",  "Air Force District of Washington"),
    ("AU",    "Air University"),
    ("USAFA", "United States Air Force Academy"),
]
OAC_BY_COMPONENT = {
    "AF":  ["AFGSC", "AMC", "ACC", "AETC", "AFMC", "AFSOC", "PACAF", "USAFE", "SAF", "AFDW", "AU", "USAFA"],
    "AFR": ["AFRC"],
    "ANG": ["ANG"],
}

# Weapon System Codes (real AF WSC families with synthetic suffix).
WSC_TABLE = [
    ("AC0001", "F-15 Eagle"),
    ("AC0002", "F-16 Fighting Falcon"),
    ("AC0003", "F-22 Raptor"),
    ("AC0004", "F-35A Lightning II"),
    ("AC0010", "B-1B Lancer"),
    ("AC0011", "B-2 Spirit"),
    ("AC0012", "B-52H Stratofortress"),
    ("AC0020", "C-17A Globemaster III"),
    ("AC0021", "C-130J Super Hercules"),
    ("AC0030", "KC-46A Pegasus"),
    ("AC0031", "KC-135R Stratotanker"),
    ("AC0040", "RQ-4 Global Hawk"),
    ("AC0041", "MQ-9 Reaper"),
    ("AC0050", "HH-60W Combat Rescue Helicopter"),
    ("SP0001", "GPS III"),
    ("SP0002", "Space Surveillance Network"),
    ("CY0001", "Cyber Mission Force"),
    ("NA",     "Non-Weapon System"),
]

# Geographic OCO operations.
OCO_OPS_TABLE = [
    ("00", "Non-OCO"),
    ("OFS", "Operation Freedom's Sentinel"),
    ("OIR", "Operation Inherent Resolve"),
    ("OAR", "Operation Atlantic Resolve"),
    ("OSE", "Operation Spartan Shield"),
]
OCO_ISR_TABLE = [
    ("00", "Non-OCO ISR"),
    ("ISR1", "Persistent ISR - CENTCOM"),
    ("ISR2", "Persistent ISR - INDOPACOM"),
    ("ISR3", "Persistent ISR - EUCOM"),
]

# Routing Identifier Codes (real DoD RIC families).
RIC_TABLE = [
    ("FB", "Air Force Base Supply"),
    ("FE", "Air Force Depot Maintenance"),
    ("FH", "Air Force Working Capital Fund - Supply"),
    ("FK", "Air Force Acquisition"),
    ("FL", "Air Force Civil Engineering"),
    ("FM", "Air Force Medical Service"),
    ("S9I", "DLA - Aviation"),
    ("S9G", "DLA - Energy"),
    ("S9M", "DLA - Maritime"),
    ("S9T", "DLA - Troop Support"),
    ("GS00", "GSA Federal Supply Service"),
]

SFI_TABLE = [
    ("00", "Non-SFI"),
    ("CY", "Cybersecurity Initiative"),
    ("HY", "Hypersonics"),
    ("NG", "Next Gen Air Dominance"),
    ("SP", "Space Force Realignment"),
    ("AI", "AI/ML Initiative"),
]

EFFICIENCY_TITLES = [
    "",  # most rows have no efficiency
    "Category Management Savings",
    "Audit Remediation Savings",
    "Travel Policy Compression",
    "Print Reduction Initiative",
    "Software License Rationalization",
    "Energy Conservation Investment Program",
    "Facility Footprint Reduction",
]

POSITION_TITLES = [
    "", "Program Manager", "Contracting Officer", "Financial Analyst",
    "Logistician", "Engineer", "Maintenance Officer", "Pilot",
    "Boom Operator", "Intelligence Analyst", "Cyber Operator",
]

GLI_CATEGORIES = ["Direct", "Reimbursable", "Transfer", "Allotment"]

# Dollar generation tiers per AFP_CAT (in $K).
DOLLAR_TIERS = {
    "MILPERS": (50, 50_000),     # $50K - $50M per line
    "OM":      (5, 20_000),      # $5K - $20M per line
    "PROC":    (50, 80_000),     # $50K - $80M per line
    "RDTE":    (50, 120_000),    # $50K - $120M per line
    "MERHCF":  (500, 500_000),   # $500K - $500M per line (large accrual lines)
}

# Override tiers for specific AFEEIC Cost Cat Titles where the category dictates
# the dollar scale. Values are ($K min, $K max) — fuel/travel line items stay
# realistic instead of being scaled by APPN-level defaults.
AFEEIC_TIER_OVERRIDES = {
    # O&M - travel sub-categories: small individual line items
    "Travel Expenses":                     (5, 800),
    "Travel - Airfare":                    (2, 600),
    "Travel - Train":                      (1, 50),
    "Travel - Rental Cars":                (1, 80),
    "Travel - Mileage Reimbursement":      (1, 30),
    "Travel - Rideshare/Taxi":             (1, 20),
    "Travel - Fuel":                       (1, 50),
    "Travel - Lodging":                    (2, 400),
    "Travel - Lodging Incidentals":        (1, 20),
    "Travel - Meals":                      (1, 60),
    "Travel - Meal Tips":                  (1, 5),
    "Travel - Conference and Events":      (5, 500),
    "Travel - Workshop and Training":      (5, 600),
    "Travel - Communication":              (1, 40),
    "Travel - Baggage Fees":               (1, 10),
    # O&M - other services and infrastructure
    "Fuel":                                (50, 24_000),
    "Engineering Technical Services":      (50, 15_000),
    "IT Contracting Services":             (50, 18_000),
    "Software Depot":                      (50, 8_000),
    "Postal":                              (5, 500),
    "Other Services":                      (20, 12_000),
    "Other Services - Other General Training":              (10, 5_000),
    "Other Services - Acquisition and Non-Acquisition Support": (20, 10_000),
    "Other Services - Chaplain Support":                    (5, 1_500),
    "Other Services - Education":                           (10, 5_000),
    "Other Services - Tuition Assistance":                  (5, 3_000),
    "Other Services - In Country Support Cost":             (20, 12_000),
    "Other Services - Professional Education":              (10, 5_000),
    "Other Services - Continued Education":                 (10, 4_000),
    # Procurement
    "Vehicles":                  (100, 25_000),
    "Electronics Equipment":     (200, 60_000),
    "Communications Equipment":  (100, 40_000),
    "Base Support Equipment":    (50, 20_000),
    "Spares and Repair Parts":   (20, 12_000),
    # NGP detail lines stay modest (personnel allowances)
    "adm - alert allowances":                                    (10, 8_000),
    "adm - enl allowances":                                      (10, 6_000),
    "adm - cloth / death gratuities":                            (5, 3_000),
    "adm - travel / allowances / base pay / school allowances":  (20, 15_000),
    "adm - retired pay / savings":                               (50, 30_000),
}


# ---------------------------------------------------------------------------
# Sampler
# ---------------------------------------------------------------------------

def build_rows(n: int, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    appn_titles = list(APPN_TABLE.keys())
    # Weight APPNs roughly by real budget share so the dataset isn't flat.
    appn_weights = {
        "Military Personnel - AF":          22,
        "National Guard Personnel - AF":     4,
        "Reserve Personnel - AF":            4,
        "Operation and Maintenance - AF":   28,
        "Operation and Maintenance - AFR":   4,
        "Operation and Maintenance - ANG":   6,
        "Other Procurement - AF":           10,
        "RDT&E - AF":                       16,
        "Medicare Retire Contribute - AF":   4,
        "Medicare Retire Contribute - AFR":  1,
        "Medicare Retire Contribute - ANG":  1,
    }
    weights = [appn_weights[t] for t in appn_titles]

    rows = []
    for _ in range(n):
        appn_title = rng.choices(appn_titles, weights=weights, k=1)[0]
        appn_meta = APPN_TABLE[appn_title]
        appn_code = appn_meta["appn"]
        afp_cat = appn_meta["afp_cat"]
        component = (
            "AFR" if "AFR" in appn_title or appn_title == "Reserve Personnel - AF"
            else "ANG" if "ANG" in appn_title or appn_title == "National Guard Personnel - AF"
            else "AF"
        )

        ba_code, ba_name = rng.choice(BA_TABLE[appn_title])
        bsa_options = BSA_TABLE.get(ba_name, [(ba_code + "0", ba_name + " - General")])
        bsa_code, bsa_title = rng.choice(bsa_options)
        # SAG mirrors BSA in this dataset (both are sub-activity groupings).
        sag_code, sag_title = bsa_code, bsa_title

        # BPAC: derive a code combining APPN + BSA + a sequential digit; title from BSA + a noun.
        bpac_seq = rng.randint(1, 99)
        bpac_code = f"{appn_code[:4]}{bsa_code}{bpac_seq:02d}"
        bpac_modifier = rng.choice(["Operations", "Sustainment", "Modernization", "Support", "Readiness"])
        bpac_title = f"{bsa_title} - {bpac_modifier}"

        afeeic_code, afeeic_title = rng.choice(AFEEIC_BY_APPN[appn_title])
        ce_title = rng.choice(CE_TITLES_BY_AFEEIC.get(afeeic_title, [afeeic_title]))

        # OP-32 only meaningful for O&M; otherwise leave blank
        if afp_cat == "OM":
            op32 = rng.choice(OP32_TABLE)
            op32_code, op32_sub, op32_title = op32[0], op32[1], op32[2]
        else:
            op32_code = op32_sub = op32_title = ""

        afpec_base, afpec_program = rng.choice(AFPEC_BASES)
        afpec_suffix = rng.choice(AFPEC_SUFFIX_BY_APPN[appn_title])
        afpec = f"{afpec_base}{afpec_suffix}"
        afpec_title = afpec_program

        # PE = AFPEC base (Program Element); PE Title = program name
        pe_code = afpec_base
        pe_title = afpec_program

        oac_code = rng.choice(OAC_BY_COMPONENT[component])
        oac_title = dict(OAC_TABLE)[oac_code]

        wsc_code, wsc_title = rng.choice(WSC_TABLE)
        oco_ops_code, oco_ops_title = rng.choices(
            OCO_OPS_TABLE, weights=[80, 5, 5, 5, 5], k=1
        )[0]
        oco_isr_code, oco_isr_title = rng.choices(
            OCO_ISR_TABLE, weights=[85, 5, 5, 5], k=1
        )[0]
        ric_code, ric_title = rng.choice(RIC_TABLE)
        sfi_code, sfi_title = rng.choices(SFI_TABLE, weights=[70, 6, 6, 6, 6, 6], k=1)[0]

        efficiency_title = rng.choices(
            EFFICIENCY_TITLES, weights=[85] + [15 / (len(EFFICIENCY_TITLES) - 1)] * (len(EFFICIENCY_TITLES) - 1), k=1,
        )[0]
        position = rng.choices(
            POSITION_TITLES, weights=[60] + [40 / (len(POSITION_TITLES) - 1)] * (len(POSITION_TITLES) - 1), k=1,
        )[0]

        fy = rng.choice(FY_RANGE)
        # Year-over-year growth ~3% baseline so dollars trend upward.
        fy_factor = 1.03 ** (fy - 2024)

        low_k, high_k = AFEEIC_TIER_OVERRIDES.get(afeeic_title, DOLLAR_TIERS[afp_cat])
        dollars_k = np_rng.lognormal(mean=np.log(np.sqrt(low_k * high_k)), sigma=0.9)
        dollars_k = float(np.clip(dollars_k, low_k, high_k * 3)) * fy_factor
        dollars_k = round(dollars_k, 1)
        dollars_m = round(dollars_k / 1000.0, 4)

        # End Strength only meaningful for MilPers categories.
        if afp_cat == "MILPERS":
            end_strength = int(np_rng.lognormal(mean=np.log(150), sigma=1.0))
            end_strength = int(np.clip(end_strength, 1, 5000))
        else:
            end_strength = 0

        # Act Doc Date: somewhere in the FY (Oct prior year - Sep of FY).
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        cal_year = fy if month <= 9 else fy - 1
        act_doc_date = f"{cal_year:04d}-{month:02d}-{day:02d}"

        # CCN: synthetic contract / cost-control number, title is a short descriptor.
        ccn = f"{appn_code[:4]}-{rng.randint(10000, 99999)}-{rng.choice('ABCDEFGH')}"
        ccn_title = f"{bpac_modifier} - {ce_title}"

        # SPC: Standard Program Code (synthetic 4-digit).
        spc = f"S{rng.randint(100, 999)}"
        spc_title = f"{afpec_program} - {bpac_modifier}"

        rows.append({
            "AFPEC": afpec,
            "AFPEC Title": afpec_title,
            "APPN": appn_code,
            "APPN Title": appn_title,
            "BA": ba_code,
            "BA Name": ba_name,
            "GLI Category": rng.choices(GLI_CATEGORIES, weights=[80, 12, 4, 4], k=1)[0],
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
            "PE Title": pe_title,
            "SPC": spc,
            "SPC Title": spc_title,
            "Position": position,
            "AFP Category": afp_cat,
            "AFP Category Title": AFP_CATEGORY_TITLES[afp_cat],
            "SFI": sfi_code,
            "SFI Title": sfi_title,
            "OCO Ops": oco_ops_code,
            "OCO Ops Title": oco_ops_title,
            "WSC": wsc_code,
            "WSC Title": wsc_title,
            "OCO ISR": oco_isr_code,
            "OCO ISR Title": oco_isr_title,
        })

    return pd.DataFrame(rows, columns=COLUMNS)


def _write(df: pd.DataFrame, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".csv":
        df.to_csv(out, index=False)
    else:
        df.to_excel(out, index=False, sheet_name="Data")
    print(f"Wrote {out}: {len(df):,} rows x {len(df.columns)} cols, "
          f"sum=${df['Dollars (in $K)'].sum():,.0f}K")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED, help="RNG seed")
    parser.add_argument("--rows", type=int, default=N_ROWS, help="row count")
    parser.add_argument("--out", type=Path, default=None,
                        help="output file (.xlsx or .csv). Default: data/synthetic_data_red_side.xlsx")
    parser.add_argument("--db-pulls", action="store_true",
                        help="generate data/db_pull_1.csv and data/db_pull_2.csv "
                             "with different seeds (overrides --seed/--out)")
    args = parser.parse_args()

    data_dir = Path(__file__).resolve().parents[1] / "data"

    if args.db_pulls:
        for seed, name in [(70001, "db_pull_1.csv"), (70002, "db_pull_2.csv")]:
            df = build_rows(args.rows, seed)
            _write(df, data_dir / name)
        return

    out = args.out if args.out is not None else data_dir / "synthetic_data_red_side.xlsx"
    df = build_rows(args.rows, args.seed)
    _write(df, out)


if __name__ == "__main__":
    main()