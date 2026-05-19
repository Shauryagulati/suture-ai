"""SQLAlchemy ORM models.

Importing this package registers all models with the declarative base
metadata and with the audit listener registry. Always import via
`from app.models import ...` so registration side-effects run.
"""

from __future__ import annotations

from app.models.audit_log import AuditAction, AuditLog
from app.models.base import Base, ClinicScopedBase, GlobalBase
from app.models.clinic import Clinic
from app.models.clinic_membership import ClinicMembership, MembershipRole
from app.models.patient import Patient
from app.models.provider import Provider, ProviderType
from app.models.user import User

__all__ = [
    "AuditAction",
    "AuditLog",
    "Base",
    "Clinic",
    "ClinicMembership",
    "ClinicScopedBase",
    "GlobalBase",
    "MembershipRole",
    "Patient",
    "Provider",
    "ProviderType",
    "User",
]


# Attach audit event listeners after all models are imported.
# Deferred to here to avoid a circular import between audit.py and models.
from app.utils.audit import register_audited_models

register_audited_models()
