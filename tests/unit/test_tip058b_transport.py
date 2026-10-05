from __future__ import annotations

import ast
import copy
import hashlib
import http.client as http_client
import ipaddress
import os
import socket
import sqlite3
import ssl
import threading
import time
from dataclasses import replace
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from queue import Queue
from fleet_gateway_fixture import gateway_thread_stack, preserve_fixture_failure, stop_gateway_fixture

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID

from vibemql5.fleet.gateway_control import GatewayControlStore, Policy
from vibemql5.fleet.node_keys import create_node_key, load_node_key
from vibemql5.fleet.read_broker import ACCOUNT_FIELDS, TERMINAL_FIELDS, FleetPolicy, ReadBroker, snapshot_rows, unavailable
from vibemql5.fleet.transport import GatewayController, HttpsClient, NodeClient, OutboundNode, OwnerClient, serve_gateway
from vibemql5.fleet.wire import WireError, decode_body, encode_body, sign_request, verify_request

DEVICE = "dev_" + "a" * 32
TERMINAL = "term_" + "b" * 32
TARGET = {"schema":"fleet.target/1","device_id":DEVICE,"route_generation":1,"terminal_id":TERMINAL,"terminal_generation":1}
TOKEN = "fixture-owner-" + "a" * 40

def fleet_policy():
    return FleetPolicy(max_body_bytes=32768,max_response_bytes=65536,http_timeout_ms=1000,
        max_pending_reads=20,max_retained_results=100,max_targets=4,max_poll_commands=4,read_deadline_ms=1200,
        session_timeout_ms=30000,heartbeat_interval_ms=1000,poll_interval_ms=10,freshness_ms=5000,
        max_clock_future_ms=0,max_rows=100,max_owner_token_bytes=128,max_operation_id_bytes=64)

def control_policy():
    return Policy(singleton_wait_ms=10,sqlite_busy_timeout_ms=100,grant_ttl_ms=60000,clock_skew_ms=5000,
        nonce_retention_ms=10000,grant_secret_bytes=32,max_devices=5,max_grants=10,max_nonces=100,
        max_operations=100,max_nonce_bytes=128,max_operation_id_bytes=128)


class FixtureHttpsClient(HttpsClient):
    """Keep safe cause/timing evidence without changing transport behavior."""
    def __init__(self, *args, server_thread, failures, **kwargs):
        super().__init__(*args, **kwargs)
        self.server_thread, self.failures = server_thread, failures

    def post(self, *args, **kwargs):
        begun = time.monotonic()
        try:
            return super().post(*args, **kwargs)
        except WireError as error:
            # Never include exception text, headers, URLs, paths or bodies.
            frame = error.__context__.__traceback__ if error.__context__ is not None else None
            stack = []
            while frame is not None and len(stack) < 8:
                stack.append({"file": os.path.basename(frame.tb_frame.f_code.co_filename),
                    "function": frame.tb_frame.f_code.co_name, "line": frame.tb_lineno})
                frame = frame.tb_next
            error.add_note("TRANSPORT_HTTPS_FIXTURE " + str({
                "code": error.code, "cause_type": type(error.__context__).__name__,
                "elapsed_ms": round((time.monotonic() - begun) * 1000),
                "http_timeout_ms": self.policy.http_timeout_ms,
                "server_thread_alive": self.server_thread.is_alive(),
                "server_failure_count": self.failures.qsize(), "cause_stack": stack,
                "server_stack": gateway_thread_stack(self.server_thread)}))
            raise


class ControlPostObservation:
    """Finite route/timing facts only; original calls and errors stay intact."""
    ROUTES = {"/fleet/v1/heartbeat": "HEARTBEAT", "/fleet/v1/poll": "POLL",
              "/fleet/v1/native/start": "NATIVE_AUTHORIZE", "/fleet/v1/results": "RESULT",
              "/fleet/v1/writers/authorize": "WRITER_AUTHORIZE"}

    def __init__(self, original):
        self.original, self.rows, self.count, self.seconds = original, [], 0, 0.0

    def post(self, *args, **kwargs):
        began, outcome = time.monotonic(), "RETURNED"
        try:
            return self.original(*args, **kwargs)
        except BaseException as error:
            outcome = "WIRE_ERROR" if isinstance(error, WireError) else "OTHER_ERROR"
            raise
        finally:
            elapsed = max(0, time.monotonic() - began)
            self.count += 1; self.seconds += elapsed
            if len(self.rows) < 32:
                path = args[0] if args else kwargs.get("path")
                route = self.ROUTES.get(path, "OTHER") if type(path) is str else "OTHER"
                self.rows.append({"route": route,
                                  "elapsed_ms": round(elapsed * 1000), "outcome": outcome})

    def summary(self, elapsed):
        return {"elapsed_ms": round(elapsed * 1000), "post_count": self.count,
                "post_elapsed_ms": round(self.seconds * 1000),
                "outside_observed_posts_ms": round(max(0, elapsed - self.seconds) * 1000),
                "rows_truncated": self.count > len(self.rows), "posts": list(self.rows)}


@contextmanager
def observe_control_posts(http):
    present, prior = "post" in vars(http), vars(http).get("post")
    observation = ControlPostObservation(http.post)
    http.post = observation.post
    try:
        yield observation
    finally:
        if present: http.post = prior
        else: del http.post


@pytest.mark.parametrize("raises", [False, True])
@pytest.mark.parametrize("instance_override", [False, True])
def test_control_post_observation_preserves_original_call_error_and_restoration(raises, instance_override):
    marker = "fixture-sensitive-path-body-header-exception"
    error = WireError("HTTPS_UNAVAILABLE"); error.add_note(marker)
    calls, returned = [], object()
    class Http:
        def post(self, *args, **kwargs):
            calls.append((args, kwargs))
            if raises: raise error
            return returned
    http = Http()
    if instance_override: http.post = http.post
    before = dict(vars(http)); body, headers = {"secret": marker}, {"Authorization": marker}
    with observe_control_posts(http) as observed:
        if raises:
            with pytest.raises(WireError) as caught:
                http.post(marker, body, headers, deadline_monotonic=123)
            assert caught.value is error and error.__notes__ == [marker]
        else:
            assert http.post(marker, body, headers, deadline_monotonic=123) is returned
    assert vars(http) == before
    assert calls == [((marker, body, headers), {"deadline_monotonic": 123})]
    assert calls[0][0][1] is body and calls[0][0][2] is headers
    report = observed.summary(observed.seconds)
    assert marker not in str(report)
    assert report["posts"][0]["route"] == "OTHER"
    assert report["posts"][0]["outcome"] == ("WIRE_ERROR" if raises else "RETURNED")
    assert set(report["posts"][0]) == {"route", "elapsed_ms", "outcome"}


