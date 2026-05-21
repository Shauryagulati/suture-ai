"""Bridge sync Celery tasks to the async DB layer.

ContextVars do not propagate into Celery workers; tasks accept clinic_id
and user_id as kwargs, set the ContextVars at the top of the coroutine,
and reset them on exit.

When called from within a running event loop (e.g. pytest-asyncio eager
mode), asyncio.run() would raise RuntimeError. In that case we fall back
to running the coroutine in a fresh thread, which has its own event loop.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from app.utils.context import current_clinic_id, current_user_id


def run_async(
    coro_factory: Callable[[], Awaitable[Any]],
    *,
    clinic_id: UUID,
    user_id: UUID | None = None,
) -> Any:
    def _run_in_thread() -> Any:
        # Set ContextVars inside the thread — they are thread-local copies.
        cid_token = current_clinic_id.set(clinic_id)
        uid_token = current_user_id.set(user_id)
        try:
            return asyncio.run(coro_factory())
        finally:
            current_clinic_id.reset(cid_token)
            current_user_id.reset(uid_token)

    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is None:
        # Normal Celery worker path: no event loop in this thread yet.
        cid_token = current_clinic_id.set(clinic_id)
        uid_token = current_user_id.set(user_id)
        try:
            return asyncio.run(coro_factory())
        finally:
            current_clinic_id.reset(cid_token)
            current_user_id.reset(uid_token)
    else:
        # Called from within a running loop (e.g. eager mode in async tests).
        # Spin up a new thread with its own event loop to avoid the
        # "cannot be called from a running event loop" RuntimeError.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_in_thread)
            return future.result()


def run_async_unscoped(coro_factory: Callable[[], Awaitable[Any]]) -> Any:
    """Run an async coroutine without setting tenant ContextVars.

    Used by global maintenance tasks (e.g. check_overdue_tasks) that
    iterate over clinics internally and set/reset the ContextVar
    themselves per clinic.

    Mirrors `run_async`'s loop detection (tests run inside an outer loop;
    real Celery workers don't).
    """
    def _run_in_thread() -> Any:
        return asyncio.run(coro_factory())

    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is None:
        # Normal Celery worker path: no event loop in this thread yet.
        return asyncio.run(coro_factory())
    else:
        # Called from within a running loop (e.g. eager mode in async tests).
        # Spin up a new thread with its own event loop.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_in_thread)
            return future.result()
