"""Entry point: `python -m ember` boots the worker.

Wires up the LiveKit Agents framework with our entrypoint. The worker
process runs forever, accepting dispatched jobs (one per Call). See
`README.md` for run instructions.
"""

from __future__ import annotations

from livekit import agents

from ember.worker import entrypoint


def main() -> None:
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="ember",
        )
    )


if __name__ == "__main__":
    main()
