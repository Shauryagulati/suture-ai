"""Seed development data.

Idempotent: deletes seed rows by slug/email before re-inserting.

Inventory:
- 2 clinics (Pittsburgh metro — Western PA cardiology)
- 6 users (3 per clinic: admin / reviewer / readonly)
- 6 clinic_memberships (one default per user)
- 20 patients (10 per clinic, age 45-80, varied insurance)
- 10 providers (5 per clinic, mix of PCP / hospitalist / ED / IM / family)

Run with: make seed
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from faker import Faker
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import (
    Appointment,
    AppointmentStatus,
    Base,
    Call,
    CallStatus,
    CallType,
    Clinic,
    ClinicMembership,
    MembershipRole,
    Patient,
    Provider,
    ProviderType,
    User,
)
from app.utils.context import current_clinic_id
from app.utils.security import hash_password
from seeds.scripts._npi import generate_npi

# ─── Fixture data ──────────────────────────────────────────────────────

CLINICS = [
    ("steel-city-cardiology", "Steel City Cardiology Associates"),
    ("allegheny-valley-heart", "Allegheny Valley Heart & Vascular"),
]

# Email scheme: {role}@{slug}.example.com (`.example.com` is RFC-2606
# reserved-for-docs; .local is rejected by email-validator).
USERS_PER_CLINIC = [
    ("admin", MembershipRole.admin),
    ("reviewer", MembershipRole.reviewer),
    ("readonly", MembershipRole.readonly),
]

DEV_PASSWORD = "suture_dev_123"

PAYERS = ["Highmark", "UPMC Health Plan", "Aetna", "UHC", "Cigna", "Medicare"]

PROVIDER_KIND = [
    ("PCP", ProviderType.referring, "Internal Medicine"),
    ("Hospitalist", ProviderType.referring, "Hospital Medicine"),
    ("ED", ProviderType.referring, "Emergency Medicine"),
    ("Internal Medicine", ProviderType.referring, "Internal Medicine"),
    ("Family Practice", ProviderType.referring, "Family Medicine"),
]

# Clinic-scoped tables in children-first FK order for idempotent re-seeding.
# Mirrors the test-harness cleanup order. payer_rules / workflow_runs are
# omitted on purpose (RAG KB + task bookkeeping aren't part of a dev-data run).
_CLINIC_SCOPED_DELETE_ORDER = [
    "audit_logs",
    "eval_runs",
    "ai_invocations",
    "prior_auth_events",
    "prior_auths",
    "call_transcripts",
    "calls",
    "document_extractions",
    "referral_tasks",
    "referrals",
    "faxes",
    "discharge_summaries",
    "appointments",
    "outreach_attempts",
    "eligibility_checks",
    "insurance_policies",
    "documents",
    "patients",
    "providers",
]


# ─── Main ──────────────────────────────────────────────────────────────


async def seed() -> None:
    fake = Faker()
    Faker.seed(42)
    rng = random.Random(42)

    async with async_session_maker() as db:
        # ── Idempotency: delete prior seed rows ──
        await _clear_seed(db)

        clinic_ids: dict[str, str] = {}
        for slug, name in CLINICS:
            cid = uuid4()
            clinic_ids[slug] = str(cid)
            db.add(Clinic(id=cid, name=name, slug=slug))
        await db.commit()

        # Re-fetch as objects to get UUIDs back as UUIDs.
        clinics = (await db.execute(select(Clinic))).scalars().all()
        by_slug = {c.slug: c for c in clinics}

        # ── Users + memberships ──
        users_created = 0
        memberships_created = 0
        for clinic in clinics:
            for role_prefix, role_enum in USERS_PER_CLINIC:
                user = User(
                    id=uuid4(),
                    email=f"{role_prefix}@{clinic.slug}.example.com",
                    hashed_password=hash_password(DEV_PASSWORD),
                    full_name=f"{role_prefix.title()} {clinic.name}",
                )
                db.add(user)
                await db.flush()
                db.add(
                    ClinicMembership(
                        user_id=user.id,
                        clinic_id=clinic.id,
                        role=role_enum,
                        is_default=True,
                    )
                )
                users_created += 1
                memberships_created += 1
        await db.commit()

        # ── Patients (must set tenant context for the guard) ──
        patients_created = 0
        for clinic in clinics:
            token = current_clinic_id.set(clinic.id)
            try:
                for _ in range(10):
                    age = rng.randint(45, 80)
                    dob = fake.date_of_birth(minimum_age=age, maximum_age=age)
                    db.add(
                        Patient(
                            clinic_id=clinic.id,
                            first_name=fake.first_name(),
                            last_name=fake.last_name(),
                            dob=dob.isoformat(),
                            phone=fake.phone_number()[:32],
                            email=fake.safe_email(),
                            address_line1=fake.street_address(),
                            city=rng.choice(
                                [
                                    "Pittsburgh",
                                    "Monroeville",
                                    "Cranberry",
                                    "Greensburg",
                                    "Washington",
                                    "Butler",
                                    "Beaver",
                                ]
                            ),
                            state="PA",
                            zip_code=fake.postcode_in_state("PA"),
                            mrn=f"MRN-{fake.unique.bothify(text='######').upper()}",
                            notes=f"Primary payer: {rng.choice(PAYERS)}",
                        )
                    )
                    patients_created += 1
                await db.commit()
            finally:
                current_clinic_id.reset(token)

        # ── Providers ──
        providers_created = 0
        for clinic in clinics:
            token = current_clinic_id.set(clinic.id)
            try:
                for kind_name, kind_type, specialty in PROVIDER_KIND:
                    db.add(
                        Provider(
                            clinic_id=clinic.id,
                            first_name=fake.first_name(),
                            last_name=fake.last_name(),
                            npi=generate_npi(rng),
                            practice_name=f"{kind_name} of {clinic.name}",
                            practice_phone=fake.phone_number()[:32],
                            practice_fax=fake.phone_number()[:32],
                            practice_address=fake.street_address(),
                            provider_type=kind_type,
                            specialty=specialty,
                        )
                    )
                    providers_created += 1
                await db.commit()
            finally:
                current_clinic_id.reset(token)

        # ── Appointments / calls / eval runs (so demo pages aren't empty) ──
        appointments_created = 0
        calls_created = 0
        now = datetime.now(UTC)
        for clinic in clinics:
            token = current_clinic_id.set(clinic.id)
            try:
                clinic_patients = (
                    (await db.execute(select(Patient).where(Patient.clinic_id == clinic.id)))
                    .scalars()
                    .all()
                )
                clinic_providers = (
                    (await db.execute(select(Provider).where(Provider.clinic_id == clinic.id)))
                    .scalars()
                    .all()
                )
                if clinic_patients and clinic_providers:
                    appt_plan = [
                        (3, AppointmentStatus.scheduled),
                        (10, AppointmentStatus.confirmed),
                        (-7, AppointmentStatus.completed),
                    ]
                    for i, (day_offset, status) in enumerate(appt_plan):
                        db.add(
                            Appointment(
                                patient_id=clinic_patients[i % len(clinic_patients)].id,
                                provider_id=clinic_providers[i % len(clinic_providers)].id,
                                appointment_at=now + timedelta(days=day_offset, hours=9 + i),
                                appointment_type="follow_up",
                                status=status,
                            )
                        )
                        appointments_created += 1
                    for i in range(2):
                        started = now - timedelta(days=2, hours=i)
                        db.add(
                            Call(
                                patient_id=clinic_patients[i % len(clinic_patients)].id,
                                call_type=CallType.outbound_followup,
                                status=CallStatus.completed,
                                started_at=started,
                                ended_at=started + timedelta(minutes=4),
                                duration_seconds=240,
                                outcome={
                                    "resolved": True,
                                    "summary": "Confirmed follow-up appointment.",
                                },
                            )
                        )
                        calls_created += 1
                # NOTE: eval_runs are NOT seeded here. They must come from the
                # real harness (`make eval-extraction`), which writes metrics in
                # the `aggregate` shape the evals API reads. Hand-seeded rows
                # showed 0% because their metrics were the wrong shape.
                await db.commit()
            finally:
                current_clinic_id.reset(token)

        # ── Summary ──
        print()
        print("┌────────────────────────────────────────────────────┐")
        print("│ Suture dev seed complete                           │")
        print("├────────────────────────────────────────────────────┤")
        print(f"│ Clinics:     {len(by_slug):>3}                                  │")
        print(f"│ Users:       {users_created:>3}                                  │")
        print(f"│ Memberships: {memberships_created:>3}                                  │")
        print(f"│ Patients:    {patients_created:>3}                                  │")
        print(f"│ Providers:   {providers_created:>3}                                  │")
        print("├────────────────────────────────────────────────────┤")
        print("│ Login: admin@<slug>.example.com / suture_dev_123   │")
        print(f"│   slugs: {', '.join(by_slug)}    │")
        print("└────────────────────────────────────────────────────┘")
        print(f"  + appointments: {appointments_created}, calls: {calls_created}")
        print("  (eval_runs come from `make eval-extraction`, not the seed)")


async def _clear_seed(db: AsyncSession) -> None:
    """Remove prior seed rows so the script is idempotent.

    Uses Core `Table.delete()` (not ORM `delete(Model)`) for the
    clinic-scoped tables so the tenant guard's `do_orm_execute`
    listener doesn't fire — admin cleanup spans clinics intentionally.
    """
    seed_slugs = [s for s, _ in CLINICS]
    seed_emails = [
        f"{role}@{slug}.example.com" for slug in seed_slugs for role, _ in USERS_PER_CLINIC
    ]

    seed_clinics = (
        (await db.execute(select(Clinic).where(Clinic.slug.in_(seed_slugs)))).scalars().all()
    )
    seed_clinic_ids = [c.id for c in seed_clinics]
    if seed_clinic_ids:
        # Core deletes via __table__ bypass the do_orm_execute tenant listener
        # (admin cleanup spans clinics intentionally). Delete clinic-scoped rows
        # children-first so RESTRICT FKs don't block — this must stay robust even
        # after `make seed-documents` has populated referrals/tasks/outreach, so a
        # re-run of `make seed` doesn't crash on a referrals→patients FK.
        # payer_rules is intentionally left alone: the RAG KB is seeded separately
        # and isn't tied to a dev-data run.
        for table_name in _CLINIC_SCOPED_DELETE_ORDER:
            table = Base.metadata.tables[table_name]
            await db.execute(table.delete().where(table.c.clinic_id.in_(seed_clinic_ids)))
    # Users + clinics are GlobalBase tables — direct deletes are fine.
    await db.execute(delete(User).where(User.email.in_(seed_emails)))
    await db.execute(delete(Clinic).where(Clinic.slug.in_(seed_slugs)))
    await db.commit()


if __name__ == "__main__":
    asyncio.run(seed())