def test_control_post_observation_caps_rows_without_replaying_calls():
    calls = []
    observed = ControlPostObservation(lambda *args, **kwargs: calls.append(args) or {})
    for _ in range(35): observed.post("/fleet/v1/heartbeat", {})
    report = observed.summary(observed.seconds)
    assert len(calls) == report["post_count"] == 35
    assert len(report["posts"]) == 32 and report["rows_truncated"]
    assert {row["route"] for row in report["posts"]} == {"HEARTBEAT"}


def test_control_post_observation_invalid_unhashable_route_cannot_mask_original_error():
    calls, path = [], {"secret": "fixture-sensitive-invalid-route"}
    error = WireError("WIRE_INVALID"); error.add_note("ORIGINAL_INVALID_ROUTE")
    def rejected(*args, **kwargs):
        calls.append(args); raise error
    observed = ControlPostObservation(rejected)
    with pytest.raises(WireError) as caught: observed.post(path, {})
    assert caught.value is error and error.__notes__ == ["ORIGINAL_INVALID_ROUTE"]
    assert len(calls) == 1 and calls[0][0] is path
    assert observed.rows[0]["route"] == "OTHER" and "fixture-sensitive-invalid-route" not in str(observed.summary(observed.seconds))

def signed(key, body, *, nonce="1"*48, route=1, path="/fleet/v1/heartbeat", origin="https://localhost", timestamp=100):
    raw = encode_body(body,32768)
    headers=sign_request(key,device_id=DEVICE,route_generation=route,timestamp_ms=timestamp,nonce=nonce,path=path,body=raw,audience=origin)
    return raw,headers

def test_real_signature_exact_bytes_and_immutable_projection():
    key=ed25519.Ed25519PrivateKey.generate()
    raw,headers=signed(key,{"nested":{"a":[1]}})
    proof=verify_request("POST","/fleet/v1/heartbeat",headers.items(),raw,audience="https://localhost",max_body_bytes=32768)
    projected=proof.body;projected["nested"]["a"].append(2)
    assert proof.body == {"nested":{"a":[1]}}
    with pytest.raises(WireError,match="WIRE_SIGNATURE_INVALID"):
        verify_request("POST","/fleet/v1/heartbeat",headers.items(),raw+b" ",audience="https://localhost",max_body_bytes=32768)
    with pytest.raises(WireError,match="WIRE_SIGNATURE_INVALID"):
        verify_request("POST","/fleet/v1/heartbeat",headers.items(),raw,audience="https://other.example",max_body_bytes=32768)

@pytest.mark.parametrize("raw",[b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1e999}',b'[]',b'\xff',b'{"a":"\\ud800"}'])
def test_strict_json(raw):
    with pytest.raises(WireError):
        decode_body(raw,128)

@pytest.mark.parametrize("change",[{"x-vibe-route":"01"},{"x-vibe-time":"true"},{"x-vibe-nonce":"a\nb"},{"x-vibe-key":"A"*64}])
def test_strict_headers(change):
    key=ed25519.Ed25519PrivateKey.generate();raw,headers=signed(key,{"schema":"x"});headers.update(change)
    with pytest.raises(WireError):
        verify_request("POST","/fleet/v1/heartbeat",headers.items(),raw,audience="https://localhost",max_body_bytes=128)

def test_duplicate_header_rejected():
    key=ed25519.Ed25519PrivateKey.generate();raw,headers=signed(key,{"schema":"x"})
    with pytest.raises(WireError):
        verify_request("POST","/fleet/v1/heartbeat",list(headers.items())+[("X-Vibe-Time","100")],raw,audience="https://localhost",max_body_bytes=128)

def test_policy_no_booleans_and_mechanism_ceiling():
    with pytest.raises(WireError):replace(fleet_policy(),max_targets=True)
    with pytest.raises(WireError):replace(fleet_policy(),max_targets=1000)

def test_private_key_explicit_exclusive_restrictive(tmp_path):
    directory=tmp_path/"secrets";directory.mkdir(mode=0o700)
    path=directory/"node-key.pem"
    result=create_node_key(path)
    assert load_node_key(path).public_key().public_bytes_raw().hex() == result["public_key"]
    assert set(result)=={"schema","public_key"}
    with pytest.raises(WireError,match="NODE_KEY_EXISTS"):create_node_key(path)
    if __import__('os').name != "nt":
        path.chmod(0o644)
        with pytest.raises(WireError):load_node_key(path)

def test_windows_owner_and_protected_acl_contract():
    from vibemql5.fleet.node_keys import _windows_validate_acl
    sid="S-1-5-21-100-200-300-1001"
    aces=[(0,0,0x001F01FF,"S-1-5-18"),(0,0,0x001F01FF,sid)]
    _windows_validate_acl(0x1004,aces,sid,sid)
    _windows_validate_acl(0x1404,list(reversed(aces)),sid,"S-1-5-18")
    _windows_validate_acl(0x1004,[aces[0]],"S-1-5-18","S-1-5-18")
    with pytest.raises(WireError):_windows_validate_acl(0x1004,aces,sid,"S-1-5-32-544")
    with pytest.raises(WireError):_windows_validate_acl(0x1004,aces+[(0,0,0x00120089,"S-1-1-0")],sid,sid)
    with pytest.raises(WireError):_windows_validate_acl(4,aces,sid,sid)
    with pytest.raises(WireError):_windows_validate_acl(0x1004,[aces[0],(0,0x10,0x001F01FF,sid)],sid,sid)
    with pytest.raises(WireError):_windows_validate_acl(0x1004,[aces[0],(0,0,0x00120089,sid)],sid,sid)

@pytest.mark.skipif(os.name!="nt",reason="Actual retained-handle numeric ACL fixture requires Windows")
def test_windows_private_acl_roundtrip_reports_public_semantics(tmp_path):
    from vibemql5.fleet.node_keys import _windows_acl,_windows_create,_windows_validate_acl
    directory=tmp_path/"secrets";directory.mkdir();path=directory/"public-fixture.txt"
    fd=_windows_create(path)
    try:
        evidence=_windows_acl(fd,set_restrictive=True)
        _windows_validate_acl(evidence["control"],evidence["aces"],evidence["current_sid"],evidence["owner_sid"])
        assert _windows_acl(fd)==evidence,evidence
        print("WINDOWS_ACL_PUBLIC_EVIDENCE",evidence)
    finally:os.close(fd)

@pytest.mark.skipif(os.name!="nt",reason="Actual retained-handle Windows ownership fixture requires Windows")
def test_windows_private_key_foreign_owner_denied_on_retained_handle(tmp_path):
    import ctypes as C
    from ctypes import wintypes as W
    directory=tmp_path/"secrets";directory.mkdir()
    path=directory/"foreign-owner.pem";create_node_key(path)
    kernel=C.WinDLL("kernel32",use_last_error=True);adv=C.WinDLL("advapi32",use_last_error=True)
    pointer=C.c_void_p
    kernel.CreateFileW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,pointer,W.DWORD,W.DWORD,W.HANDLE]
    kernel.CreateFileW.restype=W.HANDLE
    kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
    kernel.LocalFree.argtypes=[pointer];kernel.LocalFree.restype=pointer
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[W.LPCWSTR,W.DWORD,C.POINTER(pointer),pointer]
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype=W.BOOL
    adv.GetSecurityDescriptorOwner.argtypes=[pointer,C.POINTER(pointer),C.POINTER(W.BOOL)]
    adv.GetSecurityDescriptorOwner.restype=W.BOOL
    adv.SetSecurityInfo.argtypes=[W.HANDLE,C.c_int,W.DWORD,pointer,pointer,pointer,pointer]
    adv.SetSecurityInfo.restype=W.DWORD
    descriptor=pointer();owner=pointer();defaulted=W.BOOL()
    assert adv.ConvertStringSecurityDescriptorToSecurityDescriptorW("O:BA",1,C.byref(descriptor),None)
    handle=kernel.CreateFileW(str(path),0x00080000,0,None,3,0x00200080,None)
    try:
        if handle==C.c_void_p(-1).value:
            pytest.skip("Fixture token cannot open temporary key with WRITE_OWNER")
        assert adv.GetSecurityDescriptorOwner(descriptor,C.byref(owner),C.byref(defaulted))
        error=adv.SetSecurityInfo(handle,1,1,owner,None,None,None)
        if error:
            pytest.skip("Normal fixture token cannot assign Administrators as foreign owner; no privilege is enabled")
    finally:
        if handle!=C.c_void_p(-1).value:kernel.CloseHandle(handle)
        kernel.LocalFree(descriptor)
    with pytest.raises(WireError,match="NODE_KEY_STORAGE_INVALID"):load_node_key(path)

