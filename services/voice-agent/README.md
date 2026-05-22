# Ember — Suture Voice Agent

LiveKit Agents Python worker that drives Suture's outbound patient calls.

## Architecture

Three processes run in parallel during local dev:

1. **API process** (`make api`) — owns DB writes, mints LiveKit access tokens, hosts the REST + WebSocket surface.
2. **Ember worker** (`make voice-agent`) — this package. Subscribes to dispatched LiveKit rooms, runs the STT → conversation-state-machine → TTS pipeline, publishes interim transcripts to Redis pub/sub, persists encrypted final transcripts.
3. **LiveKit server** (`make voice-up`) — local SFU.

PSTN is out of scope for v1 — calls are exercised via the browser caller page at `/voice/test-caller/[callId]`.

## Run

```bash
make voice-up       # boot LiveKit server in Docker
make voice-agent    # boot Ember in foreground (auto-reloads on save)
```

First boot downloads the faster-whisper + Piper voice models into
`apps/api/data/voice-models/` (~150 MB Whisper base.en + ~60 MB Piper amy).
Subsequent boots are instant.

## Tests

State-machine + lifecycle tests live under `apps/api/tests/` so they share
the existing pytest fixtures (DB session, tenant context, mocked LLM).
Slow integration tests (real Whisper / Piper roundtrips) are gated under
`pytest -m slow` and run via `make eval-voice`.
