"""Cardiology referral + discharge scenario constants.

Drives:
- Which ICD-10 / CPT codes appear on each kind of document.
- The fixed corpus distribution (10 stress / 8 echo / 7 cath / 5 EP; 8 MI / 5
  CHF / 4 cath / 3 ablation).
- Plausible urgency tier distributions per scenario.
- Follow-up window heuristics.

NOT a clinical authority — these are realistic-enough patterns for synthetic
test data. The eval harness ASSERTS the model extracts the same codes, so the
canonical mapping lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Urgency = str  # "stat" | "urgent" | "routine"
UrgencyTier = str  # "critical" | "high" | "medium" | "routine"


@dataclass(frozen=True)
class ReferralScenario:
    """Specification for one type of cardiology referral."""

    key: str
    label: str  # human-readable, e.g. "Stress Test"
    cpt_code: str
    # Each inner list is one plausible diagnosis-code combination for this referral.
    icd10_combinations: list[list[str]]
    # Distribution of urgency levels: weights sum implicit, sampled by index.
    urgency_choices: list[tuple[Urgency, float]]
    # Acceptable follow-up window (inclusive, days).
    follow_up_window_days_range: tuple[int, int]
    # Common chief-complaint phrasings to prompt the LLM with (one is sampled).
    chief_complaints: list[str]


@dataclass(frozen=True)
class DischargeScenario:
    """Specification for one type of discharge summary."""

    key: str
    label: str
    primary_diagnosis_options: list[str]  # human-readable diagnoses
    icd10_combinations: list[list[str]]
    typical_procedures: list[list[tuple[str, str | None]]]  # (description, cpt or None)
    urgency_tier_choices: list[tuple[UrgencyTier, float]]
    urgent_flag_options: list[str]
    follow_up_window_days_range: tuple[int, int]
    medication_change_pool: list[tuple[str, str]]  # (name, action)


# ─── Referral corpus ───────────────────────────────────────────────────────

REFERRAL_SCENARIOS: dict[str, ReferralScenario] = {
    "stress_test": ReferralScenario(
        key="stress_test",
        label="Stress Test",
        cpt_code="93015",
        icd10_combinations=[
            ["R07.9"],  # chest pain, unspecified
            ["R07.9", "I10"],  # chest pain + essential HTN
            ["R07.89", "Z82.49"],  # other chest pain + family hx cardiac dz
            ["I25.10"],  # ASHD without angina
            ["R00.0", "R07.9"],  # tachycardia + chest pain
        ],
        urgency_choices=[("routine", 0.7), ("urgent", 0.25), ("stat", 0.05)],
        follow_up_window_days_range=(14, 30),
        chief_complaints=[
            "exertional chest pressure",
            "atypical chest pain with exertion",
            "shortness of breath on exertion, ruling out cardiac etiology",
            "palpitations with mild exertional symptoms",
            "pre-operative cardiac clearance prior to elective surgery",
        ],
    ),
    "echo": ReferralScenario(
        key="echo",
        label="Echocardiogram (TTE)",
        cpt_code="93306",
        icd10_combinations=[
            ["I50.9"],  # heart failure, unspecified
            ["I50.22"],  # chronic systolic CHF
            ["I35.0"],  # nonrheumatic aortic stenosis
            ["I05.0", "I50.9"],  # mitral stenosis + HF
            ["R01.1"],  # heart murmur
            ["I42.9"],  # cardiomyopathy, unspecified
        ],
        urgency_choices=[("routine", 0.75), ("urgent", 0.2), ("stat", 0.05)],
        follow_up_window_days_range=(7, 21),
        chief_complaints=[
            "newly noted systolic murmur on auscultation",
            "lower extremity edema with suspected diastolic dysfunction",
            "follow-up evaluation of known mild aortic stenosis",
            "worsening dyspnea, evaluate LV function",
            "dyspnea on exertion, NYHA II symptoms",
        ],
    ),
    "cath": ReferralScenario(
        key="cath",
        label="Left Heart Catheterization",
        cpt_code="93458",
        icd10_combinations=[
            ["I25.10", "I20.9"],  # CAD + angina
            ["I20.0"],  # unstable angina
            ["I25.110", "I20.9"],  # native CAD + angina
            ["R94.39", "I20.9"],  # abnormal CV function study + angina
            ["I25.10", "Z95.5"],  # CAD + hx stent
        ],
        urgency_choices=[("urgent", 0.5), ("routine", 0.3), ("stat", 0.2)],
        follow_up_window_days_range=(3, 14),
        chief_complaints=[
            "positive stress test with reversible ischemia, anterior wall",
            "unstable angina with rising troponin trend",
            "progressive angina symptoms despite optimal medical therapy",
            "post-MI risk stratification, evaluate native and graft anatomy",
            "abnormal noninvasive testing in patient with established CAD",
        ],
    ),
    "ep_study": ReferralScenario(
        key="ep_study",
        label="Electrophysiology Study",
        cpt_code="93620",
        icd10_combinations=[
            ["I48.0"],  # paroxysmal a-fib
            ["I47.2"],  # sustained ventricular tachycardia
            ["I49.5"],  # sick-sinus syndrome
            ["I48.91", "R55"],  # unspecified a-fib + syncope
            ["I47.1", "R00.0"],  # supraventricular tachycardia + tachycardia
        ],
        urgency_choices=[("urgent", 0.55), ("routine", 0.3), ("stat", 0.15)],
        follow_up_window_days_range=(7, 21),
        chief_complaints=[
            "recurrent symptomatic paroxysmal atrial fibrillation despite rate control",
            "unexplained syncope with non-sustained VT on Holter",
            "wide-complex tachycardia documented on telemetry",
            "sick sinus syndrome with symptomatic pauses, consider pacemaker workup",
            "supraventricular tachycardia refractory to medical management, ablation candidate",
        ],
    ),
}

REFERRAL_COUNTS: dict[str, int] = {
    "stress_test": 10,
    "echo": 8,
    "cath": 7,
    "ep_study": 5,
}

# Sanity check at import — wrong totals here would silently produce the wrong
# corpus, which is exactly the kind of bug TDD won't catch later.
assert sum(REFERRAL_COUNTS.values()) == 30, "referral counts must sum to 30"


# ─── Discharge corpus ──────────────────────────────────────────────────────

DISCHARGE_SCENARIOS: dict[str, DischargeScenario] = {
    "post_mi": DischargeScenario(
        key="post_mi",
        label="Post-MI",
        primary_diagnosis_options=[
            "Acute STEMI, anterior wall",
            "NSTEMI, mid-LAD distribution",
            "Acute inferior STEMI",
            "Type II NSTEMI, demand-related",
        ],
        icd10_combinations=[
            ["I21.09", "I25.10"],  # acute STEMI anterior + ASHD
            ["I21.4", "I25.10"],  # NSTEMI + ASHD
            ["I21.19", "I25.10"],  # acute STEMI inferior + ASHD
            ["I21.A1", "I25.10"],  # type II MI + ASHD
        ],
        typical_procedures=[
            [("Coronary angiography", "93458"), ("PCI to LAD with DES", "92928")],
            [("Coronary angiography", "93458"), ("PCI to RCA with DES", "92928")],
            [("Coronary angiography", "93458")],  # diagnostic only
            [("CABG x3", None)],  # transferred out for surgical
        ],
        urgency_tier_choices=[("high", 0.55), ("critical", 0.3), ("medium", 0.15)],
        urgent_flag_options=[
            "post-acute-MI",
            "recent-revascularization",
            "post-PCI dual antiplatelet therapy",
            "EF<40%",
        ],
        follow_up_window_days_range=(5, 10),
        medication_change_pool=[
            ("Atorvastatin 80 mg daily", "started"),
            ("Aspirin 81 mg daily", "started"),
            ("Clopidogrel 75 mg daily", "started"),
            ("Metoprolol succinate 50 mg daily", "started"),
            ("Lisinopril 10 mg daily", "started"),
            ("Ticagrelor 90 mg BID", "started"),
        ],
    ),
    "post_chf": DischargeScenario(
        key="post_chf",
        label="Post-CHF exacerbation",
        primary_diagnosis_options=[
            "Acute on chronic systolic heart failure",
            "Acute on chronic diastolic heart failure",
            "HFrEF with acute decompensation",
            "Right-sided heart failure with volume overload",
        ],
        icd10_combinations=[
            ["I50.21", "I25.10"],
            ["I50.31", "I10"],
            ["I50.22"],
            ["I50.811"],
        ],
        typical_procedures=[
            [("IV diuresis with furosemide", None)],
            [("Right heart catheterization", "93451")],
            [("Echocardiogram (TTE)", "93306"), ("IV diuresis", None)],
        ],
        urgency_tier_choices=[("high", 0.4), ("medium", 0.5), ("critical", 0.1)],
        urgent_flag_options=[
            "30-day-readmission-risk",
            "EF<40%",
            "BNP elevated at discharge",
            "active volume overload at discharge",
        ],
        follow_up_window_days_range=(7, 14),
        medication_change_pool=[
            ("Furosemide 40 mg BID", "started"),
            ("Sacubitril/valsartan 49/51 mg BID", "started"),
            ("Spironolactone 25 mg daily", "started"),
            ("Carvedilol 6.25 mg BID", "adjusted"),
            ("Empagliflozin 10 mg daily", "started"),
            ("Metoprolol tartrate", "stopped"),
        ],
    ),
    "post_cath": DischargeScenario(
        key="post_cath",
        label="Post-cath",
        primary_diagnosis_options=[
            "Coronary artery disease s/p elective LHC",
            "Stable angina s/p PCI to mid-LAD",
            "CAD s/p diagnostic catheterization, no intervention",
            "Mild CAD on diagnostic angiography",
        ],
        icd10_combinations=[
            ["I25.10", "Z98.61"],  # CAD + post-procedural
            ["I20.9", "Z95.5"],  # angina + hx stent
            ["I25.110"],
            ["I25.10"],
        ],
        typical_procedures=[
            [("Coronary angiography", "93458"), ("PCI to LAD with DES", "92928")],
            [("Coronary angiography", "93458")],
            [("Coronary angiography with FFR", "93458")],
        ],
        urgency_tier_choices=[("routine", 0.55), ("medium", 0.4), ("high", 0.05)],
        urgent_flag_options=[
            "post-PCI dual antiplatelet therapy",
            "femoral access — bleed precautions",
            "radial access — wrist precautions",
        ],
        follow_up_window_days_range=(7, 21),
        medication_change_pool=[
            ("Clopidogrel 75 mg daily", "started"),
            ("Aspirin 81 mg daily", "started"),
            ("Atorvastatin 40 mg daily", "adjusted"),
            ("Isosorbide mononitrate 30 mg daily", "started"),
        ],
    ),
    "post_ablation": DischargeScenario(
        key="post_ablation",
        label="Post-ablation",
        primary_diagnosis_options=[
            "Paroxysmal atrial fibrillation s/p PVI ablation",
            "Persistent atrial fibrillation s/p RF ablation",
            "AVNRT s/p slow-pathway ablation",
            "Atrial flutter s/p cavotricuspid isthmus ablation",
        ],
        icd10_combinations=[
            ["I48.0", "Z95.0"],  # paroxysmal a-fib + hx cardiac device
            ["I48.1"],  # persistent a-fib
            ["I47.1"],  # SVT
            ["I48.3"],  # typical atrial flutter
        ],
        typical_procedures=[
            [("Pulmonary vein isolation", "93656")],
            [("RF ablation of atrial fibrillation", "93656")],
            [("Slow-pathway ablation for AVNRT", "93653")],
            [("Cavotricuspid isthmus ablation", "93653")],
        ],
        urgency_tier_choices=[("medium", 0.65), ("routine", 0.3), ("high", 0.05)],
        urgent_flag_options=[
            "post-ablation anticoagulation required",
            "groin access precautions",
            "blanking period — symptoms expected",
        ],
        follow_up_window_days_range=(14, 30),
        medication_change_pool=[
            ("Apixaban 5 mg BID", "started"),
            ("Rivaroxaban 20 mg daily", "started"),
            ("Flecainide 100 mg BID", "started"),
            ("Metoprolol tartrate 25 mg BID", "adjusted"),
            ("Amiodarone", "stopped"),
        ],
    ),
}

DISCHARGE_COUNTS: dict[str, int] = {
    "post_mi": 8,
    "post_chf": 5,
    "post_cath": 4,
    "post_ablation": 3,
}

assert sum(DISCHARGE_COUNTS.values()) == 20, "discharge counts must sum to 20"


# ─── Hospital pool (real Western-PA institutions for "discharging from" field) ──

WESTERN_PA_HOSPITALS: list[str] = [
    "UPMC Presbyterian",
    "UPMC Shadyside",
    "UPMC Mercy",
    "UPMC Passavant",
    "AHN Allegheny General Hospital",
    "AHN West Penn Hospital",
    "AHN Forbes Hospital",
    "St. Clair Hospital",
    "Excela Health Westmoreland Hospital",
    "Heritage Valley Beaver",
]


# ─── Payer pool used by patient generator ─────────────────────────────────

PAYERS_PRIMARY: list[str] = [
    "Highmark BCBS PA",
    "UPMC Health Plan",
    "Aetna",
    "UnitedHealthcare",
    "Cigna",
    "Medicare",
]