@pytest.mark.skipif(os.name!="nt",reason="Actual protected staging-directory handle fixture requires Windows")
def test_windows_staging_directory_cannot_be_renamed_while_held(tmp_path):
    from vibemql5.fleet.node_keys import _windows_hold_private_directory
    directory=tmp_path/"secrets";directory.mkdir()
    staging=directory/"staging";staging.mkdir()
    replacement=directory/"replacement"
    fd=_windows_hold_private_directory(staging)
    try:
        with pytest.raises(OSError):staging.rename(replacement)
        assert staging.is_dir() and not replacement.exists()
        create_node_key(staging/"fixture.pem")
        assert load_node_key(staging/"fixture.pem") is not None
    finally:os.close(fd)
    staging.rename(replacement)
    assert replacement.is_dir()

@pytest.fixture
def tls_files(tmp_path):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"Fleet fixture CA")])
    now=datetime.now(timezone.utc)
    ca=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(key,hashes.SHA256()))
    server_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    leaf=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"localhost")]))
        .issuer_name(name).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),critical=False).sign(key,hashes.SHA256()))
    ca_path=tmp_path/"ca.pem";certificate=tmp_path/"server.pem";private=tmp_path/"server-key.pem"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM));certificate.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(server_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    return ca_path,certificate,private

@pytest.fixture
def service(tmp_path,tls_files):
    ca,certificate,private=tls_files
    stopping=threading.Event();ready=Queue();failures=Queue()
    def factory(address):
        store=GatewayControlStore.initialize(tmp_path/"control.sqlite",policy=control_policy())
        origin="https://127.0.0.1:"+str(address[1])
        return GatewayController(store,fleet_policy(),audience=origin,owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),broker=ReadBroker.for_synthetic_tests(fleet_policy()))
    def run():
        try:serve_gateway(("127.0.0.1",0),certificate=certificate,key_file=private,controller_factory=factory,stop_event=stopping,started=ready.put)
        except BaseException as exc:failures.put(exc)
    thread=threading.Thread(target=run,daemon=True);thread.start();address=ready.get(timeout=5)
    http=FixtureHttpsClient("https://127.0.0.1:"+str(address[1]),fleet_policy(),cafile=str(ca),
        server_thread=thread,failures=failures)
    yield http,OwnerClient(http,TOKEN),address,stopping,thread
    stopping.set();thread.join(timeout=3)
    assert not thread.is_alive()
    if not failures.empty():raise failures.get()

def enrolled(service):
    http,owner,*_=service
    key=ed25519.Ed25519PrivateKey.generate()
    grant=owner.admin("grant",{"device_id":DEVICE,"public_key":key.public_key().public_bytes_raw().hex(),"operation_id":"grant-a","expected_revision":1,"expected_route_generation":None})
    node=NodeClient(http,key,DEVICE,0)
    paired=node.pair(grant_id=grant["receipt"]["grant_id"],secret=grant["secret"],operation_id="pair-a",expected_revision=2)
    return node,grant,paired

def test_actual_https_pair_retry_replay_sessions_and_no_secrets(service):
    http,owner,*_=service;node,grant,paired=enrolled(service)
    retried=node.pair(grant_id=grant["receipt"]["grant_id"],secret=grant["secret"],operation_id="pair-a",expected_revision=2)
    assert retried["receipt"]==paired["receipt"] and retried["idempotent_recovered"]
    assert "secret" not in retried
    node.heartbeat("session1")
    with pytest.raises(WireError,match="NODE_SESSION_CONFLICT"):node.heartbeat("session2")
    raw,headers=signed(node.key,{"schema":"fleet.heartbeat/1","session_id":"session1"},origin=http.origin,timestamp=int(time.time()*1000))
    assert http.post("/fleet/v1/heartbeat",decode_body(raw,32768),headers)["transport"]=="ONLINE"
    with pytest.raises(WireError,match="CONTROL_REPLAY"):http.post("/fleet/v1/heartbeat",decode_body(raw,32768),headers)
    with pytest.raises(WireError,match="OWNER_UNAUTHORIZED"):
        OwnerClient(http,"x"*40).read("get_account_snapshot",TARGET,"badowner")


