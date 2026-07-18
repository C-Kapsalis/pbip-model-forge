"""Build a sample Physiotherapy Clinic PBIP.

Run:  python scripts/build_physio.py
Then: tmdl-preflight check out/PhysioClinic

Star schema:
    Patients (dim)  Therapists (dim)  TreatmentTypes (dim)
    Visits (fact)   __Calendar (calc dim)   Measures
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbip_model_forge.build_model import build_pbip  # noqa: E402


SPEC = {
    "name": "PhysioClinic",
    "tables": [
        {
            "name": "Patients",
            "description": "One row per patient registered at the clinic.",
            "columns": [
                {"name": "patient_id", "type": "int64", "key": True},
                {"name": "patient_name", "type": "string"},
                {"name": "gender", "type": "string"},
                {"name": "age_band", "type": "string"},
                {"name": "referral_source", "type": "string"},
                {"name": "insurance_provider", "type": "string"},
            ],
            "rows": [
                [1, "Eleni Vasquez", "Female", "30-44", "GP Referral", "BlueCross"],
                [2, "Marcus Lindqvist", "Male", "45-59", "Self-Referral", "Self-Pay"],
                [3, "Aisha Karim", "Female", "18-29", "Sports Club", "Aetna"],
                [4, "Tomasz Nowak", "Male", "60+", "GP Referral", "Medicare"],
                [5, "Priya Chandran", "Female", "45-59", "Physician", "UnitedHealth"],
                [6, "Daniel O'Brien", "Male", "30-44", "Self-Referral", "BlueCross"],
                [7, "Sofia Rossi", "Female", "18-29", "Sports Club", "Self-Pay"],
            ],
        },
        {
            "name": "Therapists",
            "description": "Physiotherapists and their specialties.",
            "columns": [
                {"name": "therapist_id", "type": "int64", "key": True},
                {"name": "therapist_name", "type": "string"},
                {"name": "specialty", "type": "string"},
                {"name": "seniority", "type": "string"},
                {"name": "hourly_rate", "type": "double", "format": "$ #,0.00"},
            ],
            "rows": [
                [1, "Dr. Hannah Wells", "Sports Injury", "Senior", 120.00],
                [2, "Dr. Rafael Mendez", "Orthopedic", "Senior", 115.00],
                [3, "Grace Yamamoto", "Neurological", "Mid", 95.00],
                [4, "Owen Fitzgerald", "Musculoskeletal", "Junior", 80.00],
            ],
        },
        {
            "name": "TreatmentTypes",
            "description": "Catalog of treatment / service types offered.",
            "columns": [
                {"name": "treatment_type_id", "type": "int64", "key": True},
                {"name": "treatment_name", "type": "string"},
                {"name": "category", "type": "string"},
                {"name": "standard_duration_min", "type": "int64"},
                {"name": "list_price", "type": "double", "format": "$ #,0.00"},
            ],
            "rows": [
                [1, "Initial Assessment", "Assessment", 60, 110.00],
                [2, "Manual Therapy", "Hands-On", 45, 85.00],
                [3, "Exercise Rehab", "Rehabilitation", 45, 75.00],
                [4, "Dry Needling", "Hands-On", 30, 65.00],
                [5, "Sports Massage", "Recovery", 60, 90.00],
                [6, "Follow-up Review", "Assessment", 30, 55.00],
            ],
        },
        {
            "name": "Clinics",
            "description": "Physical clinic locations.",
            "columns": [
                {"name": "clinic_id", "type": "int64", "key": True},
                {"name": "clinic_name", "type": "string"},
                {"name": "city", "type": "string"},
                {"name": "region", "type": "string"},
                {"name": "treatment_rooms", "type": "int64"},
            ],
            "rows": [
                [1, "Riverside Physio", "Portland", "West", 6],
                [2, "Summit Rehab Center", "Denver", "Mountain", 8],
                [3, "Harbor Wellness", "Boston", "Northeast", 5],
            ],
        },
        {
            "name": "Diagnoses",
            "description": "Clinical diagnosis / presenting condition for a visit.",
            "columns": [
                {"name": "diagnosis_id", "type": "int64", "key": True},
                {"name": "diagnosis_name", "type": "string"},
                {"name": "body_region", "type": "string"},
                {"name": "condition_type", "type": "string"},
            ],
            "rows": [
                [1, "Lower Back Pain", "Spine", "Chronic"],
                [2, "ACL Tear", "Knee", "Acute"],
                [3, "Rotator Cuff Strain", "Shoulder", "Acute"],
                [4, "Sciatica", "Spine", "Chronic"],
                [5, "Tennis Elbow", "Elbow", "Chronic"],
                [6, "Ankle Sprain", "Ankle", "Acute"],
                [7, "Post-Op Hip Replacement", "Hip", "Post-Surgical"],
            ],
        },
        {
            "name": "Visits",
            "description": "One row per clinical visit / treatment session. Core fact.",
            "hidden": True,
            "columns": [
                {"name": "visit_id", "type": "int64", "hidden": True},
                {"name": "appointment_date", "type": "datetime", "hidden": True,
                 "format": "General Date"},
                {"name": "booking_date", "type": "datetime", "hidden": True,
                 "format": "General Date"},
                {"name": "patient_id", "type": "int64", "hidden": True},
                {"name": "therapist_id", "type": "int64", "hidden": True},
                {"name": "treatment_type_id", "type": "int64", "hidden": True},
                {"name": "clinic_id", "type": "int64", "hidden": True},
                {"name": "diagnosis_id", "type": "int64", "hidden": True},
                {"name": "attendance_status", "type": "string", "hidden": True},
                {"name": "duration_minutes", "type": "int64", "hidden": True,
                 "summarizeBy": "sum"},
                {"name": "fee_charged", "type": "double", "hidden": True,
                 "summarizeBy": "sum", "format": "$ #,0.00"},
            ],
            "rows": [
                [5001, dt.date(2024, 1, 8),  dt.date(2024, 1, 3),  1, 1, 1, 1, 1, "Attended", 60, 110.00],
                [5002, dt.date(2024, 1, 22), dt.date(2024, 1, 15), 1, 1, 2, 1, 1, "Attended", 45, 85.00],
                [5003, dt.date(2024, 2, 14), dt.date(2024, 2, 10), 2, 2, 1, 2, 2, "Attended", 60, 110.00],
                [5004, dt.date(2024, 3, 5),  dt.date(2024, 2, 28), 3, 1, 5, 1, 5, "No-Show", 60, 90.00],
                [5005, dt.date(2024, 4, 19), dt.date(2024, 4, 12), 4, 3, 1, 3, 4, "Attended", 60, 110.00],
                [5006, dt.date(2024, 5, 2),  dt.date(2024, 4, 25), 4, 3, 3, 3, 4, "Attended", 45, 75.00],
                [5007, dt.date(2024, 6, 17), dt.date(2024, 6, 10), 5, 2, 2, 2, 3, "Attended", 45, 85.00],
                [5008, dt.date(2024, 7, 30), dt.date(2024, 7, 24), 6, 4, 4, 2, 6, "No-Show", 30, 65.00],
                [5009, dt.date(2024, 9, 11), dt.date(2024, 9, 4),  3, 1, 5, 1, 5, "Attended", 60, 90.00],
                [5010, dt.date(2024, 10, 8), dt.date(2024, 10, 1), 7, 4, 3, 3, 7, "Attended", 45, 75.00],
                [5011, dt.date(2024, 11, 20),dt.date(2024, 11, 13),2, 2, 6, 2, 2, "Cancelled", 30, 55.00],
                [5012, dt.date(2025, 1, 14), dt.date(2025, 1, 6),  5, 2, 2, 2, 3, "Attended", 45, 85.00],
                [5013, dt.date(2025, 2, 26), dt.date(2025, 2, 18), 1, 1, 6, 1, 1, "Attended", 30, 55.00],
                [5014, dt.date(2025, 3, 12), dt.date(2025, 3, 5),  6, 4, 4, 2, 6, "No-Show", 30, 65.00],
                [5015, dt.date(2025, 4, 23), dt.date(2025, 4, 16), 3, 3, 3, 3, 7, "Attended", 45, 75.00],
                [5016, dt.date(2025, 6, 4),  dt.date(2025, 5, 28), 7, 1, 5, 1, 5, "Attended", 60, 90.00],
                [5017, dt.date(2025, 7, 9),  dt.date(2025, 7, 1),  4, 3, 6, 3, 4, "Attended", 30, 55.00],
                [5018, dt.date(2025, 8, 21), dt.date(2025, 8, 14), 2, 2, 2, 2, 3, "Attended", 45, 85.00],
            ],
        },
    ],
    "calendar": {"name": "__Calendar", "start_year": 2024, "end_year": 2025},
    "measures_table": {
        "name": "Clinic Measures",
        "description": "Measure home table: all user-facing measures live here.",
        "measures": [
            {"name": "Total Revenue", "expression": "SUM(Visits[fee_charged])",
             "format": "$ #,0.00", "description": "Total fees charged across visits."},
            {"name": "Visits #", "expression": "DISTINCTCOUNT(Visits[visit_id])",
             "format": "#,0", "description": "Number of clinical visits."},
            {"name": "Patients Seen",
             "expression": "DISTINCTCOUNT(Visits[patient_id])", "format": "#,0"},
            {"name": "Avg Fee per Visit",
             "expression": "DIVIDE([Total Revenue], [Visits #])", "format": "$ #,0.00"},
            {"name": "Total Treatment Hours",
             "expression": "DIVIDE(SUM(Visits[duration_minutes]), 60)",
             "format": "#,0.0"},
            {"name": "Avg Visits per Patient",
             "expression": "DIVIDE([Visits #], [Patients Seen])", "format": "#,0.0"},
            {"name": "No-Shows #",
             "expression": "CALCULATE([Visits #], Visits[attendance_status] = \"No-Show\")",
             "format": "#,0", "description": "Count of visits marked as no-show."},
            {"name": "No-Show Rate",
             "expression": "DIVIDE([No-Shows #], [Visits #])", "format": "0.0%",
             "description": "Share of booked visits where the patient did not attend."},
            {"name": "Diagnoses per Therapist",
             "expression": "DIVIDE(DISTINCTCOUNT(Visits[diagnosis_id]), DISTINCTCOUNT(Visits[therapist_id]))",
             "format": "#,0.0",
             "description": "Average distinct diagnoses handled per therapist in context; "
                            "relates the Diagnoses dimension to Therapists (by specialty)."},
        ],
    },
    "relationships": [
        {"from": "Visits.patient_id", "to": "Patients.patient_id"},
        {"from": "Visits.therapist_id", "to": "Therapists.therapist_id"},
        {"from": "Visits.treatment_type_id", "to": "TreatmentTypes.treatment_type_id"},
        {"from": "Visits.clinic_id", "to": "Clinics.clinic_id"},
        {"from": "Visits.diagnosis_id", "to": "Diagnoses.diagnosis_id"},
        {"from": "Visits.appointment_date", "to": "__Calendar.Date"},
        {"from": "Visits.booking_date", "to": "__Calendar.Date", "active": False},
    ],
}


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "out" / "PhysioClinic"
    pbip = build_pbip(SPEC, out)
    print(f"Built PBIP: {pbip}")


if __name__ == "__main__":
    main()
