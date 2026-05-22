"""Redis pub/sub consumer for live transcript chunks.

The Ember worker (Phase 8 / `services/voice-agent/`) publishes turn-by-turn
transcript chunks to the channel returned by `transcript_channel(call_id)`.
The API's WebSocket endpoint subscribes here and forwards messages to the
browser client.

Wire payload is JSON (decoded by the consumer):

    {"type": "turn",  "role": "patient"|"agent", "text": "...", "ts": "iso-utc"}
    {"type": "state", "state": "scheduling" | "confirmation" | ...}
    {"type": "end",   "outcome": {...}}

A consumer iterates until it sees `{"type": "end"}` or its caller closes
the iterator.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis


def transcript_channel(call_id: UUID) -> str:
    return f"call:{call_id}:transcript"


class TranscriptBus:
    """Subscribe to and consume the per-call transcript channel."""

    def __init__(self, *, redis_url: str) -> None:
        self._redis_url = redis_url

    async def subscribe(self, call_id: UUID) -> AsyncIterator[dict[str, Any]]:
        """Yield decoded JSON messages until the channel emits `{"type": "end"}`."""
        client = aioredis.from_url(self._redis_url, decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(transcript_channel(call_id))
        try:
            async for raw in pubsub.listen():
                if raw is None or raw.get("type") != "message":
                    continue
                payload = raw.get("data")
                if not payload:
                    continue
                try:
                    msg: dict[str, Any] = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                yield msg
                if msg.get("type") == "end":
                    return
        finally:
            await pubsub.unsubscribe(transcript_channel(call_id))
            await pubsub.aclose()  # type: ignore[no-untyped-call]
            await client.aclose()