@pytest.mark.parametrize("cause", [TimeoutError, ssl.SSLCertVerificationError, http_client.BadStatusLine])
def test_transport_fixture_preserves_error_cause_without_retry_or_sensitive_text(service, monkeypatch, cause):
    http, owner, *_ = service
    attempts = []
    fault = cause("fixture-sensitive-exception-text")
    request = {"device_id": DEVICE,
        "public_key": ed25519.Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex(),
        "operation_id": "fault-before-send", "expected_revision": 1, "expected_route_generation": None}
    def fail_connect(connection):
        attempts.append("connect")
        raise fault
    with monkeypatch.context() as fixture:
        fixture.setattr(http_client.HTTPSConnection, "connect", fail_connect)
        with pytest.raises(WireError, match="HTTPS_UNAVAILABLE") as caught:
            owner.admin("grant", request)
    assert caught.value.__context__ is fault and caught.value.__suppress_context__
    note = caught.value.__notes__[0]
    diagnostic = ast.literal_eval(note.removeprefix("TRANSPORT_HTTPS_FIXTURE "))
    assert cause.__name__ in note and "'http_timeout_ms': 1000" in note
    assert TOKEN not in note and request["public_key"] not in note and str(fault) not in note
    assert 1 <= len(diagnostic["cause_stack"]) <= 8
    assert diagnostic["cause_stack"][-1]["function"] == "fail_connect"
    assert all("/" not in frame["file"] and "\\" not in frame["file"] for frame in diagnostic["cause_stack"])
    assert attempts == ["connect"]
    receipt = owner.admin("grant", {**request, "operation_id": "after-controlled-fault"})
    assert receipt["receipt"]["revision"] == 2
    print(note)


def test_transport_fixture_keeps_owner_denial_and_safe_notes(service):
    http, *_ = service
    with pytest.raises(WireError, match="OWNER_UNAUTHORIZED") as caught:
        OwnerClient(http, "x" * 40).read_status("fixture-sensitive-command")
    note = caught.value.__notes__[0]
    assert "OWNER_UNAUTHORIZED" in note and "fixture-sensitive-command" not in note and "x" * 40 not in note
    print(note)


def test_transport_fixture_timeout_can_follow_committed_grant_without_replay(service, monkeypatch):
    http, owner, *_ = service
    original = GatewayController.handle
    committed, release = threading.Event(), threading.Event()
    calls = []
    request = {"device_id": DEVICE,
        "public_key": ed25519.Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex(),
        "operation_id": "held-after-commit", "expected_revision": 1, "expected_route_generation": None}
    def hold_response(controller, method, path, headers, body):
        result = original(controller, method, path, headers, body)
        if path == "/fleet/v1/admin/grant":
            calls.append(result["receipt"]["revision"])
            committed.set()
            release.wait(timeout=3)
        return result
    with monkeypatch.context() as fixture:
        fixture.setattr(GatewayController, "handle", hold_response)
        try:
            with pytest.raises(WireError, match="HTTPS_UNAVAILABLE") as caught:
                owner.admin("grant", request)
            assert committed.is_set() and calls == [2]
            assert isinstance(caught.value.__context__, TimeoutError)
            note = caught.value.__notes__[0]
            diagnostic = ast.literal_eval(note.removeprefix("TRANSPORT_HTTPS_FIXTURE "))
            assert "TimeoutError" in note and "'http_timeout_ms': 1000" in note
            assert 1 <= len(diagnostic["cause_stack"]) <= 8
            assert any(frame["function"] == "getresponse" for frame in diagnostic["cause_stack"])
            assert all("/" not in frame["file"] and "\\" not in frame["file"] for frame in diagnostic["cause_stack"])
            assert 1 <= len(diagnostic["server_stack"]) <= 12
            assert any(frame["function"] == "hold_response" for frame in diagnostic["server_stack"])
            assert all("/" not in frame["file"] and "\\" not in frame["file"] for frame in diagnostic["server_stack"])
            assert TOKEN not in note and request["public_key"] not in note
            print(note)
        finally:
            release.set()
    # A failed HTTPS receipt cannot establish absence of the persisted effect.
    with pytest.raises(WireError, match="CONTROL_REVISION_CONFLICT"):
        owner.admin("grant", {**request, "operation_id": "confirm-retained-revision"})
    assert calls == [2]


def test_transport_timeout_during_pending_grant_commit_retains_one_durable_effect(service, tmp_path, monkeypatch):
    http, owner, _, stopped, thread = service
    entered, release, committed, handler_finished = (threading.Event() for _ in range(4))
    facts, owners, calls = {"grant_delegations": 0}, [], []
    original = GatewayController.handle
    request = {"device_id": DEVICE,
        "public_key": ed25519.Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex(),
        "operation_id": "pending-commit-grant", "expected_revision": 1, "expected_route_generation": None}
    class PendingGrantCommit:
        def __init__(self, connection, path):
            self.connection, self.path, self.calls = connection, path, 0
        def __getattr__(self, name): return getattr(self.connection, name)
        def commit(self):
            self.calls += 1
            if self.calls != 2:
                return self.connection.commit()
            # The first actual commit retained observed wall time. Hold the
            # grant COMMIT call before delegating to this same FULL/WAL handle.
            facts.update(synchronous=self.connection.execute("PRAGMA synchronous").fetchone()[0],
                journal_mode=self.connection.execute("PRAGMA journal_mode").fetchone()[0],
                transaction_pending=self.connection.in_transaction,
                pending_revision=self.connection.execute("SELECT revision FROM control").fetchone()[0])
            reader = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True,
                timeout=control_policy().sqlite_busy_timeout_ms / 1000, isolation_level=None)
            try:
                revision, wall = reader.execute("SELECT revision,last_wall_ms FROM control").fetchone()
                facts.update(committed_revision_before=revision,
                    wall_persisted=wall > 0 and wall == self.connection.execute("SELECT last_wall_ms FROM control").fetchone()[0],
                    committed_grants_before=reader.execute("SELECT count(*) FROM grants").fetchone()[0],
                    committed_operations_before=reader.execute("SELECT count(*) FROM operations").fetchone()[0])
            finally: reader.close()
            entered.set()
            assert release.wait(timeout=3)
            facts["grant_delegations"] += 1
            result = self.connection.commit()
            facts["transaction_pending_after"] = self.connection.in_transaction
            committed.set()
            return result
    def hold_actual_commit(controller, method, path, headers, body):
        if path != "/fleet/v1/admin/grant":
            return original(controller, method, path, headers, body)
        calls.append("grant"); owners.append(controller.store)
        connection = controller.store._db
        assert type(connection) is sqlite3.Connection
        facts["owner_thread_matches"] = threading.get_ident() == controller._owner_thread
        proxy = PendingGrantCommit(connection, controller.store.path)
        controller.store._db = proxy
        try:
            return original(controller, method, path, headers, body)
        finally:
            facts["same_connection"] = controller.store._db is proxy and proxy.connection is connection
            facts["commit_calls"] = proxy.calls
            if controller.store._db is proxy: controller.store._db = connection
            handler_finished.set()
    with monkeypatch.context() as fixture:
        fixture.setattr(GatewayController, "handle", hold_actual_commit)
        try:
            with pytest.raises(WireError, match="HTTPS_UNAVAILABLE") as caught:
                owner.admin("grant", request)
            assert entered.is_set() and not release.is_set() and not committed.is_set()
            assert facts["grant_delegations"] == 0 and facts["transaction_pending"]
            assert facts["synchronous"] == 2 and facts["journal_mode"] == "wal"
            assert facts["committed_revision_before"] == 1 and facts["pending_revision"] == 2
            assert facts["wall_persisted"] and facts["committed_grants_before"] == facts["committed_operations_before"] == 0
            assert isinstance(caught.value.__context__, TimeoutError)
            diagnostic = ast.literal_eval(caught.value.__notes__[0].removeprefix("TRANSPORT_HTTPS_FIXTURE "))
            assert diagnostic["http_timeout_ms"] == 1000 and diagnostic["server_thread_alive"]
            assert any(frame["file"] == "test_tip058b_transport.py" and frame["function"] == "commit" for frame in diagnostic["server_stack"])
            caught.value.add_note("PENDING_COMMIT_FIXTURE " + str(dict(facts)))
            assert TOKEN not in str(caught.value.__notes__) and request["public_key"] not in str(caught.value.__notes__)
            print(caught.value.__notes__[-1])
        finally:
            with preserve_fixture_failure():
                release.set()
                stop_gateway_fixture(stopped, thread, http.failures)
    assert handler_finished.is_set() and committed.is_set() and not thread.is_alive()
    assert facts["grant_delegations"] == 1 and facts["commit_calls"] == 2 and facts["same_connection"]
    assert facts["owner_thread_matches"] and not facts["transaction_pending_after"]
    assert calls == ["grant"] and len(owners) == 1 and owners[0]._db is None
    # Reopen only after the real event owner closed the actual database/lock.
    with GatewayControlStore.open_existing(tmp_path / "control.sqlite", policy=control_policy()) as reopened:
        state = reopened.snapshot()
        assert state["revision"] == 2 and len(state["grants"]) == len(state["operations"]) == 1
        assert not state["devices"] and not state["nonces"] and not state["grants"][0]["consumed"]
        assert state["operations"][0]["receipt"]["operation"] == "ISSUE_GRANT"
    print("CONTROLLED_PENDING_GRANT_COMMIT_EXACTLY_ONE_DURABLE_EFFECT", facts)

