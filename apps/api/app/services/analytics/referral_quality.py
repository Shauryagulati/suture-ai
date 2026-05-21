"""Per-referring-provider data-quality scorecard.

Joins Referral -> Document -> DocumentExtraction so we can attribute
missing-field counts to the referring provider. Referrals without a
referring_provider_id are excluded (they contribute to no one's score)."""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentExtraction, Provider, Referral
from app.schemas.analytics import ReferralQualityRow, ReferralQualitySummary

REFERRAL_FIELD_COUNT = 12


async def compute_referral_quality(db: AsyncSession) -> ReferralQualitySummary:
    referrals = (
        (
            await db.execute(
                select(Referral).where(Referral.referring_provider_id.is_not(None))
            )
        )
        .scalars()
        .all()
    )
    if not referrals:
        return ReferralQualitySummary(rows=[])

    provider_ids = {r.referring_provider_id for r in referrals if r.referring_provider_id}
    providers = (
        (await db.execute(select(Provider).where(Provider.id.in_(provider_ids))))
        .scalars()
        .all()
    )
    prov_by_id = {p.id: p for p in providers}

    document_ids = {r.document_id for r in referrals if r.document_id}
    extractions_by_doc: dict[UUID, DocumentExtraction] = {}
    if document_ids:
        extractions = (
            (
                await db.execute(
                    select(DocumentExtraction).where(
                        DocumentExtraction.document_id.in_(document_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        for ext in extractions:
            extractions_by_doc[ext.document_id] = ext

    missing_by_provider: dict[UUID, list[list[str]]] = {}
    volume_by_provider: dict[UUID, int] = {}
    for r in referrals:
        assert r.referring_provider_id is not None
        volume_by_provider[r.referring_provider_id] = (
            volume_by_provider.get(r.referring_provider_id, 0) + 1
        )
        if r.document_id and r.document_id in extractions_by_doc:
            missing_by_provider.setdefault(r.referring_provider_id, []).append(
                extractions_by_doc[r.document_id].missing_fields or []
            )

    rows: list[ReferralQualityRow] = []
    for pid, volume in volume_by_provider.items():
        prov = prov_by_id.get(pid)
        if prov is None:
            continue
        missing_lists = missing_by_provider.get(pid, [])
        if missing_lists:
            avg_missing = sum(len(m) for m in missing_lists) / len(missing_lists)
            counter: Counter[str] = Counter()
            for m in missing_lists:
                counter.update(m)
            top_missing = [f for f, _ in counter.most_common(3)]
        else:
            avg_missing = 0.0
            top_missing = []
        completeness = max(0.0, 1.0 - (avg_missing / REFERRAL_FIELD_COUNT))
        rows.append(
            ReferralQualityRow(
                provider_id=prov.id,
                provider_name=f"{prov.first_name} {prov.last_name}".strip(),
                practice_name=prov.practice_name,
                referral_volume=volume,
                avg_missing_fields=round(avg_missing, 2),
                completeness_pct=round(completeness, 4),
                top_missing_fields=top_missing,
            )
        )
    rows.sort(key=lambda r: r.referral_volume, reverse=True)
    return ReferralQualitySummary(rows=rows)
