"""Build a sample hospital PBIP under out/Hospital.

Run:  python scripts/build_hospital.py
Then: tmdl-preflight check out/Hospital

Star schema (snowflaked on insurance):
    Patients  (dim)   Physicians (dim)   Departments (dim)   Diagnoses (dim)
    InsuranceCompanies (dim, ->Patients)
    Encounters (fact)   __Calendar (calc dim)   Clinic Measures (measures-only)
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbip_model_forge.build_model import build_pbip  # noqa: E402


SPEC = {
    "name": "Hospital",
    "tables": [
        {
            "name": "Patients",
            "description": "One row per patient.",
            "columns": [
                {"name": "patient_id", "type": "int64", "key": True},
                {"name": "patient_name", "type": "string"},
                {"name": "gender", "type": "string"},
                {"name": "age", "type": "int64"},
                {"name": "insurance_company_id", "type": "int64"},
            ],
            "rows": [
                [1, "John Whitfield", "Male", 45, 1],
                [2, "Maria Gonzalez", "Female", 62, 3],
                [3, "Wei Chen", "Male", 34, 2],
                [4, "Aisha Rahman", "Female", 29, 4],
                [5, "Robert Klein", "Male", 71, 3],
                [6, "Emily Novak", "Female", 8, 5],
            ],
        },
        {
            "name": "InsuranceCompanies",
            "description": "Insurance payer directory.",
            "columns": [
                {"name": "company_id", "type": "int64", "key": True},
                {"name": "company_name", "type": "string"},
                {"name": "plan_type", "type": "string"},
                {"name": "network_type", "type": "string"},
            ],
            "rows": [
                [1, "Blue Cross Blue Shield", "PPO", "In-Network"],
                [2, "UnitedHealthcare", "HMO", "In-Network"],
                [3, "Medicare", "Government", "National"],
                [4, "Medicaid", "Government", "National"],
                [5, "Aetna", "PPO", "In-Network"],
            ],
        },
        {
            "name": "Physicians",
            "description": "Attending physician directory.",
            "columns": [
                {"name": "physician_id", "type": "int64", "key": True},
                {"name": "physician_name", "type": "string"},
                {"name": "specialty", "type": "string"},
            ],
            "rows": [
                [1, "Dr. Sarah Bennett", "Cardiology"],
                [2, "Dr. James Okafor", "Orthopedics"],
                [3, "Dr. Lisa Tran", "Pediatrics"],
                [4, "Dr. Michael Reyes", "Emergency Medicine"],
                [5, "Dr. Anna Kowalski", "Internal Medicine"],
            ],
        },
        {
            "name": "Departments",
            "description": "Hospital department / ward directory.",
            "columns": [
                {"name": "department_id", "type": "int64", "key": True},
                {"name": "department_name", "type": "string"},
                {"name": "floor", "type": "string"},
            ],
            "rows": [
                [1, "Cardiology", "Floor 3"],
                [2, "Orthopedics", "Floor 2"],
                [3, "Pediatrics", "Floor 4"],
                [4, "Emergency", "Ground Floor"],
                [5, "Internal Medicine", "Floor 3"],
            ],
        },
        {
            "name": "Diagnoses",
            "description": "Diagnosis code reference.",
            "columns": [
                {"name": "diagnosis_id", "type": "int64", "key": True},
                {"name": "diagnosis_code", "type": "string"},
                {"name": "diagnosis_description", "type": "string"},
                {"name": "category", "type": "string"},
            ],
            "rows": [
                [1, "I21.9", "Acute myocardial infarction", "Cardiovascular"],
                [2, "S72.001A", "Fracture of femur", "Musculoskeletal"],
                [3, "J45.909", "Asthma, unspecified", "Respiratory"],
                [4, "E11.9", "Type 2 diabetes mellitus", "Endocrine"],
                [5, "A09", "Infectious gastroenteritis", "Infectious Disease"],
                [6, "I10", "Essential hypertension", "Cardiovascular"],
            ],
        },
        {
            "name": "Encounters",
            "description": "One row per patient encounter/admission. Core fact table.",
            "hidden": True,
            "columns": [
                {"name": "encounter_id", "type": "int64", "hidden": True},
                {"name": "admission_date", "type": "datetime", "hidden": True,
                 "format": "General Date"},
                {"name": "discharge_date", "type": "datetime", "hidden": True,
                 "format": "General Date"},
                {"name": "patient_id", "type": "int64", "hidden": True},
                {"name": "physician_id", "type": "int64", "hidden": True},
                {"name": "department_id", "type": "int64", "hidden": True},
                {"name": "diagnosis_id", "type": "int64", "hidden": True},
                {"name": "length_of_stay", "type": "int64", "hidden": True,
                 "summarizeBy": "sum"},
                {"name": "billed_amount", "type": "double", "hidden": True,
                 "summarizeBy": "sum"},
            ],
            "rows": [
                [2001, dt.date(2024, 1, 5), dt.date(2024, 1, 9), 1, 1, 1, 1, 4, 18500.00],
                [2002, dt.date(2024, 1, 20), dt.date(2024, 1, 21), 2, 4, 4, 6, 1, 3200.00],
                [2003, dt.date(2024, 2, 14), dt.date(2024, 2, 20), 3, 2, 2, 2, 6, 27500.00],
                [2004, dt.date(2024, 3, 2), dt.date(2024, 3, 3), 4, 3, 3, 3, 1, 4100.00],
                [2005, dt.date(2024, 3, 25), dt.date(2024, 3, 27), 5, 1, 1, 6, 2, 9800.00],
                [2006, dt.date(2024, 4, 10), dt.date(2024, 4, 11), 6, 3, 3, 3, 1, 3600.00],
                [2007, dt.date(2024, 5, 18), dt.date(2024, 5, 19), 1, 4, 4, 5, 1, 2900.00],
                [2008, dt.date(2024, 6, 22), dt.date(2024, 6, 30), 2, 1, 1, 1, 8, 42000.00],
                [2009, dt.date(2024, 7, 14), dt.date(2024, 7, 15), 3, 4, 4, 5, 1, 2750.00],
                [2010, dt.date(2024, 8, 9), dt.date(2024, 8, 16), 5, 2, 2, 2, 7, 31000.00],
                [2011, dt.date(2024, 9, 27), dt.date(2024, 9, 28), 4, 5, 5, 4, 1, 3300.00],
                [2012, dt.date(2024, 11, 5), dt.date(2024, 11, 6), 6, 5, 5, 6, 1, 2600.00],
                [2013, dt.date(2025, 1, 12), dt.date(2025, 1, 14), 2, 5, 5, 4, 2, 6100.00],
                [2014, dt.date(2025, 2, 20), dt.date(2025, 2, 21), 1, 3, 3, 3, 1, 3400.00],
                [2015, dt.date(2025, 4, 8), dt.date(2025, 4, 15), 5, 1, 1, 1, 7, 39500.00],
                [2016, dt.date(2025, 5, 30), dt.date(2025, 5, 31), 3, 4, 4, 5, 1, 2950.00],
            ],
        },
    ],
    "calendar": {"name": "__Calendar", "start_year": 2024, "end_year": 2025},
    "measures_table": {
        "name": "Clinic Measures",
        "description": "Measure home table: all user-facing measures live here.",
        "measures": [
            {"name": "Total Billed Revenue",
             "expression": "SUM(Encounters[billed_amount])",
             "format": "$ #,0.00", "description": "Total billed amount across encounters."},
            {"name": "Encounters #",
             "expression": "DISTINCTCOUNT(Encounters[encounter_id])",
             "format": "#,0"},
            {"name": "Total Patient Days",
             "expression": "SUM(Encounters[length_of_stay])",
             "format": "#,0"},
            {"name": "Avg Length of Stay",
             "expression": "AVERAGE(Encounters[length_of_stay])",
             "format": "#,0.0"},
            {"name": "Avg Billed per Encounter",
             "expression": "DIVIDE([Total Billed Revenue], [Encounters #])",
             "format": "$ #,0.00"},
            {"name": "Insured Patients #",
             "expression": "DISTINCTCOUNT(Patients[patient_id])",
             "format": "#,0",
             "description": "Distinct patients in context, e.g. sliced by insurer."},
            {"name": "Avg Billed per Patient",
             "expression": "DIVIDE([Total Billed Revenue], [Insured Patients #])",
             "format": "$ #,0.00"},
            {"name": "Revenue Share by Insurer",
             "expression": (
                 "DIVIDE([Total Billed Revenue], "
                 "CALCULATE([Total Billed Revenue], ALL(InsuranceCompanies)))"
             ),
             "format": "0.0%",
             "description": "This insurer's share of total billed revenue."},
        ],
    },
    "relationships": [
        {"from": "Encounters.patient_id", "to": "Patients.patient_id"},
        {"from": "Encounters.physician_id", "to": "Physicians.physician_id"},
        {"from": "Encounters.department_id", "to": "Departments.department_id"},
        {"from": "Encounters.diagnosis_id", "to": "Diagnoses.diagnosis_id"},
        {"from": "Encounters.admission_date", "to": "__Calendar.Date"},
        {"from": "Encounters.discharge_date", "to": "__Calendar.Date", "active": False},
        {"from": "Patients.insurance_company_id", "to": "InsuranceCompanies.company_id"},
    ],
}


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "out" / "Hospital"
    pbip = build_pbip(SPEC, out)
    print(f"Built hospital PBIP: {pbip}")


if __name__ == "__main__":
    main()
