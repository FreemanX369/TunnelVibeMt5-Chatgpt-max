"""Owned real-RPC ordering and one carried authority-burst budget."""
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
import threading
import time

import pytest

from test_tip058b_transport import fleet_policy
from vibemql5.fleet.transport import NodeRpcProxy, OutboundNode
from vibemql5.fleet.wire import WireError


@pytest.mark.parametrize("boundary", ["HEARTBEAT", "PREVIOUS_DRAIN"])
def test_actual_rpc_survives_individually_valid_slow_owner_operations(boundary):
    gate, queued = threading.Event(), threading.Event()
    outcomes, operations, services = [], [], []
    policy = fleet_policy()
    class OwnedQueue(Queue):
        def put_nowait(self, value):
            result = super().put_nowait(value)
            queued.set()
            return result
    class Client:
        device_id, route_generation = "dev_fixture", 1
        http = SimpleNamespace(policy=policy)
        phase = 1 if boundary == "HEARTBEAT" else 0
        def operation(self, name):
            if boundary == "HEARTBEAT" and name == "HEARTBEAT":
                gate.set(); assert queued.wait(2)
            start = time.monotonic()
            if self.phase: time.sleep(.6)
            operations.append((name, time.monotonic() - start))
        def heartbeat(self, session): self.operation("HEARTBEAT")
        def poll(self, session, maximum):
            self.operation("POLL"); return {"commands": []}
        def start_authorize(self, session, command, *, deadline_monotonic):
            assert agent._lock.locked() and time.monotonic() < deadline_monotonic
            services.append("START_AUTHORIZE"); return {"accepted": True}
    class Dispatcher:
        def drain(self, client, session):
            if not client.phase:
                gate.set(); assert queued.wait(2); client.phase = 1
            return []
    client = Client()
    agent = OutboundNode(client, Path("owned-fixture"), policy, domain_dispatcher=Dispatcher())
    agent._rpc = OwnedQueue(maxsize=policy.max_pending_reads)
    agent.rpc_proxy = NodeRpcProxy(client, agent._rpc)
    def request():
        assert gate.wait(2)
        try: outcomes.append(agent.rpc_proxy.start_authorize("fixture", {}))
        except WireError as error: outcomes.append(error.code)
    worker = threading.Thread(target=request)
    worker.start()
    try:
        agent.step()
        if boundary == "PREVIOUS_DRAIN": agent.step()
    finally:
        gate.set(); worker.join(3)
    assert not worker.is_alive() and outcomes == [{"accepted": True}]
    assert services == ["START_AUTHORIZE"]
    assert all(elapsed < 1 for _, elapsed in operations)


def enqueue(agent, future, *, deadline=10):
    agent._rpc.put_nowait(("START_AUTHORIZE", {"session_id": "fixture", "command": {}}, deadline, future))


def test_empty_early_checkpoint_does_not_spend_late_work_burst(tmp_path, monkeypatch):
    import vibemql5.fleet.transport as transport
    clock, events, future = [0.0], [], Future()
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    policy = fleet_policy()
    class Client:
        http = SimpleNamespace(policy=policy)
        device_id, route_generation = "dev_fixture", 1
        def heartbeat(self, session): events.append("heartbeat")
        def poll(self, *args):
            clock[0] = 1.1; enqueue(agent, future); return {"commands": []}
        def start_authorize(self, *args, deadline_monotonic):
            assert deadline_monotonic == pytest.approx(2.1)
            events.append("authority"); return {"accepted": True}
    agent = OutboundNode(Client(), tmp_path, policy)
    agent.step()
    assert future.result() == {"accepted": True} and events == ["heartbeat", "authority"]


