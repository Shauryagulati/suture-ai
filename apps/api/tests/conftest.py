"""Shared pytest fixtures.

DB strategy: a dedicated `suture_test` database is created at session
start (dropping any existing one) and populated via
`Base.metadata.create_all`. Each test gets its own AsyncSession; tests
that need rollback isolation can use `db_session_rollback`, tests that
need to inspect committed state use `db_session`.

PHI_ENCRYPTION_KEY and DATABASE_URL are set BEFORE the app modules are
imported, so settings pick them up.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

# Make `seeds.scripts.seed_dev` importable for test_seed.py.
# Layout: <root>/apps/api/tests/conftest.py and <root>/seeds/
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ── Test environment — set BEFORE any app imports ──
os.environ.setdefault("PHI_ENCRYPTION_KEY", "VbDtA5sCxOf8b9pYwT-jXNVKfNF7HMu0_rDFZIO_eIM=")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://suture:suture_dev_password@localhost:5432/suture_test",
)
os.environ.setdefault("JWT_SECRET", "test_jwt_secret_abc")
os.environ.setdefault("OTEL_DISABLED", "1")

# Late imports — env vars above must be set BEFORE app/* loads settings.
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Force every async test onto the session-scoped event loop.

    With `asyncio_default_fixture_loop_scope = "session"`, fixtures share
    one loop. Without this hook, tests still default to function-scope,
    which causes asyncpg connections to bind to a loop the next fixture
    can't reach. Marking every test session-scoped puts them all on the
    same loop as the fixtures.
    """
    for item in items:
        if "asyncio" in item.keywords:
            item.add_marker(pytest.mark.asyncio(loop_scope="session"))


from app.config import get_settings  # noqa: E402
from app.database import async_session_maker  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Clinic, User  # noqa: E402 — side-effect imports
from app.utils.context import current_clinic_id, current_user_id  # noqa: E402

# Admin DB URL (postgres database) for creating/dropping the test DB.
ADMIN_DB_URL = "postgresql+asyncpg://suture:suture_dev_password@localhost:5432/postgres"
TEST_DB_NAME = "suture_test"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
async def _create_test_database() -> AsyncIterator[None]:
    """Drop + create the test DB once per pytest session, then create tables."""
    admin_engine = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        # Terminate other connections so we can drop.
        await conn.exec_driver_sql(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{TEST_DB_NAME}' AND pid <> pg_backend_pid()"
        )
        await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"')
        await conn.exec_driver_sql(f'CREATE DATABASE "{TEST_DB_NAME}"')
    await admin_engine.dispose()

    # Enable extensions and create schema on the fresh test DB.
    test_engine = create_async_engine(get_settings().database_url)
    async with test_engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS citext")
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        await conn.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.create_all)
    await test_engine.dispose()

    yield

    # Teardown: drop the test DB to leave a clean slate.
    admin_engine = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.exec_driver_sql(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{TEST_DB_NAME}' AND pid <> pg_backend_pid()"
        )
        await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"')
    await admin_engine.dispose()


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Yield a fresh AsyncSession. Caller is responsible for commits.

    Truncates clinic-scoped tables at fixture exit so the next test
    starts clean. (Simpler than rollback for tests that need to see
    audit-log side-effects, which fire on commit.)
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass  # Ignore rollback errors — cleanup below is always authoritative.
            # Truncate everything between tests for isolation. Order is
            # children-before-parents so RESTRICT FKs (e.g. referral_tasks
            # -> patients) don't block the patients DELETE.
            async with async_session_maker() as cleanup:
                await cleanup.execute(Base.metadata.tables["audit_logs"].delete())
                await cleanup.execute(Base.metadata.tables["eval_runs"].delete())
                await cleanup.execute(Base.metadata.tables["ai_invocations"].delete())
                await cleanup.execute(Base.metadata.tables["prior_auth_events"].delete())
                await cleanup.execute(Base.metadata.tables["prior_auths"].delete())
                await cleanup.execute(Base.metadata.tables["call_transcripts"].delete())
                await cleanup.execute(Base.metadata.tables["calls"].delete())
                await cleanup.execute(Base.metadata.tables["document_extractions"].delete())
                await cleanup.execute(Base.metadata.tables["referral_tasks"].delete())
                await cleanup.execute(Base.metadata.tables["referrals"].delete())
                await cleanup.execute(Base.metadata.tables["discharge_summaries"].delete())
                await cleanup.execute(Base.metadata.tables["appointments"].delete())
                await cleanup.execute(Base.metadata.tables["outreach_attempts"].delete())
                await cleanup.execute(Base.metadata.tables["eligibility_checks"].delete())
                await cleanup.execute(Base.metadata.tables["insurance_policies"].delete())
                await cleanup.execute(Base.metadata.tables["documents"].delete())
                await cleanup.execute(Base.metadata.tables["patients"].delete())
                await cleanup.execute(Base.metadata.tables["providers"].delete())
                await cleanup.execute(Base.metadata.tables["clinic_memberships"].delete())
                await cleanup.execute(Base.metadata.tables["users"].delete())
                await cleanup.execute(Base.metadata.tables["clinics"].delete())
                await cleanup.commit()


