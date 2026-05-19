# ADR 003 — Field-level PHI encryption with Fernet via SQLAlchemy TypeDecorator

**Status:** Accepted (2026-05-18)
**Author:** Shaurya

## Context

Some PHI columns (`dob`, `phone`, `ssn`, insurance `member_id`) should be encrypted at rest, distinct from disk-level encryption. Three options:

1. **`pgcrypto` column encryption:** Postgres-native, ciphertext in the column, decrypt with `pgp_sym_decrypt(col, key)`. Looks serious on paper.
2. **App-layer Fernet via SQLAlchemy `TypeDecorator`:** symmetric encryption at the ORM boundary, ciphertext in `String` columns.
3. **Defer entirely:** TLS in transit + disk encryption, no column-level encryption in v1.

## Decision

Option 2 — Fernet `TypeDecorator`.

- `EncryptedString` in `app/utils/encryption.py` wraps `cryptography.fernet.Fernet`.
- Key from `settings.PHI_ENCRYPTION_KEY` (32-byte base64 from env). Generated locally by `make gen-phi-key`.
- Applied to `patients.dob` (stored as `YYYY-MM-DD` ciphertext), `patients.phone`, `patients.ssn`, `insurance_policies.member_id`.
- Test verifies that a raw `SELECT` from the DB returns ciphertext while the ORM returns plaintext.

## Consequences

### Positive
- App code reads/writes plaintext via the ORM — no special-casing.
- Fernet provides authenticated encryption (HMAC-SHA256) — ciphertext can't be silently tampered with.
- IV randomness means two patients with the same DOB have different ciphertext (verified by test).
- Migrating encrypted data on key rotation is a single Python script.
- Honest: TLS + Fernet + disk encryption is the real production posture, not a checkbox.

### Negative
- **Encrypted columns are not searchable or indexable on value.** Cannot `WHERE phone = '...'`. Cannot `LIKE '%555%'`. By design.
  - Plan queries around this: indexed columns for search keys (MRN, last_name); encrypted columns for retrieval only.
- The Fernet key is now a critical secret. Loss = data loss. Production must move to KMS (documented in SECURITY.md).
- Slight CPU overhead per row (~microseconds; not measurable in profile).

### Rejected: pgcrypto
- Column-level pgcrypto requires `pgp_sym_decrypt(col, :key)` in every query reading the column — breaks ORM patterns, breaks autogeneration, breaks JOINs in subtle ways.
- The decryption key lives in the SQL query, which is a leak vector via logs / `pg_stat_statements`.
- "Looks compliant" but the implementation surface area is larger and the practical bugs are worse.

### Rejected: defer entirely
- Healthcare audience and HIPAA framing make "no PHI encryption" indefensible in v1, even for a portfolio project.

## Production path (deferred to v2)

1. Move `PHI_ENCRYPTION_KEY` behind a KMS (AWS KMS / GCP KMS / HashiCorp Vault Transit).
2. On rotation: KMS-wrapped data key → re-encrypt all rows in a one-time migration → drop the old key.
3. Audit-log every decryption event.

## Revisit when

- KMS becomes available (production deploy).
- We need search on an encrypted column (likely indicates the column shouldn't be encrypted — re-classify).
- Key rotation policy formalizes (probably driven by SOC 2 readiness).