@pytest.mark.parametrize("boundary", ["POLL", "DRAIN"])
def test_later_checkpoint_cannot_renew_elapsed_authority_burst(tmp_path, monkeypatch, boundary):
    import vibemql5.fleet.transport as transport
    clock, serviced = [0.0], []
    first, later = Future(), Future()
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    policy = replace(fleet_policy(), heartbeat_interval_ms=20)
    def late():
        clock[0] += .010; enqueue(agent, later)
    class Client:
        http = SimpleNamespace(policy=policy)
        device_id, route_generation = "dev_fixture", 1
        def heartbeat(self, session): enqueue(agent, first)
        def poll(self, *args):
            if boundary == "POLL": late()
            return {"commands": []}
        def start_authorize(self, *args, deadline_monotonic):
            assert deadline_monotonic == .02
            clock[0] += .015; serviced.append(True); return {"accepted": True}
    class Dispatcher:
        def drain(self, *args):
            if boundary == "DRAIN": late()
            return []
    agent = OutboundNode(Client(), tmp_path, policy, domain_dispatcher=Dispatcher())
    agent.step()
    assert first.result() == {"accepted": True} and serviced == [True]
    assert not later.done() and agent._rpc.qsize() == 1 and clock[0] == .025


@pytest.mark.parametrize("first_cancelled", [False, True])
def test_dequeue_cap_is_shared_across_checkpoints_including_cancelled(tmp_path, first_cancelled):
    policy = replace(fleet_policy(), max_poll_commands=2)
    first, second, later = Future(), Future(), Future()
    if first_cancelled: first.cancel()
    serviced = []
    class Client:
        http = SimpleNamespace(policy=policy)
        device_id, route_generation = "dev_fixture", 1
        def heartbeat(self, session):
            enqueue(agent, first, deadline=time.monotonic()+1)
            enqueue(agent, second, deadline=time.monotonic()+1)
        def poll(self, *args):
            enqueue(agent, later, deadline=time.monotonic()+1); return {"commands": []}
        def start_authorize(self, *args, **kwargs):
            serviced.append(True); return {"accepted": True}
    agent = OutboundNode(Client(), tmp_path, policy)
    agent.step()
    assert len(serviced) == (1 if first_cancelled else 2)
    assert first.done() and second.result() == {"accepted": True}
    assert not later.done() and agent._rpc.qsize() == 1


def test_failed_heartbeat_cannot_forward_queued_authority(tmp_path):
    policy, future, fault = fleet_policy(), Future(), WireError("ROUTE_STALE")
    events = []
    class Client:
        http = SimpleNamespace(policy=policy)
        device_id, route_generation = "dev_fixture", 1
        def heartbeat(self, session): raise fault
        def poll(self, *args): events.append("poll")
        def start_authorize(self, *args, **kwargs): events.append("authority")
    agent = OutboundNode(Client(), tmp_path, policy)
    enqueue(agent, future, deadline=time.monotonic()+1)
    with pytest.raises(WireError) as captured: agent.step()
    assert captured.value is fault and not events and not future.done()


def test_late_rpc_borrows_only_remaining_burst_and_keeps_original_error(tmp_path, monkeypatch):
    import vibemql5.fleet.transport as transport
    clock, deadlines = [0.0], []
    first, later, third = Future(), Future(), Future()
    fault = WireError("HTTP_DEADLINE_EXCEEDED")
    fault.add_note("original deadline note")
    monkeypatch.setattr(transport, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    policy = replace(fleet_policy(), heartbeat_interval_ms=20)
    class Client:
        http = SimpleNamespace(policy=policy)
        device_id, route_generation = "dev_fixture", 1
        def heartbeat(self, session): enqueue(agent, first)
        def poll(self, *args):
            clock[0] += .005; enqueue(agent, later); return {"commands": []}
        def start_authorize(self, *args, deadline_monotonic):
            deadlines.append(deadline_monotonic)
            if len(deadlines) == 1:
                clock[0] += .010; return {"accepted": True}
            assert clock[0] == .015 and deadline_monotonic == .020
            clock[0] = deadline_monotonic
            raise fault
    class Dispatcher:
        def drain(self, *args): enqueue(agent, third); return []
    agent = OutboundNode(Client(), tmp_path, policy, domain_dispatcher=Dispatcher())
    agent.step()
    assert first.result() == {"accepted": True} and later.exception() is fault
    assert fault.__notes__ == ["original deadline note"] and deadlines == [.02, .02]
    assert not third.done() and agent._rpc.qsize() == 1
