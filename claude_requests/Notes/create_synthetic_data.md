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
- Reserve Personnel -AF

`APPN Title` and AFEIC Cost Cat title are hierachial 

Example: 
National Guard Peronnel - AF: 
* adm alert allowances
* adm - enl allowances
* adm - cloth / death gratuities
* adm - travel / allowances / base pay / school allowances/ base pay/ retired pay/ savings. 


Operational and Maintenance AF -> AFEIC Title, 
`AFEIC` Title Sample Values: 
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

* Create an Excel spreadsheet in [data](../../data) with right column headings
* 

### Status