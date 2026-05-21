"""Referral source quality — per-provider completeness scorecard."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.analytics.referral_quality import (
    REFERRAL_FIELD_COUNT,
    compute_referral_quality,
)
from tests.analytics_helpers import (
    make_document,
    make_extraction,
    make_patient,
    make_provider,
    make_referral,
)

pytestmark = pytest.mark.asyncio


async def test_clean_provider_scores_higher_than_messy_provider(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        patient = make_patient(clinic_id=clinic_a)
        clean = make_provider(clinic_id=clinic_a, first="Clean", last="Doc")
        messy = make_provider(clinic_id=clinic_a, first="Messy", last="Doc")
        db_session.add_all([patient, clean, messy])
        await db_session.flush()
        for prov, missing in [
            (clean, []),
            (clean, []),
            (messy, ["dob", "phone", "insurance_member_id", "diagnosis_codes"]),
            (messy, ["dob", "phone", "insurance_member_id"]),
        ]:
            doc = make_document(clinic_id=clinic_a, patient_id=patient.id)
            db_session.add(doc)
            await db_session.flush()
            db_session.add(
                make_extraction(
                    clinic_id=clinic_a, document_id=doc.id, missing_fields=missing
                )
            )
            db_session.add(
                make_referral(
                    clinic_id=clinic_a,
                    patient_id=patient.id,
                    referring_provider_id=prov.id,
                    document_id=doc.id,
                )
            )
            await db_session.flush()
        await db_session.commit()
        summary = await compute_referral_quality(db_session)

    by_id = {r.provider_id: r for r in summary.rows}
    assert by_id[clean.id].completeness_pct > by_id[messy.id].completeness_pct
    assert by_id[clean.id].avg_missing_fields == 0.0
    assert by_id[messy.id].avg_missing_fields == pytest.approx(3.5)
    assert by_id[clean.id].referral_volume == 2
    assert by_id[messy.id].referral_volume == 2


async def test_top_missing_fields_per_provider(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        patient = make_patient(clinic_id=clinic_a)
        prov = make_provider(clinic_id=clinic_a)
        db_session.add_all([patient, prov])
        await db_session.flush()
        for missing in [["dob", "phone"], ["dob", "insurance_member_id"], ["dob"]]:
            doc = make_document(clinic_id=clinic_a, patient_id=patient.id)
            db_session.add(doc)
            await db_session.flush()
            db_session.add(
                make_extraction(
                    clinic_id=clinic_a, document_id=doc.id, missing_fields=missing
                )
            )
            db_session.add(
                make_referral(
                    clinic_id=clinic_a,
                    patient_id=patient.id,
                    referring_provider_id=prov.id,
                    document_id=doc.id,
                )
            )
        await db_session.commit()
        summary = await compute_referral_quality(db_session)

    row = next(r for r in summary.rows if r.provider_id == prov.id)
    assert row.top_missing_fields[0] == "dob"


async def test_completeness_pct_is_one_when_no_missing(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    clinic_a, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a, user_id=test_user):
        patient = make_patient(clinic_id=clinic_a)
        prov = make_provider(clinic_id=clinic_a)
        db_session.add_all([patient, prov])
        await db_session.flush()
        doc = make_document(clinic_id=clinic_a, patient_id=patient.id)
        db_session.add(doc)
        await db_session.flush()
        db_session.add(
            make_extraction(clinic_id=clinic_a, document_id=doc.id, missing_fields=[])
        )
        db_session.add(
            make_referral(
                clinic_id=clinic_a,
                patient_id=patient.id,
                referring_provider_id=prov.id,
                document_id=doc.id,
            )
        )
        await db_session.commit()
        summary = await compute_referral_quality(db_session)
    assert summary.rows[0].completeness_pct == 1.0
    assert REFERRAL_FIELD_COUNT > 0
