# Suture — Security & Compliance Posture

> Tracks what is actually built, what is deferred, and where the gaps are.
> The core controls below (tenant isolation, PHI encryption, audit logging,
> auth) are as-built and current. Module-specific surfaces added after the
> foundation (extraction, outreach, prior-auth, voice) are governed by their
> own ADRs in `docs/DECISIONS/`; ADR 011 records the tenant-isolation
> boundaries (as-built guard mechanism, the bare-`count(*)` limit, and the
> app-layer-only / no-RLS posture).

## Threat model summary

Suture handles PHI (Protected Health Information) under HIPAA. Primary threats:

1. **Cross-tenant data leakage** — clinic A reads clinic B's PHI.
2. **PHI in logs / telemetry** — an exception with patient data ends up in stdout.
3. **Audit gaps** — a PHI access happens but is not recorded.
4. **At-rest disclosure** — disk theft, backup leak, DB dump in a Slack channel.
5. **In-transit interception** — bearer token or PHI captured on the wire.
6. **Credential compromise** — leaked JWT secret, leaked Fernet key.

## Controls implemented in foundation

### 1. Multi-tenant isolation (Gate B1)
- Every clinic-scoped query is rewritten by a SQLAlchemy `before_execute` event listener to add `WHERE clinic_id = :current_clinic_id`.
- `current_clinic_id` comes from a `ContextVar` set by the auth dependency from the JWT.
- Queries with the context unset raise `TenantContextMissingError` — fail closed.
- An "attack path" test (`test_select_by_id_in_other_clinic_returns_empty`) asserts that attempting to fetch a known clinic-B row ID from a clinic-A session returns empty.
- Raw `text()` SQL in app code is forbidden — it bypasses the guard. The migration-skill enforces this.

### 2. PHI-safe logging (Gate A, tested Gate B1)
- structlog processor `scrub_phi` drops keys in a deny-list (`first_name`, `last_name`, `dob`, `phone`, `email`, `ssn`, `mrn`, addresses, member_id) before rendering.
- App code is forbidden to log PHI — `audit_logs.details` JSONB carries only IDs and column names.
- Test: log an event with `first_name="Jane"`, assert the key is absent from JSON output.

### 3. Audit logging (Gate B1)
- SQLAlchemy `after_insert`/`after_update`/`after_delete` event listeners on every PHI-bearing model write to `audit_logs`.
- View actions emitted from an explicit `track_view()` helper called from GET endpoints (SQLAlchemy has no SELECT event).
- `audit_logs.details` JSONB contains **only column names and IDs** — PHI values are never written.
- Schema: `clinic_id`, `user_id`, `action`, `resource_type`, `resource_id`, `details`, `ip_address`, `timestamp`.

### 4. Field-level PHI encryption (Gate B1)
- A `EncryptedString(TypeDecorator)` wraps `cryptography.fernet.Fernet` to encrypt/decrypt at the ORM boundary.
- Applied to `patients.dob`, `patients.phone`, `patients.ssn`, `insurance_policies.member_id`.
- Key: `PHI_ENCRYPTION_KEY` env var (32-byte base64). Generate locally with `make gen-phi-key`.
- Trade-off: encrypted columns are not searchable or indexable on value. By design — see ADR 003.

### 5. Auth (Gate B2)
- bcrypt password hashing via passlib.
- JWT signed HS256 with `JWT_SECRET` env (32 random bytes via `make gen-jwt-keys`).
- Access tokens TTL 1 hour, refresh tokens TTL 30 days.
- JWT carries `sub`, `clinic_id`, `role`, `exp`, `iat` — clinic_id drives the tenant guard.
- Frontend uses NextAuth Credentials → JWT strategy. Bearer token never crosses the bundle boundary directly (lives in NextAuth session or in the route-handler proxy under the fallback variant — see ADR 006).

### 6. RBAC
- Three roles per clinic: `admin`, `reviewer`, `readonly`.
- Mapped via `clinic_memberships`.
- Foundation only checks role at the auth boundary. Per-route enforcement begins in Module 1.

### 7. HTTP hardening
- **Security headers** on every response (`app/middleware.py`): `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, and a restrictive `Content-Security-Policy` (`default-src 'none'`) for JSON responses (the interactive docs are exempt so Swagger UI loads).
- **Rate limiting** on auth endpoints (`/api/auth/login`, `/api/auth/register`): fixed-window per-IP, `auth_rate_limit_per_minute` (default 20), returns 429 + `Retry-After`. In-process for the single-worker local v1; a multi-worker deployment swaps in a Redis-backed limiter. Implemented as pure ASGI middleware to preserve the tenant-guard ContextVar across streaming responses.

## Controls NOT implemented in foundation (deferred, documented)

| Control | Foundation | Plan |
|---|---|---|
| TLS in transit | Documented; mkcert for local dev pending | Add in Module 1 polish |
| Disk-level encryption | Documented; assumed at deployment time | Production deployment posture |
| Soft delete + retention | Schema includes `is_active` flags; retention policy hooks are stubs | Module 3a (workflow) |
| Dependency scanning | None | Add `pip-audit` and `pnpm audit` to CI in polish |
| SOC 2 controls | None — local dev only | v2+ |

## PHI key rotation (production path)

The Fernet key rotation strategy for v2:
1. Wrap the Fernet key with a KMS key (AWS KMS, GCP KMS, or HashiCorp Vault Transit).
2. On rotation: generate a new data key, re-encrypt all rows via a one-time migration script, update env, drop the old key.
3. Until KMS lands, the env-var key is the trust boundary. **Never commit `.env`.** `.gitignore` enforces this.

## Logging policy

**Never log:**
- Patient names (first, last, full)
- DOBs
- Phone numbers
- Email addresses
- SSNs
- MRNs (medical record numbers)
- Insurance member IDs
- Physical addresses
- Diagnosis descriptions (ICD-10 codes are OK as identifiers, but free-text diagnoses are not)
- Full document text from extractions

**Always log (when relevant):**
- UUIDs (patient_id, document_id, referral_id, ...)
- Status transitions
- AI model + token counts
- Latency, error codes
- User actions (user_id + action_type, no PHI in the details)

The `scrub_phi` processor is a backstop, not a primary control.

## Reporting a security issue

This is a solo-built project with no SLA. If you find a vulnerability, file an issue marked `security:` in the title. Do not post PHI in issues.