def positive(command):
    result=unavailable(command,"fixture")
    terminal={key:None for key in TERMINAL_FIELDS};terminal.update(alias="FIXTURE",build=1,connected=True,trade_allowed=False)
    account={key:None for key in ACCOUNT_FIELDS};account.update(status="CONNECTED",present=True,login_masked="***1234",currency="USD",balance=100.0)
    result.update(status="SUCCEEDED",reason_code=None,resolved_target=command["target"],source="SYNTHETIC_TEST",
        observed_at_utc=datetime.now(timezone.utc).isoformat(),terminal=terminal,account=account,
        observed_binding={"executable":"/fixture/terminal","data_root":"/fixture/data","alias":"FIXTURE","process":{"pid":12,"creation":"123","image":"/fixture/terminal"}},
        cleanup={"status":"PROVEN","reason_code":None},ownership={"status":"CLOSED"})
    return result

def test_https_read_attribution_once_lost_ack_and_partial_snapshot(service,tmp_path):
    http,owner,*_=service;node,_,_=enrolled(service);calls=[]
    agent=OutboundNode(node,tmp_path,fleet_policy(),synthetic_read_adapter=lambda c:(calls.append(c["command_id"]) or positive(c)))
    queued=owner.read("get_account_snapshot",TARGET,"read1")
    original=node.result
    def lost(session,command,result):
        response=original(session,command,result)
        raise WireError("fixture_lost_ack")
    node.result=lost
    with pytest.raises(WireError,match="fixture_lost_ack"):agent.step()
    node.result=original
    assert owner.read_status(queued["command_id"])["result"]["source"]=="SYNTHETIC_TEST"
    agent.step()
    assert len(calls)==1
    result=owner.read_status(queued["command_id"])["result"]
    other={**TARGET,"terminal_id":"term_"+"c"*32}
    partial=snapshot_rows([TARGET,other],[result,unavailable({"operation":"get_account_snapshot","target":other},"OFFLINE")],now_ms=int(time.time()*1000),freshness_ms=5000)
    assert partial["coverage"]=={"requested":2,"succeeded":1,"failed":1}
    assert partial["rows"][1]["account"] is None and "total" not in partial

def test_tls_hostname_and_ca_are_verified(service,monkeypatch):
    http,owner,address,*_=service
    resolve=socket.getaddrinfo
    # Route this mismatched IP to the genuine local TLS fixture; verification
    # still receives the original127.0.0.2 name absent from its certificate.
    with monkeypatch.context() as fixture:
        fixture.setattr(socket,"getaddrinfo",lambda host,*args,**kwargs:resolve("127.0.0.1" if host=="127.0.0.2" else host,*args,**kwargs))
        with pytest.raises(WireError,match="HTTPS_UNAVAILABLE"):
            HttpsClient("https://127.0.0.2:"+str(address[1]),fleet_policy(),ssl_context=http.context).post("/fleet/v1/read-status",{"schema":"fleet.read-status-request/1","command_id":"read_x"},{"Authorization":"Bearer "+TOKEN})
    with pytest.raises(WireError,match="HTTPS_UNAVAILABLE"):
        HttpsClient(http.origin,fleet_policy()).post("/fleet/v1/read-status",{"schema":"fleet.read-status-request/1","command_id":"read_x"},{"Authorization":"Bearer "+TOKEN})
    context=ssl._create_unverified_context()
    with pytest.raises(WireError,match="TLS_VERIFICATION_REQUIRED"):HttpsClient(http.origin,fleet_policy(),ssl_context=context)

