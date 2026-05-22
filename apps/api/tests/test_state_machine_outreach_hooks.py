"""State-machine hook tests — auto-schedule outreach on entry to
ready_to_schedule (referrals) and patient_contacted (discharges)."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discharge_summary import DischargeStatus, DischargeSummary
from app.models.outreach_attempt import OutreachAttempt, OutreachChannel
from app.models.referral import Referral, ReferralStatus
from app.models.referral_task import ReferralTask
from app.services.workflow.state_machine import (
    apply_discharge_transition,
    apply_referral_transition,
)

pytestmark = pytest.mark.asyncio


async def test_referral_transition_to_ready_to_schedule_auto_schedules_outreach(
    db_session: AsyncSession,
    seeded_referral_a: Referral,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await apply_referral_transition(
            db_session,
            referral=seeded_referral_a,
            target=ReferralStatus.ready_to_schedule,
        )
        await db_session.commit()

        tasks = (
            (
                await db_session.execute(
                    select(ReferralTask).where(
                        ReferralTask.referral_id == seeded_referral_a.id
                    )
                )
            )
            .scalars()
            .all()
        )
        attempts = (
            (
                await db_session.execute(
                    select(OutreachAttempt).where(
                        OutreachAttempt.referral_id == seeded_referral_a.id
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(tasks) == 4
    assert len(attempts) == 3
    assert {a.channel for a in attempts} == {
        OutreachChannel.sms,
        OutreachChannel.email,
        OutreachChannel.voice,
    }


async def test_discharge_transition_to_patient_contacted_auto_schedules_outreach(
    db_session: AsyncSession,
    seeded_discharge_a: DischargeSummary,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await apply_discharge_transition(
            db_session,
            discharge=seeded_discharge_a,
            target=DischargeStatus.patient_contacted,
        )
        await db_session.commit()

        attempts = (
            (
                await db_session.execute(
                    select(OutreachAttempt).where(
                        OutreachAttempt.discharge_summary_id == seeded_discharge_a.id
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(attempts) == 3
    assert {a.channel for a in attempts} == {
        OutreachChannel.sms,
        OutreachChannel.email,
        OutreachChannel.voice,
    }


async def test_referral_double_transition_does_not_duplicate_outreach(
    db_session: AsyncSession,
    seeded_referral_a: Referral,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
) -> None:
    """Idempotency check — apply_referral_transition can be called twice
    (e.g., from a retried Celery task) without doubling outreach."""
    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        await apply_referral_transition(
            db_session,
            referral=seeded_referral_a,
            target=ReferralStatus.ready_to_schedule,
        )
        await db_session.commit()

        # Manually re-call the inner generator (the public transition would
        # raise InvalidTransitionError on a no-op move). We import the
        # private function to exercise its idempotency directly.
        from app.services.outreach.orchestrator import schedule_outreach_sequence

        await schedule_outreach_sequence(db_session, referral=seeded_referral_a)
        await db_session.commit()

        attempts = (
            (
                await db_session.execute(
                    select(OutreachAttempt).where(
                        OutreachAttempt.referral_id == seeded_referral_a.id
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(attempts) == 3  # still 3, not 6


async def test_discharge_transition_to_confirmation_sent_fires_fax(
    db_session: AsyncSession,
    seeded_discharge_a: DischargeSummary,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
    tmp_path,
    monkeypatch,
) -> None:
    """Walk the discharge through new -> patient_contacted -> scheduled
    -> seen -> confirmation_sent. The terminal transition must (a) set
    confirmation_fax_path + confirmation_fax_sent_at on the discharge,
    and (b) record exactly one send on the stub fax provider."""
    from app.models.fax import Fax, FaxDirection, FaxStatus, FaxType
    from app.services.discharge import confirmation as confirmation_mod
    from app.services.fax import factory as fax_factory
    from app.services.fax import stub as fax_stub_mod
    from app.services.fax.stub import StubFaxProvider

    monkeypatch.setattr(confirmation_mod, "_PERSIST_ROOT", tmp_path / "confirmations")
    monkeypatch.setattr(fax_stub_mod, "_OUTBOX_ROOT", tmp_path / "fax_outbox")
    fax_factory.reset_fax_provider_cache()

    clinic_a_id, _ = two_clinics
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        for target in (
            DischargeStatus.patient_contacted,
            DischargeStatus.scheduled,
            DischargeStatus.seen,
            DischargeStatus.confirmation_sent,
        ):
            await apply_discharge_transition(
                db_session, discharge=seeded_discharge_a, target=target
            )
            await db_session.commit()

        assert seeded_discharge_a.status == DischargeStatus.confirmation_sent
        assert seeded_discharge_a.confirmation_fax_path is not None
        assert seeded_discharge_a.confirmation_fax_sent_at is not None

        fax_rows = (
            (
                await db_session.execute(
                    select(Fax).where(
                        Fax.direction == FaxDirection.outbound,
                        Fax.fax_type == FaxType.confirmation,
                        Fax.patient_id == seeded_discharge_a.patient_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(fax_rows) == 1
        assert fax_rows[0].status == FaxStatus.sent

        provider = fax_factory.get_fax_provider()
        assert isinstance(provider, StubFaxProvider)
        matching = [
            r for r in provider.sent if r.discharge_summary_id == seeded_discharge_a.id
        ]
        assert len(matching) == 1
    fax_factory.reset_fax_provider_cache()
