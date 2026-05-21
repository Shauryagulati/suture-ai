"""Migration round-trip tests.

Use a dedicated `suture_migration_test` database (separate from the one
the rest of the test suite uses) so we can apply alembic upgrade/downgrade
fully without colliding with the metadata.create_all() schema.

These tests shell out to alembic so we test the actual command path that
runs in CI and production.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.asyncio


MIGRATION_DB_NAME = "suture_migration_test"
ADMIN_URL = "postgresql+asyncpg://suture:suture_dev_password@localhost:5432/postgres"
MIGRATION_URL = (
    f"postgresql+asyncpg://suture:suture_dev_password@localhost:5432/{MIGRATION_DB_NAME}"
)
# Alembic uses sync (or async) URL; our env.py picks up `database_url` from
# settings — we override via env var below.
API_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
async def fresh_migration_db() -> AsyncIterator[None]:
    """Drop + recreate suture_migration_test with extensions enabled."""
    admin_engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.exec_driver_sql(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{MIGRATION_DB_NAME}' AND pid <> pg_backend_pid()"
        )
        await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{MIGRATION_DB_NAME}"')
        await conn.exec_driver_sql(f'CREATE DATABASE "{MIGRATION_DB_NAME}"')
    await admin_engine.dispose()

    target = create_async_engine(MIGRATION_URL)
    async with target.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS citext")
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        await conn.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    await target.dispose()

    yield

    admin_engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.exec_driver_sql(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{MIGRATION_DB_NAME}' AND pid <> pg_backend_pid()"
        )
        await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{MIGRATION_DB_NAME}"')
    await admin_engine.dispose()


def _run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = MIGRATION_URL
    return subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


async def test_upgrade_head_clean_on_empty_db(fresh_migration_db: None) -> None:
    """`alembic upgrade head` succeeds from an empty database."""
    result = _run_alembic("upgrade", "head")
    assert result.returncode == 0, (
        f"alembic upgrade head failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # Quick sanity: at least the alembic_version table + a known table exist.
    engine = create_async_engine(MIGRATION_URL)
    async with engine.connect() as conn:
        rows = await conn.exec_driver_sql(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        tables = {r[0] for r in rows.fetchall()}
    await engine.dispose()

    assert "alembic_version" in tables
    assert "clinics" in tables  # 0001
    assert "documents" in tables  # 0002
    assert "payer_rules" in tables  # 0002


async def test_downgrade_to_base_then_upgrade_head_round_trip(
    fresh_migration_db: None,
) -> None:
    """upgrade → downgrade base → upgrade head round-trip is clean.

    Catches missing DROP TYPE / DROP TABLE statements in downgrade().
    """
    up1 = _run_alembic("upgrade", "head")
    assert up1.returncode == 0, f"first upgrade failed: {up1.stderr}"

    down = _run_alembic("downgrade", "base")
    assert down.returncode == 0, f"downgrade failed: {down.stderr}"

    # Verify only alembic_version remains.
    engine = create_async_engine(MIGRATION_URL)
    async with engine.connect() as conn:
        rows = await conn.exec_driver_sql(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        tables = {r[0] for r in rows.fetchall()}
    await engine.dispose()

    assert tables.issubset({"alembic_version"}), (
        f"downgrade left tables behind: {tables - {'alembic_version'}}"
    )

    up2 = _run_alembic("upgrade", "head")
    assert up2.returncode == 0, (
        f"second upgrade (after downgrade) failed — likely a missing "
        f"DROP TYPE in downgrade():\nstderr: {up2.stderr}"
    )


async def test_migration_003_upgrades_vector_dimension(
    fresh_migration_db: None,
) -> None:
    """Migration 0003 changes payer_rules.embedding from vector(384) to vector(1024).

    Verifies the round-trip: head -> downgrade -1 (back to vector(384)) -> head
    (back to vector(1024)).
    """
    dim_query = (
        "SELECT format_type(atttypid, atttypmod) "
        "FROM pg_attribute "
        "WHERE attrelid = 'payer_rules'::regclass AND attname = 'embedding'"
    )

    async def _embedding_type() -> str:
        engine = create_async_engine(MIGRATION_URL)
        async with engine.connect() as conn:
            rows = await conn.exec_driver_sql(dim_query)
            value = rows.scalar()
        await engine.dispose()
        return str(value)

    up = _run_alembic("upgrade", "head")
    assert up.returncode == 0, f"upgrade head failed: {up.stderr}"
    assert await _embedding_type() == "vector(1024)"

    down = _run_alembic("downgrade", "-1")
    assert down.returncode == 0, f"downgrade -1 failed: {down.stderr}"
    assert await _embedding_type() == "vector(384)"

    up2 = _run_alembic("upgrade", "head")
    assert up2.returncode == 0, f"re-upgrade head failed: {up2.stderr}"
    assert await _embedding_type() == "vector(1024)"