def test_delayed_wrong_family_cannot_send_expired_authority_and_numeric_fixture_needs_no_extra_budget(service,monkeypatch):
    http,owner,address,*_=service
    resolve,connect,clock=socket.getaddrinfo,socket.socket.connect,time.monotonic
    elapsed=[0.0];attempts=[]
    def dual(host,port,*args,**kwargs):
        if host=="localhost":
            return [(socket.AF_INET6,socket.SOCK_STREAM,6,"",("::1",port,0,0)),
                (socket.AF_INET,socket.SOCK_STREAM,6,"",("127.0.0.1",port))]
        return resolve(host,port,*args,**kwargs)
    def delayed(protected,destination):
        attempts.append(protected.family)
        if protected.family==socket.AF_INET6:
            elapsed[0]+=http.policy.http_timeout_ms/1000+.001
            raise ConnectionRefusedError("fixture delayed IPv6 refusal")
        return connect(protected,destination)
    with monkeypatch.context() as fixture:
        fixture.setattr(socket,"getaddrinfo",dual);fixture.setattr(socket.socket,"connect",delayed)
        fixture.setattr(time,"monotonic",lambda:clock()+elapsed[0])
        old=OwnerClient(HttpsClient("https://localhost:"+str(address[1]),fleet_policy(),ssl_context=http.context),TOKEN)
        request={"device_id":DEVICE,"public_key":ed25519.Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex(),
            "operation_id":"expired-before-send","expected_revision":1,"expected_route_generation":None}
        with pytest.raises(WireError,match="HTTP_DEADLINE_EXCEEDED"):old.admin("grant",request)
    assert attempts==[socket.AF_INET6,socket.AF_INET]
    # Revision1 proves the late connection sent no prior owner mutation. The
    # same policy budget now succeeds using exact fixture IP and verified SAN.
    receipt=owner.admin("grant",{**request,"operation_id":"numeric-fixture"})
    assert receipt["receipt"]["revision"]==2 and http.policy.http_timeout_ms==1000

def test_slow_fragmented_headers_cannot_renew_total_budget(service):
    http,owner,address,*_=service
    protected=http.context.wrap_socket(socket.create_connection(address,timeout=2),server_hostname="localhost")
    protected.sendall(b"POST /fleet/v1/heartbeat HTTP/1.1\r\nHost: localhost\r\nX-Slow: ")
    start=time.monotonic()
    while time.monotonic()-start < 1.4:
        try:protected.sendall(b"a")
        except OSError:break
        time.sleep(.1)
    protected.settimeout(.5)
    try:assert protected.recv(1)==b""
    except (ssl.SSLError,OSError):pass
    protected.close()
    assert time.monotonic()-start < 2
    with pytest.raises(WireError,match="READ_INTERRUPTED"):owner.read_status("read_unknown")

def test_lost_result_before_commit_repoll_uses_exact_cached_observation(service,tmp_path):
    http,owner,*_=service;node,_,_=enrolled(service);calls=[]
    agent=OutboundNode(node,tmp_path,fleet_policy(),synthetic_read_adapter=lambda c:(calls.append(c["command_id"]) or positive(c)))
    queued=owner.read("get_account_snapshot",TARGET,"read-before-drop")
    original=node.result
    node.result=lambda *args:(_ for _ in ()).throw(WireError("fixture_before_commit"))
    with pytest.raises(WireError):agent.step()
    assert owner.read_status(queued["command_id"])["status"]=="PENDING"
    node.result=original
    agent.step()
    assert len(calls)==1 and owner.read_status(queued["command_id"])["status"]=="SUCCEEDED"

def test_default_node_adapter_no_sdk_or_fallback(service,tmp_path,monkeypatch):
    import sys
    http,owner,*_=service;node,_,_=enrolled(service)
    monkeypatch.setitem(sys.modules,"MetaTrader5",None)
    queued=owner.read("get_account_snapshot",TARGET,"default-denied")
    assert OutboundNode(node,tmp_path,fleet_policy()).step()["sdk_status"]=="UNQUALIFIED"
    result=owner.read_status(queued["command_id"])["result"]
    assert result["status"]=="FAILED" and result["requested_target"]==TARGET and result["account"] is None
    assert result["reason_code"]=="IDENTITY_UNENROLLED"

def test_source_owner_does_not_start_gateway_per_client(service):
    http,owner,*_=service
    assert not hasattr(http,"store") and not hasattr(owner,"store")
    with pytest.raises(WireError,match="READ_INTERRUPTED"):owner.read_status("read_not_there")

def test_sealed_read_admission_requires_tls_delivery_and_once_only(service):
    from vibemql5.fleet.transport import NodeReadAdmission
    http,owner,*_=service;node,_,_=enrolled(service)
    node.heartbeat("qualified-session")
    queued=owner.read("get_account_snapshot",TARGET,"sealed-read")
    commands=node.poll("qualified-session",1)["commands"]
    command=commands[0]
    with pytest.raises(WireError,match="READ_ADMISSION_UNVERIFIED"):
        NodeReadAdmission(node,"qualified-session",command,_seal=object())
    proof=node.admit_read("qualified-session",command)
    proof.claim(command)
    with pytest.raises(WireError,match="READ_ADMISSION_USED"):proof.claim(command)
    with pytest.raises(WireError,match="READ_ADMISSION_USED"):node.admit_read("qualified-session",command)
    changed=copy.deepcopy(command);changed["target"]["terminal_generation"]=2
    with pytest.raises(WireError,match="READ_ADMISSION_MISMATCH"):proof.assert_current(changed)

def test_recovery_evidence_reverifies_exact_signed_envelope():
    import base64
    key=ed25519.Ed25519PrivateKey.generate()
    raw,headers=signed(key,{"schema":"fixture.recovery/1"},path="/fleet/v1/reconcile")
    proof=verify_request("POST","/fleet/v1/reconcile",headers.items(),raw,audience="https://localhost",max_body_bytes=32768)
    evidence=proof.recovery_evidence()
    replay=verify_request(evidence["method"],evidence["path"],evidence["header_pairs"],base64.b64decode(evidence["body_base64"]),audience=evidence["audience"],max_body_bytes=32768)
    assert replay.request_sha256==proof.request_sha256
    raw,headers=signed(key,{"schema":"fixture"})
    ordinary=verify_request("POST","/fleet/v1/heartbeat",headers.items(),raw,audience="https://localhost",max_body_bytes=32768)
    with pytest.raises(WireError,match="WIRE_RECOVERY_ONLY"):ordinary.recovery_evidence()

def test_read_admission_completed_and_revoked_are_rechecked(service):
    http,owner,*_=service;node,_,_=enrolled(service)
    node.heartbeat("admission-session")
    owner.read("get_account_snapshot",TARGET,"admission-complete")
    command=node.poll("admission-session",1)["commands"][0]
    admission=node.admit_read("admission-session",command)
    node.result("admission-session",command,positive(command))
    with pytest.raises(WireError,match="READ_ADMISSION_CLOSED"):admission.assert_current(command)
    owner.read("get_account_snapshot",TARGET,"admission-revoke")
    command=node.poll("admission-session",1)["commands"][0]
    admission=node.admit_read("admission-session",command)
    last=node.heartbeat("admission-session")
    owner.admin("revoke",{"device_id":DEVICE,"expected_route_generation":1,
        "expected_revision":last["control_head"]["revision"],"operation_id":"revoke-admission"})
    with pytest.raises(WireError,match="CONTROL_ROUTE_MISMATCH"):admission.assert_current(command)

