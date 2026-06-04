"""Entry point: `python -m ember` boots the worker.

Wires up the LiveKit Agents framework with our entrypoint. The worker
process runs forever, accepting dispatched jobs (one per Call). See
`README.md` for run instructions.
"""

from __future__ import annotations

import os

from app.config import get_settings
from livekit import agents

from ember.worker import entrypoint


def main() -> None:
    # The livekit-agents CLI reads LIVEKIT_URL / LIVEKIT_API_KEY /
    # LIVEKIT_API_SECRET from the process environment. Bridge them from our
    # config (apps/api/.env) so `make voice-agent` works without a separate
    # worker .env. setdefault so an explicit env var still wins.
    settings = get_settings()
    os.environ.setdefault("LIVEKIT_URL", settings.livekit_url)
    os.environ.setdefault("LIVEKIT_API_KEY", settings.livekit_api_key)
    os.environ.setdefault("LIVEKIT_API_SECRET", settings.livekit_api_secret)

    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="ember",
        )
    )


if __name__ == "__main__":
    main()
