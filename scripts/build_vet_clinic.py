"""Build a sample veterinary clinic PBIP under out/VetClinic.

Run:  python scripts/build_vet_clinic.py
Then: tmdl-preflight check out/VetClinic

Star schema:
    Patients (dim)   Veterinarians (dim)   Services (dim)   InsuranceProviders (dim)
    Visits (fact)   __Calendar (calc dim)   Clinic Measures
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbip_model_forge.build_model import build_pbip  # noqa: E402


SPEC = {
    "name": "VetClinic",
    "tables": [
        {
            "name": "Patients",
            "description": "One row per animal patient.",
            "columns": [
                {"name": "patient_id", "type": "int64", "key": True},
                {"name": "patient_name", "type": "string",
                 "description": "The animal's name."},
                {"name": "species", "type": "string",
                 "description": "Species, e.g. Dog or Cat."},
                {"name": "breed", "type": "string",
                 "description": "Breed as recorded at registration."},
                {"name": "owner_name", "type": "string",
                 "description": "Name of the animal's owner."},
            ],
            "rows": [
                [1, "Max", "Dog", "Labrador", "John Carter"],
                [2, "Bella", "Cat", "Siamese", "Maria Lopez"],
                [3, "Rocky", "Dog", "Bulldog", "Tom Reed"],
                [4, "Whiskers", "Cat", "Persian", "Anna Kim"],
                [5, "Charlie", "Rabbit", "Dutch", "Sam Patel"],
                [6, "Luna", "Dog", "Poodle", "Emily Chen"],
                [7, "Milo", "Cat", "Tabby", "David Brown"],
                [8, "Coco", "Bird", "Cockatiel", "Rachel Green"],
            ],
        },
        {
            "name": "Veterinarians",
            "description": "Clinic veterinary staff.",
            "columns": [
                {"name": "vet_id", "type": "int64", "key": True},
                {"name": "vet_name", "type": "string",
                 "description": "Veterinarian's name."},
                {"name": "specialty", "type": "string",
                 "description": "Veterinarian's specialty."},
            ],
            "rows": [
                [1, "Dr. Sarah Johnson", "General Practice"],
                [2, "Dr. Michael Chen", "Surgery"],
                [3, "Dr. Priya Nair", "Dermatology"],
                [4, "Dr. James Wilson", "Dentistry"],
            ],
        },
        {
            "name": "Services",
            "description": "Catalog of billable clinic services.",
            "columns": [
                {"name": "service_id", "type": "int64", "key": True},
                {"name": "service_name", "type": "string",
                 "description": "Billable service name."},
                {"name": "category", "type": "string",
                 "description": "Service category, e.g. Preventive or Surgery."},
                {"name": "base_price", "type": "double", "format": "$ #,0.00",
                 "description": "List price of the service, in USD."},
            ],
            "rows": [
                [1, "Wellness Exam", "Preventive", 65.00],
                [2, "Vaccination", "Preventive", 45.00],
                [3, "Dental Cleaning", "Dental", 220.00],
                [4, "Spay/Neuter Surgery", "Surgery", 350.00],
                [5, "X-Ray", "Diagnostic", 150.00],
                [6, "Skin Treatment", "Dermatology", 95.00],
                [7, "Blood Panel", "Diagnostic", 120.00],
                [8, "Grooming", "Wellness", 55.00],
            ],
        },
        {
            "name": "InsuranceProviders",
            "description": "Pet insurance companies covering patients.",
            "columns": [
                {"name": "insurance_provider_id", "type": "int64", "key": True},
                {"name": "provider_name", "type": "string",
                 "description": "Pet insurance company name."},
                {"name": "plan_type", "type": "string",
                 "description": "Insurance plan type."},
                {"name": "coverage_rate", "type": "double", "format": "0%",
                 "description": "Share of a claim the plan reimburses."},
            ],
            "rows": [
                [1, "PetGuard Insurance", "Comprehensive", 0.80],
                [2, "Healthy Paws Co", "Accident & Illness", 0.70],
                [3, "FurCare Plus", "Wellness Plan", 0.50],
                [4, "SafeVet Assurance", "Accident Only", 0.60],
                [5, "Self-Pay", "None", 0.00],
            ],
        },
        {
            "name": "Visits",
            "description": "One row per clinic visit. Core fact table.",
            "hidden": True,
            "columns": [
                {"name": "visit_id", "type": "int64", "hidden": True},
                {"name": "visit_date", "type": "datetime", "hidden": True,
                 "format": "General Date"},
                {"name": "followup_date", "type": "datetime", "hidden": True,
                 "format": "General Date"},
                {"name": "patient_id", "type": "int64", "hidden": True},
                {"name": "vet_id", "type": "int64", "hidden": True},
                {"name": "service_id", "type": "int64", "hidden": True},
                {"name": "insurance_provider_id", "type": "int64", "hidden": True},
                {"name": "duration_minutes", "type": "int64", "hidden": True,
                 "summarizeBy": "sum"},
                {"name": "total_cost", "type": "double", "hidden": True,
                 "summarizeBy": "sum"},
                {"name": "claim_amount", "type": "double", "hidden": True,
                 "summarizeBy": "sum"},
                {"name": "covered_amount", "type": "double", "hidden": True,
                 "summarizeBy": "sum"},
            ],
            "rows": [
                # visit_id, visit_date, followup_date, patient_id, vet_id, service_id,
                # insurance_provider_id, duration_minutes, total_cost, claim_amount, covered_amount
                [5001, dt.date(2024, 1, 10), dt.date(2024, 1, 24), 1, 1, 1, 1, 30, 65.00, 65.00, 52.00],
                [5002, dt.date(2024, 2, 5), dt.date(2024, 2, 19), 2, 3, 6, 2, 45, 95.00, 95.00, 66.50],
                [5003, dt.date(2024, 2, 18), dt.date(2024, 3, 4), 3, 2, 4, 5, 90, 350.00, 0.00, 0.00],
                [5004, dt.date(2024, 3, 3), dt.date(2024, 3, 17), 4, 1, 2, 3, 15, 45.00, 45.00, 22.50],
                [5005, dt.date(2024, 3, 25), dt.date(2024, 4, 8), 5, 1, 1, 5, 30, 65.00, 0.00, 0.00],
                [5006, dt.date(2024, 4, 14), dt.date(2024, 4, 28), 6, 4, 3, 1, 60, 220.00, 220.00, 176.00],
                [5007, dt.date(2024, 5, 2), dt.date(2024, 5, 16), 7, 3, 7, 4, 20, 120.00, 120.00, 72.00],
                [5008, dt.date(2024, 6, 19), dt.date(2024, 7, 3), 8, 1, 1, 5, 25, 60.00, 0.00, 0.00],
                [5009, dt.date(2024, 7, 8), dt.date(2024, 7, 22), 1, 2, 5, 1, 40, 150.00, 150.00, 120.00],
                [5010, dt.date(2024, 8, 21), dt.date(2024, 9, 4), 2, 4, 3, 2, 60, 235.00, 235.00, 164.50],
                [5011, dt.date(2024, 10, 5), dt.date(2024, 10, 19), 3, 1, 2, 5, 15, 45.00, 0.00, 0.00],
                [5012, dt.date(2025, 1, 14), dt.date(2025, 1, 28), 4, 3, 6, 3, 45, 100.00, 100.00, 50.00],
                [5013, dt.date(2025, 2, 27), dt.date(2025, 3, 13), 5, 1, 1, 5, 30, 65.00, 0.00, 0.00],
                [5014, dt.date(2025, 4, 11), dt.date(2025, 4, 25), 6, 2, 4, 1, 90, 350.00, 350.00, 280.00],
                [5015, dt.date(2025, 6, 30), dt.date(2025, 7, 14), 7, 4, 8, 4, 30, 55.00, 55.00, 33.00],
                [5016, dt.date(2025, 9, 8), dt.date(2025, 9, 22), 8, 3, 7, 5, 20, 120.00, 0.00, 0.00],
            ],
        },
    ],
    "calendar": {"name": "__Calendar", "start_year": 2024, "end_year": 2025},
    "measures_table": {
        "name": "Clinic Measures",
        "description": "Measure home table: all user-facing measures live here.",
        "measures": [
            {"name": "Total Revenue", "expression": "SUM(Visits[total_cost])",
             "format": "$ #,0.00", "description": "Total billed revenue across visits."},
            {"name": "Visits #", "expression": "COUNTROWS(Visits)",
             "format": "#,0", "description": "Number of clinic visits."},
            {"name": "Patients #",
             "expression": "DISTINCTCOUNT(Visits[patient_id])", "format": "#,0",
             "description": "Distinct animal patients with a visit in context."},
            {"name": "Avg Cost per Visit",
             "expression": "DIVIDE([Total Revenue], [Visits #])",
             "format": "$ #,0.00", "description": "Average billed revenue per visit."},
            {"name": "Total Visit Hours",
             "expression": "DIVIDE(SUM(Visits[duration_minutes]), 60)",
             "format": "#,0.0", "description": "Total time spent in visits, in hours."},
            {"name": "Total Claims Submitted",
             "expression": "SUM(Visits[claim_amount])", "format": "$ #,0.00",
             "description": "Total dollar amount submitted to pet insurers."},
            {"name": "Total Covered Amount",
             "expression": "SUM(Visits[covered_amount])", "format": "$ #,0.00",
             "description": "Total dollar amount reimbursed by pet insurers."},
            {"name": "Total Out-of-Pocket Revenue",
             "expression": "[Total Revenue] - [Total Covered Amount]",
             "format": "$ #,0.00",
             "description": "Revenue not covered by insurance, i.e. paid by the owner."},
            {"name": "Insurance Reimbursement %",
             "expression": "DIVIDE([Total Covered Amount], [Total Claims Submitted])",
             "format": "0%",
             "description": "Share of submitted claim dollars that insurers reimbursed."},
            {"name": "Insured Visits #",
             "expression": "CALCULATE([Visits #], Visits[claim_amount] > 0)",
             "format": "#,0", "description": "Visits with an insurance claim submitted."},
            {"name": "Insured Visits %",
             "expression": "DIVIDE([Insured Visits #], [Visits #])",
             "format": "0%", "description": "Share of visits with an insurance claim."},
        ],
    },
    "relationships": [
        {"from": "Visits.patient_id", "to": "Patients.patient_id"},
        {"from": "Visits.vet_id", "to": "Veterinarians.vet_id"},
        {"from": "Visits.service_id", "to": "Services.service_id"},
        {"from": "Visits.insurance_provider_id",
         "to": "InsuranceProviders.insurance_provider_id"},
        {"from": "Visits.visit_date", "to": "__Calendar.Date"},
        {"from": "Visits.followup_date", "to": "__Calendar.Date", "active": False},
    ],
}


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "out" / "VetClinic"
    pbip = build_pbip(SPEC, out)
    print(f"Built vet clinic PBIP: {pbip}")


if __name__ == "__main__":
    main()