def test_node_control_heartbeat_continues_while_native_fixture_is_blocked(tmp_path):
    entered=threading.Event();release=threading.Event();authorized=threading.Event();owner=threading.get_ident()
    class FakeHttp:
        policy=fleet_policy()
    class FakeClient:
        http=FakeHttp();device_id=DEVICE;route_generation=1
        def __init__(self):self.heartbeats=0;self.auth_threads=[]
        def heartbeat(self,session):
            assert threading.get_ident()==owner
            self.heartbeats+=1
        def poll(self,session,limit):return {"commands":[{"kind":"NATIVE","command_id":"fixture-blocked"}]}
        def start_authorize(self,session,command,deadline_monotonic=None):
            self.auth_threads.append(threading.get_ident())
            return {"fixture_only":True}
    class AsyncFixture:
        thread=None
        def bind_control_transport(self,proxy):self.proxy=proxy
        def dispatch_async(self,command,proxy,session):
            if self.thread is None:
                def effect():
                    assert proxy.start_authorize(session,{"fixture_only":True})=={"fixture_only":True}
                    authorized.set();entered.set();release.wait(timeout=3)
                self.thread=threading.Thread(target=effect);self.thread.start()
            return {"status":"FIXTURE_QUEUED"}
        def drain(self,client,session):return []
    client=FakeClient();dispatcher=AsyncFixture();agent=OutboundNode(client,tmp_path,fleet_policy(),domain_dispatcher=dispatcher)
    try:
        agent.step()
        for _ in range(10):
            agent.step()
            if authorized.wait(timeout=.01):break
        assert entered.is_set() and client.auth_threads==[owner]
        before=client.heartbeats
        agent.step();agent.step()
        assert client.heartbeats==before+2 and dispatcher.thread.is_alive()
    finally:
        release.set()
        if dispatcher.thread:dispatcher.thread.join(timeout=3)

def test_expired_worker_rpc_does_not_later_issue_authority(tmp_path):
    from queue import Queue
    from vibemql5.fleet.transport import NodeRpcProxy
    class Http:policy=replace(fleet_policy(),http_timeout_ms=20)
    class Client:
        http=Http();device_id=DEVICE;route_generation=1
        def __init__(self):self.calls=[]
        def start_authorize(self,*args,**kwargs):self.calls.append("issued")
    client=Client();agent=OutboundNode(client,tmp_path,Http.policy)
    errors=[]
    def request():
        try:agent.rpc_proxy.start_authorize("session",{"fixture":True})
        except WireError as exc:errors.append(exc.code)
    thread=threading.Thread(target=request);thread.start();thread.join(timeout=.5)
    assert errors==["NODE_RPC_DEADLINE_EXCEEDED"]
    agent._service_rpc()
    assert client.calls==[]

def test_key_path_cannot_escape_secrets_with_parent_segments(tmp_path):
    (tmp_path/"secrets").mkdir(mode=0o700);(tmp_path/"tracked").mkdir(mode=0o700)
    with pytest.raises(WireError,match="NODE_KEY_STORAGE_INVALID"):
        create_node_key(tmp_path/"secrets"/".."/"tracked"/"private.pem")
    assert not (tmp_path/"tracked"/"private.pem").exists()

def test_https_audience_is_read_only(service):
    http,*_=service
    with pytest.raises(AttributeError):http.origin="https://other.example"

@pytest.mark.parametrize("origin",["https://localhost:0","https://host name","https://bad_label","https://-bad.example","https://[v1.host]"])
def test_https_origin_requires_concrete_canonical_host_and_port(origin):
    from vibemql5.fleet.wire import https_origin
    with pytest.raises(WireError,match="WIRE_ORIGIN_INVALID"):https_origin(origin)

def test_native_authority_projection_binds_event_and_predecessor():
    class Http:
        policy=fleet_policy()
    client=NodeClient(Http(),None,DEVICE,1)
    captured=[]
    client._post=lambda path,value,**kwargs:(captured.append((path,value,kwargs)) or {"body":{"fixture":True},"signature":"0"*128,"control_head":{}})
    predecessor={"schema":"fleet.native-effect-completion/1","grant_sha256":"1"*64,
        "phase":"reserve","event":"phase_admission","sequence":1,"challenge":"2"*32,
        "outcome":"COMPLETED","evidence":{"kind":"fixture","sha256":"3"*64}}
    command={"global_job_id":"job_fixture","node_operation_id":"op_fixture","request_sha256":"4"*64,
        "target":TARGET,"local_job_id":"local_fixture","authorization_phase":"deploy",
        "authorization_sequence":2,"authorization_challenge":"5"*32,
        "authorization_event":"before_deploy","authorization_predecessor":predecessor,"authorization_process_sha256":None}
    result=client.start_authorize("session",command,deadline_monotonic=123)
    assert result=={"body":{"fixture":True},"signature":"0"*128}
    path,body,kwargs=captured[0]
    assert path=="/fleet/v1/native/start" and body["event"]=="before_deploy" and body["predecessor"]==predecessor
    assert "process_sha256" in body and body["process_sha256"] is None
    assert kwargs["deadline_monotonic"]==123

