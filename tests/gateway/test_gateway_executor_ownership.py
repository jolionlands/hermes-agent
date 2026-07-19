import asyncio
import concurrent.futures
import threading
from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource


def _runner():
    runner = object.__new__(GatewayRunner)
    runner._worker_fence_lock = threading.Lock()
    runner._worker_fences_by_key = {}
    runner._worker_fences_by_session = {}
    return runner


@pytest.mark.asyncio
async def test_worker_fence_survives_asyncio_cancellation():
    runner = _runner()
    started = threading.Event()
    release = threading.Event()

    def _work():
        started.set()
        release.wait()

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_work)
    try:
        assert await asyncio.to_thread(started.wait, 1)
        runner._register_worker_fence(
            future, session_key="route-1", session_id="session-1"
        )

        wrapper = asyncio.wrap_future(future)
        wrapper.cancel()
        wrapper.cancel()
        await asyncio.sleep(0)

        assert runner._has_live_worker_fence(session_key="route-1")
        assert runner._has_live_worker_fence(session_id="session-1")

        release.set()
        await asyncio.to_thread(future.result, 1)
        assert not runner._has_live_worker_fence(session_key="route-1")
        assert not runner._has_live_worker_fence(session_id="session-1")
    finally:
        release.set()
        pool.shutdown(wait=True)


def test_old_worker_completion_cannot_clear_new_fence():
    runner = _runner()
    old = concurrent.futures.Future()
    new = concurrent.futures.Future()

    runner._register_worker_fence(
        old, session_key="route-1", session_id="session-1"
    )
    runner._register_worker_fence(
        new, session_key="route-1", session_id="session-1"
    )
    old.set_result(None)
    assert runner._has_live_worker_fence(session_key="route-1")

    new.set_result(None)
    assert not runner._has_live_worker_fence(session_key="route-1")


@pytest.mark.asyncio
async def test_new_refuses_to_reset_while_worker_fence_is_live():
    runner = _runner()
    future = concurrent.futures.Future()
    session_key = "agent:main:telegram:dm:42"
    session_id = "session-1"
    runner._register_worker_fence(
        future, session_key=session_key, session_id=session_id
    )
    runner._session_key_for_source = lambda source: session_key
    runner.session_store = SimpleNamespace(
        _entries={session_key: SimpleNamespace(session_id=session_id)}
    )

    source = SessionSource(
        platform=Platform.TELEGRAM, chat_id="42", chat_type="dm"
    )
    event = MessageEvent(
        text="/new", message_type=MessageType.TEXT, source=source
    )
    response = await runner._handle_reset_command(event)

    assert "was not applied" in str(getattr(response, "text", response))
    assert not future.done()
