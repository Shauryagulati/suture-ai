"""Ember — Suture's LiveKit voice agent worker.

Subscribes to dispatched rooms, drives the STT → conversation
state-machine → TTS pipeline, publishes transcript chunks to Redis
pub/sub, and persists the final encrypted transcript on call end.

Composition:

- `worker.entrypoint`        — the LiveKit Agents job handler
- `worker.run_call_pipeline` — the audio-loop orchestration (testable
                               in isolation from the LiveKit framework)
- `transcript_bus`           — Redis publisher (consumer lives in the API
                               under app.services.voice.transcript_bus)
"""