def test_rpc_burst_keeps_one_heartbeat_round_budget(tmp_path,monkeypatch):
    from concurrent.futures import Future
    from types import SimpleNamespace
    import vibemql5.fleet.transport as transport
    clock=[0.0];events=[]
    monkeypatch.setattr(transport,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    class Http:policy=replace(fleet_policy(),heartbeat_interval_ms=20)
    class Client:
        http=Http();device_id=DEVICE;route_generation=1
        def heartbeat(self,session):events.append("heartbeat")
        def poll(self,session,limit):return {"commands":[]}
        def start_authorize(self,session,command,deadline_monotonic=None):
            events.append("authority")
            assert deadline_monotonic<=.02
            if clock[0]+.015>deadline_monotonic:
                clock[0]=deadline_monotonic
                raise WireError("HTTPS_UNAVAILABLE")
            clock[0]+=.015
            return {"fixture":True}
    agent=OutboundNode(Client(),tmp_path,Http.policy)
    futures=[Future() for _ in range(4)]
    for future in futures:agent._rpc.put_nowait(("START_AUTHORIZE",{"session_id":"session","command":{}},10.0,future))
    agent.step()
    assert events==["heartbeat","authority","authority"] and agent._rpc.qsize()==2
    assert futures[0].result()=={"fixture":True} and isinstance(futures[1].exception(),WireError)
    assert not futures[2].done() and clock[0]==.02

def test_writer_drain_authority_preserves_only_finite_optional_receipts():
    class Http:policy=fleet_policy()
    client=NodeClient(Http(),None,DEVICE,1);captured=[]
    client._post=lambda path,value,**kwargs:(captured.append((path,value)) or {"body":{"fixture":True},"signature":"0"*128})
    binding={"session_id":"session","operation_id":"op","project_id":"project","target":TARGET,
        "principal_id":"principal","principal_epoch":1,"assignment_epoch":1,"writer_epoch":1,
        "phase":"session_commit","intent_sha256":"1"*64,"challenge":"2"*32,
        "phase_acks":[{"fixture_only":True}],"drain_approval":{"body":{"fixture_only":True},"signature":"3"*128}}
    assert set(client.writers_authorize(**binding))=={"body","signature"}
    assert captured[0]==("/fleet/v1/writers/authorize",{"schema":"fleet.writer-authorization-request/1",**binding})
    with pytest.raises(WireError):client.writers_authorize(**binding,caller_approved=True)
    with pytest.raises(WireError):client.writers_authorize(**{**binding,"phase_acks":[{}]*6})
    with pytest.raises(WireError):client.writers_authorize(**{**binding,"drain_approval":{"approved":True}})

def test_cancel_authority_waits_for_exact_progress_ack(tmp_path):
    from concurrent.futures import Future
    events=[]
    class Http:policy=fleet_policy()
    class Client:
        http=Http();device_id=DEVICE;route_generation=1
        def start_authorize(self,*args,**kwargs):events.append("authority");return {"fixture":True}
    class Dispatcher:
        def flush_native_progress(self,client,session,global_job_id,deadline_monotonic=None):
            assert session=="session" and global_job_id=="job_fixture"
            events.append("progress")
            raise WireError("fixture_lost_progress_ack")
    agent=OutboundNode(Client(),tmp_path,Http.policy,domain_dispatcher=Dispatcher())
    command={"global_job_id":"job_fixture","authorization_process_sha256":"1"*64}
    failed=Future();agent._rpc.put_nowait(("START_AUTHORIZE",{"session_id":"session","command":command},time.monotonic()+1,failed))
    agent._service_rpc()
    assert failed.exception().code=="fixture_lost_progress_ack" and events==["progress"]
    agent._domain_dispatcher.flush_native_progress=lambda *args,**kwargs:events.append("progress_ack")
    accepted=Future();agent._rpc.put_nowait(("START_AUTHORIZE",{"session_id":"session","command":command},time.monotonic()+1,accepted))
    agent._service_rpc()
    assert accepted.result()=={"fixture":True} and events==["progress","progress_ack","authority"]

def test_stop_control_round_keeps_heartbeat_rpc_and_drain_without_poll(tmp_path):
    from concurrent.futures import Future
    events=[]
    class Http:policy=fleet_policy()
    class Client:
        http=Http();device_id=DEVICE;route_generation=1
        def heartbeat(self,session):events.append("heartbeat")
        def poll(self,*args):raise AssertionError("stop admitted new command")
        def poll_cancel_only(self,*args):events.append("cancel_poll");return {"commands":[]}
        def start_authorize(self,*args,**kwargs):events.append("existing_authority");return {"fixture":True}
    class Dispatcher:
        def drain(self,*args):events.append("drain");return []
    node=OutboundNode(Client(),tmp_path,Http.policy,domain_dispatcher=Dispatcher())
    future=Future();node._rpc.put_nowait(("START_AUTHORIZE",{"session_id":"session","command":{}},time.monotonic()+1,future))
    node.step(poll_commands=False)
    assert future.result()=={"fixture":True} and events==["heartbeat","cancel_poll","existing_authority","drain"]
    with pytest.raises(WireError,match="NODE_CONTROL_INVALID"):node.step(poll_commands=0)

def test_terminal_recovery_witness_uses_finite_signed_lane_only():
    class Http:policy=fleet_policy()
    client=NodeClient(Http(),None,DEVICE,1);requests=[]
    client._post=lambda path,value:(requests.append((path,value)) or {"fixture":True})
    witness={"schema":"fixture.read-only-historical-witness/1","outcome":"KNOWN_TERMINAL"}
    assert client.terminal_recovery_witness("session",witness)=={"fixture":True}
    assert requests==[("/fleet/v1/jobs/recovery-witness",{"schema":"fleet.native-recovery-envelope/1","session_id":"session","witness":witness})]

def test_cancel_only_real_tls_poll_does_not_deliver_queued_reads(service):
    http,owner,*_=service;node,_,_=enrolled(service)
    node.heartbeat("stop-session")
    queued=owner.read("get_account_snapshot",TARGET,"stop-read-queued")
    assert node.poll_cancel_only("stop-session",4)["commands"]==[]
    assert owner.read_status(queued["command_id"])["status"]=="PENDING"
    assert node.poll("stop-session",4)["commands"][0]["command_id"]==queued["command_id"]

def test_cancel_only_response_cannot_admit_workload():
    class Http:policy=fleet_policy()
    client=NodeClient(Http(),None,DEVICE,1)
    client._post=lambda *args,**kwargs:{"schema":"fleet.poll-receipt/1","mode":"CANCEL_ONLY","commands":[{"kind":"NATIVE"}]}
    with pytest.raises(WireError,match="NODE_CONTROL_INVALID"):client.poll_cancel_only("session",1)

@pytest.mark.parametrize("context",[object(),ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)])
def test_server_rejects_untrusted_context_before_opening_authority(context):
    called=[]
    with pytest.raises(WireError,match="TLS_SERVER_CONTEXT_INVALID"):
        serve_gateway(("127.0.0.1",0),ssl_context=context,controller_factory=lambda *_:called.append(True))
    assert called==[]

def test_server_context_uses_loaded_identity_without_reopening_paths(tmp_path,tls_files):
    ca,certificate,private=tls_files
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate,private)
    certificate.unlink();private.unlink()
    ready=Queue();errors=Queue();stop=threading.Event()
    def factory(address):
        store=GatewayControlStore.initialize(tmp_path/"context-control.sqlite",policy=control_policy())
        return GatewayController(store,fleet_policy(),audience="https://127.0.0.1:"+str(address[1]),
            owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest())
    def run():
        try:serve_gateway(("127.0.0.1",0),ssl_context=context,controller_factory=factory,stop_event=stop,started=ready.put)
        except BaseException as error:errors.put(error)
    thread=threading.Thread(target=run,daemon=True);thread.start()
    try:
        address=ready.get(timeout=3)
        owner=OwnerClient(HttpsClient("https://127.0.0.1:"+str(address[1]),fleet_policy(),cafile=str(ca)),TOKEN)
        with pytest.raises(WireError,match="READ_INTERRUPTED"):owner.read_status("read_unknown")
    finally:
        stop.set();thread.join(timeout=3)
    assert not thread.is_alive() and errors.empty()
