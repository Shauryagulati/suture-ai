"""Voice agent (Ember / Module 6) — STT, TTS, conversation, LiveKit glue.

Submodules:

- `stt`         — faster-whisper transcription wrapper
- `tts`         — Piper synthesis wrapper
- `agent`       — conversation state machine + LLM orchestration
- `guardrails`  — medical-advice / emergency / out-of-scope refusal patterns
- `livekit_client` — token mint + room CRUD against the LiveKit server
"""