@pytest.fixture
async def two_clinics(db_session: AsyncSession) -> tuple[UUID, UUID]:
    """Insert two clinics; return their IDs.

    Clinics are GlobalBase so the tenant guard is not engaged for this
    insert.
    """
    clinic_a_id = uuid4()
    clinic_b_id = uuid4()
    db_session.add(Clinic(id=clinic_a_id, name="Test Clinic A", slug="test-clinic-a"))
    db_session.add(Clinic(id=clinic_b_id, name="Test Clinic B", slug="test-clinic-b"))
    await db_session.commit()
    return clinic_a_id, clinic_b_id


@pytest.fixture
async def test_user(db_session: AsyncSession) -> UUID:
    """Insert a test user (global table) and return its ID.

    Used by audit tests that need a real user_id for the FK constraint.
    """
    user = User(
        id=uuid4(),
        email=f"test-{uuid4().hex[:8]}@suture-test.example.com",
        hashed_password="$2b$12$test_only_not_a_real_hash_value_here_xyz",
        full_name="Test User",
    )
    db_session.add(user)
    await db_session.commit()
    return user.id


@pytest.fixture
def set_clinic_context() -> Any:
    """Return a context manager that sets/resets ContextVars for a test.

    Usage:
        async def test_xxx(set_clinic_context):
            with set_clinic_context(clinic_id=clinic_a_id, user_id=user_id):
                ...
    """
    from contextlib import contextmanager

    @contextmanager
    def _ctx(clinic_id: UUID | None = None, user_id: UUID | None = None) -> Any:
        cid_token = current_clinic_id.set(clinic_id)
        uid_token = current_user_id.set(user_id)
        try:
            yield
        finally:
            current_clinic_id.reset(cid_token)
            current_user_id.reset(uid_token)

    return _ctx


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authed_client_factory(client, db_session, two_clinics):
    """Factory: returns an async function that creates a user in a given
    clinic, logs in, and returns (client, headers_dict, user_id).

    Usage:
        client_a, headers_a, user_id_a = await authed_client_factory("a")
    """
    from app.models.clinic_membership import ClinicMembership, MembershipRole
    from app.models.user import User
    from app.utils.security import hash_password

    clinic_a_id, clinic_b_id = two_clinics

    async def _make(letter: str):
        clinic_id = clinic_a_id if letter == "a" else clinic_b_id
        email = f"endpoint-test-{letter}-{uuid4().hex[:6]}@suture-test.example.com"
        user = User(
            id=uuid4(),
            email=email,
            hashed_password=hash_password("test-password-xyz"),
            full_name="Endpoint Test User",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        db_session.add(
            ClinicMembership(
                user_id=user.id, clinic_id=clinic_id, role=MembershipRole.admin, is_default=True
            )
        )
        await db_session.commit()

        resp = await client.post(
            "/api/auth/login",
            json={"email": email, "password": "test-password-xyz"},
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        return client, {"Authorization": f"Bearer {token}"}, user.id

    return _make


@pytest.fixture
async def seeded_referral_a(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    """A Referral in clinic A in status `needs_review`, with a real Patient."""
    from app.models.document import UrgencyLevel
    from app.models.patient import Patient
    from app.models.referral import Referral, ReferralStatus

    clinic_a_id, _ = two_clinics
    patient_id = uuid4()
    referral_id = uuid4()
    referral = Referral(
        id=referral_id,
        clinic_id=clinic_a_id,
        patient_id=patient_id,
        status=ReferralStatus.needs_review,
        urgency=UrgencyLevel.urgent,
        diagnosis_codes=["I25.10"],
        procedure_codes=["93306"],
    )
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        db_session.add_all(
            [
                Patient(
                    id=patient_id,
                    clinic_id=clinic_a_id,
                    mrn=f"MRN-{uuid4().hex[:6]}",
                    first_name="Pat",
                    last_name="Ref",
                    dob="1972-03-10",
                    phone="412-555-0150",
                ),
                referral,
            ]
        )
        await db_session.commit()
    # expire_on_commit=False means the object retains its attribute values after commit
    # and remains in the session's identity map — no re-fetch needed.
    return referral


@pytest.fixture
async def seeded_discharge_a(
    db_session: AsyncSession,
    two_clinics: tuple[UUID, UUID],
    test_user: UUID,
    set_clinic_context,
):
    """A DischargeSummary in clinic A in status `new`, urgency_tier=critical (post-MI)."""
    from datetime import date

    from app.models.discharge_summary import DischargeStatus, DischargeSummary, UrgencyTier
    from app.models.patient import Patient

    clinic_a_id, _ = two_clinics
    patient_id = uuid4()
    discharge_id = uuid4()
    discharge = DischargeSummary(
        id=discharge_id,
        clinic_id=clinic_a_id,
        patient_id=patient_id,
        status=DischargeStatus.new,
        urgency_tier=UrgencyTier.critical,
        discharge_date=date(2026, 5, 20),
        diagnosis_codes=["I21.4"],
        urgent_flags=["recent_MI"],
        follow_up_window_days=7,
    )
    with set_clinic_context(clinic_id=clinic_a_id, user_id=test_user):
        # Flush Patient first so the FK dependency is satisfied before discharge insert.
        db_session.add(
            Patient(
                id=patient_id,
                clinic_id=clinic_a_id,
                mrn=f"MRN-{uuid4().hex[:6]}",
                first_name="Pat",
                last_name="Disch",
                dob="1955-07-04",
                phone="412-555-0160",
            )
        )
        await db_session.flush()
        db_session.add(discharge)
        await db_session.commit()
    # expire_on_commit=False means the object retains its attribute values after commit
    # and remains in the session's identity map — no re-fetch needed.
    return discharge
