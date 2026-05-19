# Suture — Voice Agent (Ember)

> Voice agent patterns will be filled in when **Module 6** lands.
> Module 6 is sequenced **LAST** in the build and has a defined stub-fallback.
> For project-wide rules, see the repo root `CLAUDE.md`.

## Gate 0 stub

The voice agent (Ember) is a LiveKit Agents Python worker that:
- Uses Whisper.cpp / faster-whisper for STT (local, no API cost)
- Uses Piper or Coqui TTS for synthesis (local)
- Uses Claude Haiku via the Anthropic SDK for in-loop dialogue (the only paid component)
- Implements ONE conversation flow: HIPAA verification → reason for call → scheduling slot capture
- Stores the full transcript in `call_transcripts`, with structured outcome in `calls.outcome`
- Requires human approval before any appointment row in `appointments` flips to `confirmed`

**Hard scope cap for v1:** one conversation flow, one TTS voice, basic interruption handling. No multi-flow, no voice cloning, no advanced VAD tuning.

**Fallback:** if Module 6 isn't stable by week 8 of the broader build, it ships as a transcript-stub demo: a recorded interaction in the UI that exercises the same data flow without live STT/TTS. The decision will be recorded in an ADR.

This file expands when Module 6 starts.
