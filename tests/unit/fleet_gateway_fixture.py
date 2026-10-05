"""Bounded fixture closure observations; no authority or deadline changes."""
from contextlib import contextmanager
from pathlib import Path
import sys


@contextmanager
def preserve_fixture_failure():
    primary = sys.exception()
    try:
        yield
    except BaseException as cleanup:
        if primary is not None:
            raise BaseExceptionGroup("fixture and cleanup failed", [primary, cleanup]) from None
        raise


def stop_gateway_fixture(stopped, thread, failures, *, timeout=3):
    stopped.set()
    thread.join(timeout=timeout)
    if thread.is_alive():
        frame, stack = sys._current_frames().get(thread.ident), []
        while frame is not None and len(stack) < 12:
            stack.append({"file": Path(frame.f_code.co_filename).name,
                          "function": frame.f_code.co_name, "line": frame.f_lineno})
            frame = frame.f_back
        error = TimeoutError("GATEWAY_STOP_FIXTURE_TIMEOUT")
        error.add_note(str({"timeout_seconds": timeout, "server_thread_alive": True,
                            "server_failure_count": failures.qsize(), "stack": stack}))
        raise error
    if not failures.empty():
        raise failures.get()


def close_dispatcher_fixture(agent, dispatcher, pump, *, seconds=10):
    # A proven empty retained-work set needs no new authenticated request.
    if dispatcher.has_pending_work():
        pump(agent, lambda: not dispatcher.has_pending_work(), seconds=seconds)
    dispatcher.close()
