# Suture — Demo Script

A ~5-minute walkthrough of the closed loop: **fax in → AI → review → workflow → outreach →
prior-auth → analytics.** Everything runs locally.

## Setup (once, before the demo)

```bash
make infra-up
make migrate
make seed
make seed-documents      # pre-loads the inbox + drives several docs through approval
make eval-extraction     # real extraction metrics for the Evals dashboard
make dev                 # api :8000, web :3000

# Voice (optional), in separate terminals:
make voice-up            # LiveKit server (Docker)
make voice-agent         # Ember worker (Whisper/Piper download on first run)
```

Sign in at <http://localhost:3000>:

```
admin@steel-city-cardiology.example.com  /  suture_dev_123
```

> Tip: run `make seed && make seed-documents` fresh right before demoing so the inbox,
> referrals, tasks, outreach, **and insurance policies** are all populated.

## The script

**1. The inbox (30s).** Land on `/inbox`. Point out the queue of inbound referral and
discharge PDFs with AI **classification** + confidence, status, and urgency. Click a column
header to sort. Switch to the **Needs review** tab.

**2. Review & extract (90s).** Open a referral → **Review**. Show the **side-by-side PDF and
extracted fields**, each with a deterministic **confidence badge**. Highlight a low-confidence
or missing field (e.g. phone), click the pencil, correct it inline. Note the confidence is
validator-derived, not the model's self-report.

**3. Approve → workflow engages (45s).** Click **Approve extraction**. If a required
field (patient name, DOB, or phone; provider name or NPI) is still missing, approval is
blocked with a message naming the field — **edit it inline first (the PATCH), then
approve**. On success this creates the Patient, the referring Provider, the **Referral**,
and persists the **insurance policy** —
then advances the referral to *ready_to_schedule*, which **generates SLA tasks and schedules
the outreach cadence.** You land on **Tasks**.

**4. Tasks (30s).** Show the SLA-tracked work queue with status + SLA badges. Open a task,
change its status, save.

**5. Prior auth (45s).** Go to **Prior Authorization → Check**. Enter a payer (e.g.
*Highmark BCBS PA*), procedure `93458`, diagnosis `I25.10`. Run it — the **payer-rules RAG**
returns auth-required, reasoning, required documents, turnaround, and the policy excerpts it
cited. (The packet generator builds the submission PDF from the referral's insurance on file.)

**6. Discharge closed loop (45s).** Open a discharge detail page. Walk the **timeline**
(human-readable events), the clinical summary, and the confirmation-fax panel — the loop that
faxes confirmation back to the discharging hospital.

**7. Analytics (30s).** **Analytics**: **referral leakage** (at-risk follow-ups), **payer
friction**, **referral quality**, and an **ROI** estimate (hours saved, projected revenue
recovered).

**8. Evals (20s).** **Analytics → Evals**: the extraction harness's real accuracy per run
(exact-match, macro-F1), recorded in `eval_runs` — how prompt/model changes are tracked.

**9. Voice — Ember (optional, ~60s).** On **Voice**, click **Start test call** → a new tab opens
the browser caller → **Connect** (Ember waits for you, then greets) → unmute the mic and ask to
schedule; the live transcript streams on the call's monitor page. Needs `make voice-up` +
`make voice-agent`. The browser caller stands in for a phone — PSTN is deferred (ADR 010).

## Be transparent about v1 boundaries

If asked — these are deliberate local-only scoping decisions, not gaps in the pipeline (the
full flow executes and is auditable end to end):

- **Delivery channels are stubbed.** SMS/email/voice/fax run through local stub providers; no
  message physically leaves the machine (ADR 010). The voice agent uses a browser test-caller,
  not a real phone (PSTN deferred — cost + BAA).
- **Default LLM is a local 4B model** (`medgemma1.5`); BYOK Claude Sonnet is materially more
  accurate (see `docs/EVAL.md`).
- **Extraction runs inline** on upload (~10–25s on the local model); the service is
  Celery-shaped for a later move to a worker (ADR 008).
- **Auth is HS256 / Fernet env key** for local single-issuer use; RS256 + KMS rotation is the
  documented production path (ADRs 003, 006; `docs/SECURITY.md`).
