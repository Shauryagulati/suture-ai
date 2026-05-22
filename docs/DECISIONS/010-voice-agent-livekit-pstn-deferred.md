# ADR 010 — Voice agent uses a browser caller; PSTN deferred to v2

**Status:** Accepted (2026-05-22)
**Author:** Shaurya

## Context

Module 6 (Ember, the voice agent) needs a way for a real patient to
talk to the agent end-to-end. The natural choice is a PSTN trunk
(Twilio SIP, Telnyx, etc.) that bridges a regular phone call into
LiveKit. Two problems with that for v1:

1. **Cost / vendor.** Every PSTN provider is a paid SaaS dependency,
   and the project's "only paid service is the Anthropic API" rule
   bars it. Even free trials drift into ongoing-cost territory
   quickly.
2. **HIPAA exposure.** A SIP trunk carries PHI (voice content +
   patient phone numbers) through a third party. v1 is local-only;
   adding a covered-entity vendor needs a BAA + a security review
   we're not ready for.

But Ember still has to be reachable to demo the end-to-end loop:
referral arrives → outreach escalates to voice → agent dials → patient
talks → appointment booked.

## Decision

v1 substitutes a **browser-based test caller** for the PSTN side of
the call. A staff member opens `/voice/test-caller/[callId]` in a
second browser tab; the page fetches a LiveKit access token for that
specific call, joins the room as the patient identity, and exchanges
audio with Ember via WebRTC. The agent does not know — and does not
need to know — that the other end is a browser rather than a phone.

The provider stub stays: `OUTREACH_PROVIDER=livekit` selects
LiveKitOutreachProvider, which mints the same room + agent dispatch
regardless of how the patient eventually joins. Adding PSTN later is
an additive change in the provider layer + new infra config; the
worker, the state machine, the transcript pipeline, and the DB schema
do not move.

The README and the `/voice` page header are explicit about this scope
limit so a casual reader of the demo doesn't mistake "click to talk"
for "dialing your phone."

## Trade-offs

**Lost:** A real phone-call demo. v1 cannot show "I'm sitting at my
desk and my cell phone rings." That's a real product moment we'd
want for sales / portfolio purposes.

**Kept:** Honest local-only operation, no vendor accounts, no PHI
leaving the laptop. The state machine + transcript persistence + tenant
guards are exercised exactly the same way they would be on real
telephony.

## When to revisit

Reintroduce PSTN when any of the following land:

- A signed BAA with a SIP-trunk vendor (Twilio is the default candidate
  given LiveKit's existing integration).
- A clinic willing to pilot under a real BAA path.
- A LiveKit Cloud (or self-hosted SIP gateway) deployment that the
  rest of the stack can talk to without leaking PHI into a third
  party.

When that happens, the changes are:

- Add a SIP outbound config to LiveKit (`livekit-server` config
  reload).
- Update `LiveKitOutreachProvider.start_call` to call the SIP-create
  endpoint instead of (or in addition to) the agent dispatch.
- Decide whether the browser caller stays for testing or retires.

## References

- `services/voice-agent/ember/worker.py` — the worker is PSTN-agnostic.
- `apps/web/app/(authed)/voice/test-caller/[callId]/page.tsx` — the
  browser-side stand-in.
- `apps/api/app/services/outreach/livekit.py` — the seam where SIP
  would slot in.
