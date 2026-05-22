"""Redis pub/sub producer for live transcript chunks.

Mirrors the consumer wire-format in app.services.voice.transcript_bus.
The producer is owned by the voice-agent worker; the consumer is owned
by the API's WebSocket endpoint.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis


def transcript_channel(call_id: UUID) -> str:
    return f"call:{call_id}:transcript"


class TranscriptPublisher:
    """Owns a long-lived redis connection per call."""

    def __init__(self, *, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def publish_turn(self, call_id: UUID, *, role: str, text: str) -> None:
        await self._publish(
            call_id,
            {
                "type": "turn",
                "role": role,
                "text": text,
                "ts": datetime.now(UTC).isoformat(),
            },
        )

    async def publish_state(self, call_id: UUID, *, state: str) -> None:
        await self._publish(call_id, {"type": "state", "state": state})

    async def publish_end(self, call_id: UUID, *, outcome: dict[str, Any]) -> None:
        await self._publish(call_id, {"type": "end", "outcome": outcome})

    async def _publish(self, call_id: UUID, payload: dict[str, Any]) -> None:
        await self._redis.publish(transcript_channel(call_id), json.dumps(payload, default=str))

    async def aclose(self) -> None:
        await self._redis.aclose()
