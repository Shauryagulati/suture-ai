# Suture — Backend (apps/api)

> Backend patterns. For project-wide rules, see the repo root `CLAUDE.md`.

## Module layout

```
apps/api/app/
├── main.py              # FastAPI app + lifespan
├── config.py            # pydantic-settings
├── database.py          # async engine + ClinicScopedSession + tenant guard event listener
├── utils/
│   ├── context.py       # current_clinic_id / current_user_id / current_ip_address ContextVars
│   ├── encryption.py    # EncryptedString (Fernet TypeDecorator)
│   ├── audit.py         # after_insert/update/delete listeners + track_view() helper
│   └── logging.py       # PHI-safe structlog
├── models/              # ORM models. Inherit ClinicScopedBase or GlobalBase.
├── schemas/             # Pydantic request/response models (Gate B2+)
├── routers/             # FastAPI route handlers
└── services/            # Business logic
```

## Patterns

### Adding a new tenant-scoped table

```python
# app/models/foo.py
from app.models.base import ClinicScopedBase

class Foo(ClinicScopedBase):
    __tablename__ = "foos"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
```

Then:
1. Write the Alembic migration (use `ai/skills/migration-skill/SKILL.md`).
2. If the model carries PHI, register it in `app/utils/audit.py::register_audited_models()` so insert/update/delete events emit audit rows.
3. Add the model to `app/models/__init__.py` exports.

### Adding a global table (rare — clinics/users/clinic_memberships only)

```python
from app.models.base import GlobalBase
class Vendor(GlobalBase):  # skip tenant guard
    __tablename__ = "vendors"
```

There must be an ADR explaining why a new table bypasses tenancy. Default to `ClinicScopedBase`.

### Adding an encrypted column

```python
from app.utils.encryption import EncryptedString

class Patient(ClinicScopedBase):
    ssn: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
```

Encrypted columns are not searchable on value. In the Alembic migration, declare them as plain `sa.String` (the TypeDecorator applies at the ORM layer only) and add a comment `# encrypted at app layer`.

### Adding a router

```python
# app/routers/foo.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_current_user  # Gate B2

router = APIRouter(prefix="/api/foo", tags=["foo"])

@router.get("/{foo_id}")
async def get_foo(
    foo_id: UUID,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user),
) -> FooResponse: ...
```

Register the router in `app/main.py`: `app.include_router(foo.router)`.

For GET endpoints that return PHI, call `track_view()` from `app/utils/audit.py` so the read is audited.

### Dependency ordering

`get_current_user` sets the `current_clinic_id` and `current_user_id` ContextVars BEFORE the DB session yields. Always declare it BEFORE `get_db` in the route signature so FastAPI resolves it first.

```python
async def my_route(
    user = Depends(get_current_user),  # sets ContextVars
    db: AsyncSession = Depends(get_db),  # uses ContextVars via tenant guard
):
```

## Anti-patterns

- ❌ Raw `text()` SQL outside Alembic migrations — bypasses the tenant guard.
- ❌ Manual `WHERE clinic_id = ...` in queries — the guard does this; doubling up is a code smell that suggests confusion.
- ❌ Naive `DateTime` columns — every datetime is `TIMESTAMPTZ`.
- ❌ Logging PHI values — only IDs.
- ❌ Skipping `AUDITED_MODELS` registration for a new PHI model.

## Running

```bash
uv sync                                   # install deps
uv run uvicorn app.main:app --reload      # dev server on :8000
uv run pytest -v                          # tests
uv run mypy app                           # type check
uv run ruff check app tests               # lint
uv run ruff format app tests              # auto-format
uv run alembic upgrade head               # apply migrations
uv run alembic revision -m "..."          # new migration
```
