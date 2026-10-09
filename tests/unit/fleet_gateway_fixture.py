"""Bounded fixture closure observations; no authority or deadline changes."""
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
import sys
import threading


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
        error = TimeoutError("GATEWAY_STOP_FIXTURE_TIMEOUT")
        error.add_note(str({"timeout_seconds": timeout, "server_thread_alive": True,
                            "server_failure_count": failures.qsize(), "stack": gateway_thread_stack(thread)}))
        raise error
    if not failures.empty():
        raise failures.get()


def gateway_thread_stack(thread):
    frame, stack = sys._current_frames().get(thread.ident), []
    while frame is not None and len(stack) < 12:
        stack.append({"file": Path(frame.f_code.co_filename).name,
                      "function": frame.f_code.co_name, "line": frame.f_lineno})
        frame = frame.f_back
    return stack


def close_dispatcher_fixture(agent, dispatcher, pump, *, seconds=10):
    # A proven empty retained-work set needs no new authenticated request.
    if dispatcher.has_pending_work():
        pump(agent, lambda: not dispatcher.has_pending_work(), seconds=seconds)
    dispatcher.close()


def start_gateway_fixture(address, *, certificate, key_file, controller_factory, failures,
                          startup_timeout=5, stop_timeout=5):
    from fleet_writer_fixture import wait_gateway_started
    from vibemql5.fleet.transport import serve_gateway
    stopped, ready = threading.Event(), Queue()
    def run():
        try:
            serve_gateway(address, certificate=certificate, key_file=key_file,
                controller_factory=controller_factory, stop_event=stopped, started=ready.put)
        except BaseException as error:
            failures.put(error)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        bound = wait_gateway_started(ready, failures, thread, timeout=startup_timeout)
    except BaseException:
        with preserve_fixture_failure():
            stop_gateway_fixture(stopped, thread, failures, timeout=stop_timeout)
        raise
    return stopped, thread, bound
