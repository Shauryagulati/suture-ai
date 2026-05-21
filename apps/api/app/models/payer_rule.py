"""PayerRule — RAG knowledge base over payer prior-auth guidelines.

Uses pgvector for semantic search. 1024-dim for `bge-m3` (see ADR 007).

PayerRule is NOT clinic-scoped — payer rules are global knowledge.
Uses GlobalBase to skip the tenant guard. ADR 002 has the
documented exception.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import ARRAY, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GlobalBase


class PayerRule(GlobalBase):
    __tablename__ = "payer_rules"

    payer_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    procedure_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    procedure_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    required_documents: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    common_denial_reasons: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    typical_turnaround_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    guidelines_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
