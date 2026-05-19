"""Pytest config for seeds/tests/.

These tests are DB-free and check that the committed corpus is well-formed.
They explicitly do NOT use the async DB fixtures from apps/api/tests/conftest.py.

When pytest is invoked from the repo root with `pytest seeds/tests/`, this
conftest's parent directory is on sys.path, so `from seeds.scripts.*`
imports resolve cleanly.
"""

from __future__ import annotations
