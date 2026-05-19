"""SQLAlchemy ORM models.

Importing this package registers all models with the declarative base
metadata and with the audit listener registry. Always import via
`from app.models import ...` so registration side-effects run.
"""

from __future__ import annotations

from app.models.ai_invocation import AiInvocation, InvocationType
from app.models.appointment import Appointment, AppointmentStatus
from app.models.audit_log import AuditAction, AuditLog
from app.models.base import Base, ClinicScopedBase, GlobalBase
from app.models.call import Call, CallStatus, CallTranscript, CallType
from app.models.clinic import Clinic
from app.models.clinic_membership import ClinicMembership, MembershipRole
from app.models.discharge_summary import (
    DischargeStatus,
    DischargeSummary,
    UrgencyTier,
)
from app.models.document import (
    Document,
    DocumentClassification,
    DocumentStatus,
    UrgencyLevel,
)
from app.models.document_extraction import DocumentExtraction
from app.models.eval_run import EvalRun, EvalType
from app.models.fax import Fax, FaxDirection, FaxStatus, FaxType
from app.models.insurance_policy import (
    EligibilityCheck,
    EligibilityResult,
    InsurancePolicy,
    VerificationStatus,
)
from app.models.outreach_attempt import (
    OutreachAttempt,
    OutreachChannel,
    OutreachStatus,
)
from app.models.patient import Patient
from app.models.payer_rule import PayerRule
from app.models.prior_auth import (
    PriorAuth,
    PriorAuthEvent,
    PriorAuthEventType,
    PriorAuthStatus,
)
from app.models.provider import Provider, ProviderType
from app.models.referral import Referral, ReferralStatus
from app.models.referral_task import (
    ReferralTask,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from app.models.user import User
from app.models.workflow_run import WorkflowRun, WorkflowStatus

__all__ = [
    "AiInvocation",
    "Appointment",
    "AppointmentStatus",
    "AuditAction",
    "AuditLog",
    "Base",
    "Call",
    "CallStatus",
    "CallTranscript",
    "CallType",
    "Clinic",
    "ClinicMembership",
    "ClinicScopedBase",
    "DischargeStatus",
    "DischargeSummary",
    "Document",
    "DocumentClassification",
    "DocumentExtraction",
    "DocumentStatus",
    "EligibilityCheck",
    "EligibilityResult",
    "EvalRun",
    "EvalType",
    "Fax",
    "FaxDirection",
    "FaxStatus",
    "FaxType",
    "GlobalBase",
    "InsurancePolicy",
    "InvocationType",
    "MembershipRole",
    "OutreachAttempt",
    "OutreachChannel",
    "OutreachStatus",
    "Patient",
    "PayerRule",
    "PriorAuth",
    "PriorAuthEvent",
    "PriorAuthEventType",
    "PriorAuthStatus",
    "Provider",
    "ProviderType",
    "Referral",
    "ReferralStatus",
    "ReferralTask",
    "TaskPriority",
    "TaskStatus",
    "TaskType",
    "UrgencyLevel",
    "UrgencyTier",
    "User",
    "VerificationStatus",
    "WorkflowRun",
    "WorkflowStatus",
]


# Attach audit event listeners after all models are imported.
# Deferred to here to avoid a circular import between audit.py and models.
from app.utils.audit import register_audited_models

register_audited_models()
