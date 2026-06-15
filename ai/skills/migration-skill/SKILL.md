---
name: migration-skill
description: Use when creating a new Alembic migration for the Suture backend. Enforces TIMESTAMPTZ, ClinicScopedBase pattern, encrypted columns, audit registry, reversible downgrades.
---

# Migration skill

This skill is the canonical reference for writing Alembic migrations in `apps/api/alembic/versions/`. Every project anti-pattern around the data layer (naive datetimes, broken downgrades, missing audit hooks, raw-SQL tenant bypasses) is preventable if you follow this skill.

## Decision tree: what base class does the new table use?

```
Is the table tenant-scoped (one row belongs to exactly one clinic)?
├── YES → inherits from ClinicScopedBase. Has `clinic_id UUID NOT NULL`.
│        Migration must add an index on clinic_id.
└── NO  → does it represent the tenant itself (clinics) or a global entity
         that spans clinics (users, clinic_memberships)?
         └── YES → inherits from GlobalBase. No clinic_id.
                   This is the ONLY legitimate reason to skip ClinicScopedBase.
                   Add `_skip_tenant_guard = True` on the ORM model.
```

If you can't answer YES to either branch confidently, ask the user. **Defaulting to ClinicScopedBase is always safer.**

## Step-by-step: create a migration

### 1. Generate the revision

```bash
cd apps/api && uv run alembic revision -m "short_snake_case_description"
```

This writes `apps/api/alembic/versions/<rev_id>_short_snake_case_description.py`.

**Do not use `--autogenerate`** until you've reviewed what it produces. Autogenerate misses:
- `TIMESTAMPTZ` (defaults to naive)
- The audit listener registration step (not in the schema)
- Enum down-migrations (often forgotten)

### 2. Write the `upgrade()` function

#### Required column patterns

```python
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg
from alembic import op

# Primary key
sa.Column('id', pg.UUID(as_uuid=True), primary_key=True, server_default=sa.func.uuid_generate_v4())

# Tenant foreign key (clinic-scoped tables only)
sa.Column('clinic_id', pg.UUID(as_uuid=True), sa.ForeignKey('clinics.id'), nullable=False)

# Timestamps — ALWAYS timezone=True
sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False)

# An instant column (TIMESTAMPTZ). Name ends in `_at`.
sa.Column('appointment_at', sa.DateTime(timezone=True), nullable=False)

# A calendar date (no time, no zone).
sa.Column('discharge_date', sa.Date, nullable=False)

# An encrypted PHI column. The migration sees it as a string; the ORM uses EncryptedString.
sa.Column('dob', sa.String, nullable=False)  # encrypted at app layer (EncryptedString TypeDecorator)
sa.Column('phone', sa.String, nullable=False)  # encrypted at app layer
sa.Column('ssn', sa.String, nullable=True)  # encrypted at app layer

# An enum. Always name it.
sa.Column('status', sa.Enum('new', 'reviewed', 'archived', name='document_status'), nullable=False)

# pgvector embedding. 1024-dim for the default bge-m3 provider (ADR 007).
# Match the column to get_embedding_provider().dimension — don't hardcode blindly.
sa.Column('embedding', pg.Vector(1024), nullable=True)
```

#### Required index pattern

```python
op.create_index('ix_documents_clinic_id', 'documents', ['clinic_id'])
op.create_index('ix_documents_status_urgency', 'documents', ['status', 'urgency'])
# pgvector index (ivfflat, cosine distance)
op.execute("CREATE INDEX ix_payer_rules_embedding ON payer_rules USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")
```

### 3. Write the `downgrade()` function

**Real downgrades, not `pass`.** Drop in reverse FK dependency order:

```python
def downgrade() -> None:
    op.drop_index('ix_documents_status_urgency', table_name='documents')
    op.drop_index('ix_documents_clinic_id', table_name='documents')
    op.drop_table('documents')
    op.execute('DROP TYPE document_status')  # explicit enum drop
```

The `test_migration.py::test_downgrade_to_base_then_upgrade_head_round_trip` test catches broken downgrades.

### 4. Register the model with the audit listener (PHI-bearing tables only)

In `apps/api/app/utils/audit.py`:

```python
from app.models import Document  # or wherever the new model lives

AUDITED_MODELS: list[type[ClinicScopedBase]] = [
    Patient,
    Document,  # ← add the new model here
    ...
]
```

The listener fires on `after_insert`, `after_update`, `after_delete` automatically. For GET endpoints that read PHI, call `track_view()` explicitly from the route handler.

### 5. Run and verify

```bash
make migrate            # apply
make migrate-down       # downgrade to base
make migrate            # upgrade head again (round-trip test)
uv --project apps/api run pytest tests/test_migration.py -v
```

If `test_downgrade_to_base_then_upgrade_head_round_trip` fails, the downgrade is broken — fix it before commit.

## Anti-patterns the linters won't catch

- `sa.DateTime()` (no `timezone=True`) — naive datetime. **Forbidden.**
- `nullable=True` on `clinic_id` — defeats the tenant guard. Only legal on `audit_logs` (system actions).
- Using `pgcrypto`'s `pgp_sym_encrypt` directly in a column default — we use Fernet at the ORM layer, never pgcrypto. See ADR 003.
- Forgetting to drop a CHECK constraint or enum in `downgrade()` — silently breaks the round-trip test.
- Adding a column NOT NULL without `server_default` to a table that already has rows — fails in CI on the round-trip test. Either provide a default or do a two-step migration (add nullable → backfill → set NOT NULL).

## Common patterns

### Add a column to an existing table

```python
def upgrade() -> None:
    op.add_column('patients', sa.Column('preferred_contact_method', sa.Enum('sms', 'email', 'voice', name='contact_method'), nullable=False, server_default='sms'))

def downgrade() -> None:
    op.drop_column('patients', 'preferred_contact_method')
    op.execute('DROP TYPE contact_method')
```

### Add a new index

```python
def upgrade() -> None:
    op.create_index('ix_referrals_status_urgency', 'referrals', ['status', 'urgency'])

def downgrade() -> None:
    op.drop_index('ix_referrals_status_urgency', table_name='referrals')
```

### Rename a column

```python
def upgrade() -> None:
    op.alter_column('appointments', 'appointment_date', new_column_name='appointment_at', existing_type=sa.DateTime(timezone=True))

def downgrade() -> None:
    op.alter_column('appointments', 'appointment_at', new_column_name='appointment_date', existing_type=sa.DateTime(timezone=True))
```

## Verification checklist (run before commit)

- [ ] All datetime columns use `sa.DateTime(timezone=True)`
- [ ] All FK columns have an explicit index
- [ ] `downgrade()` is real and reverse-FK-order
- [ ] Any new PHI model is registered in `AUDITED_MODELS`
- [ ] `make migrate-down && make migrate` succeeds
- [ ] `pytest tests/test_migration.py` passes
