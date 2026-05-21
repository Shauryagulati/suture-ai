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
            await session.rollback()
            # Truncate everything between tests for isolation. Order is
            # children-before-parents so RESTRICT FKs (e.g. referral_tasks
            # -> patients) don't block the patients DELETE.
            async with async_session_maker() as cleanup:
                await cleanup.execute(Base.metadata.tables["audit_logs"].delete())
                await cleanup.execute(Base.metadata.tables["referral_tasks"].delete())
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
