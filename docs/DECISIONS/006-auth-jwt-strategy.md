# ADR 006 — Auth strategy: NextAuth Credentials → FastAPI HS256 JWT

**Status:** Accepted (2026-05-19) — primary path landed within timebox
**Author:** Shaurya

## Context

Gate B2 of the foundation had to ship a real end-to-end login. The plan
defined a primary path and a fallback:

- **Primary:** NextAuth Credentials provider proxies email/password to
  FastAPI `/api/auth/login`. FastAPI returns access + refresh JWTs.
  NextAuth stores both in its own JWT session cookie. A `jwt` callback
  refreshes the API access token on expiry by calling
  `/api/auth/refresh`.
- **Fallback (engaged if E2E not green in 4 hours):** NextAuth becomes a
  thin session cookie carrying only `userId`/`clinicId`. All API calls
  route through a Next.js Route Handler proxy that holds the refresh
  token in an HTTP-only cookie and exchanges it for an access token on
  the fly.

## Decision

**The primary path landed cleanly.** Gate B2 was completed in well under
the 4-hour timebox (≈90 minutes from first auth file to E2E verification).

Backend:
- `POST /api/auth/login` — validates credentials, picks the user's
  default clinic membership, returns access + refresh tokens.
- `POST /api/auth/refresh` — accepts a refresh token, returns a new
  access token. Re-validates the user is still active and has
  memberships.
- `GET /api/auth/me` — returns the current user, active clinic, role.
- `POST /api/auth/register` — admin-only, creates a user + default
  membership in the caller's clinic.
- JWT signing: **HS256** with `JWT_SECRET` from env (32 random bytes via
  `make gen-jwt-keys`). Access TTL 1h, refresh TTL 30d.
- `get_current_user` dependency parses the bearer, validates the user
  is active, validates the JWT's `clinic_id` corresponds to a real
  `clinic_memberships` row (defends against forged-but-signed tokens
  claiming an unauthorized clinic), then sets `current_clinic_id`,
  `current_user_id`, `current_ip_address` ContextVars before yielding.

Frontend:
- NextAuth v5 (Auth.js) Credentials provider in `apps/web/auth.ts`.
- `authorize()` calls `/api/auth/login`, then `/api/auth/me` for the
  profile, returns a `User` with `apiAccessToken`, `apiRefreshToken`,
  `clinicId`, `role`.
- `jwt` callback persists tokens on the NextAuth JWT. Refresh is
  attempted ~5 minutes before access TTL via `/api/auth/refresh`. On
  refresh failure, session is invalidated (`error: "RefreshFailed"`).
- `session` callback exposes `apiAccessToken`, `clinicId`, `role` to
  the client.
- `middleware.ts` protects every route except `/login`, `/api/auth/*`,
  and static assets — unauthenticated requests redirect to
  `/login?next=<original>`.
- `lib/api.ts::apiFetch()` is the server-side helper that pulls the
  bearer from the session and prepends it to API calls.

## Consequences

### Positive
- One identity layer: FastAPI is authoritative; NextAuth is a thin
  session shell. The frontend never sees raw passwords beyond the
  login form.
- The tenant guard works end-to-end: a real browser login mints a JWT
  with the right `clinic_id`; that JWT drives the SQLAlchemy session
  filter via the ContextVar.
- Forged-but-signed tokens that claim an unauthorized clinic are
  rejected by the `get_current_user` membership lookup
  (`test_jwt_with_unauthorized_clinic_rejected` verifies).
- HS256 + env secret is good enough for local dev. Rotation is simple
  (replace env var, restart).

### Negative
- **HS256 means the JWT secret is also the verification secret.**
  Anyone with the secret can mint tokens. Production needs RS256 with
  a KMS-managed private key. Documented as a v2 upgrade path.
- The NextAuth `jwt` callback runs on every request that touches the
  session. The 5-minute refresh-window heuristic is a tradeoff: too
  large and tokens expire mid-flight; too small and we hammer
  `/api/auth/refresh`. 55 minutes is the current value (5-minute
  buffer on a 1-hour token).
- The fallback (route-handler proxy) is not implemented because the
  primary path worked. The fallback design is preserved in the plan
  file in case a future change makes NextAuth refresh impossible.

## Verification

- 9 `test_auth.py` cases pass: login happy/wrong-password/inactive,
  refresh valid/invalid, /me requires-bearer/happy, register
  requires-admin/creates-user.
- 2 `test_auth_tenant_binding.py` cases pass: JWT clinic_id drives
  /me's `active_clinic_id`; forged-clinic-id JWT rejected with 403.
- Manual curl round-trip: login → me with bearer (200) → me without
  bearer (401).
- Manual browser: `/login` renders, `/` redirects to `/login?next=/`
  when unauthenticated.
- `pnpm exec next build` is clean — middleware bundles, all routes
  generate.

## Revisit when

- Production deployment (move to RS256 + KMS).
- We add SSO (NextAuth's other providers slot in beside Credentials).
- The 55-minute refresh heuristic causes user-visible bounces — tune
  the buffer or move to silent on-demand refresh.
- We need clinic-switching mid-session — adds an endpoint that
  re-mints the access token with a different `clinic_id`.
