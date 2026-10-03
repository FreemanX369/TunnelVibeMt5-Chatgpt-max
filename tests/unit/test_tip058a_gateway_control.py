"""Durable local control evidence with explicit synthetic policy; no auth/VM/SDK claims."""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import sqlite3
import threading
import time
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from vibemql5.fleet.gateway_control import GatewayControlError, GatewayControlStore, Policy

DEVICE_A, DEVICE_B = "dev_" + "a" * 32, "dev_" + "b" * 32
KEY_A, KEY_B = "a" * 64, "b" * 64  # Public-key references only; not possession evidence.
DIGEST_A, DIGEST_B = "1" * 64, "2" * 64
MCP_SCHEMAS_C1_SHA256 = "64337437115a20a8555cc1214706a503b985195dbdbd219de2adfa35e2c8134d"


@pytest.fixture
def policy():
    # Synthetic capacities/time profile required explicitly by every constructor.
    return Policy(singleton_wait_ms=25, sqlite_busy_timeout_ms=25, grant_ttl_ms=1000,
        clock_skew_ms=100, nonce_retention_ms=300, grant_secret_bytes=32,
        max_devices=8, max_grants=16, max_nonces=16, max_operations=32,
        max_nonce_bytes=64, max_operation_id_bytes=64)


@pytest.fixture
def store(tmp_path, policy):
    value = GatewayControlStore.initialize(tmp_path / "gateway.sqlite", policy=policy)
    yield value
    value.close()


def expect(code, action):
    with pytest.raises(GatewayControlError) as caught:
        action()
    assert caught.value.code == code
    assert str(caught.value) == code
    assert len(str(caught.value)) < 64


def issue(store, *, device=DEVICE_A, key=KEY_A, generation=None, operation="issue-a", revision=None, now=1000):
    return store.issue_grant(device, key, expected_route_generation=generation,
        expected_revision=store.snapshot()["revision"] if revision is None else revision,
        operation_id=operation, now_ms=now)


def consume(store, issued, *, device=DEVICE_A, key=KEY_A, operation="consume-a", revision=None, now=1001, secret=None):
    return store.consume_grant(issued["receipt"]["grant_id"], issued["secret"] if secret is None else secret,
        device, key, expected_revision=store.snapshot()["revision"] if revision is None else revision,
        operation_id=operation, now_ms=now)


def paired(store):
    issued = issue(store)
    receipt = consume(store, issued)
    return issued, receipt


def wire_pair(store, grant, *, nonce="wire-pair-a", digest=DIGEST_A, now=1001,
              generation=0, device=DEVICE_A, key=KEY_A, operation="nodepair:consume-a", revision=2):
    # Direct trusted-hook fixture. Real Ed25519 and HTTPS are verified in B tests.
    return store.consume_verified_grant(grant["receipt"]["grant_id"], grant["secret"], device, key,
        expected_revision=revision, operation_id=operation, now_ms=now,
        signed_route_generation=generation, nonce=nonce, request_sha256=digest, timestamp_ms=now)


def assert_no_secret(snapshot, secret):
    assert secret not in json.dumps(snapshot, sort_keys=True)


def assert_control_unchanged(store, before):
    after = store.snapshot()
    assert {key: value for key, value in after.items() if key != "last_wall_ms"} == {
        key: value for key, value in before.items() if key != "last_wall_ms"}
    assert after["last_wall_ms"] >= before["last_wall_ms"]


def join(process):
    process.join(timeout=10)
    if process.is_alive():
        process.kill()
        process.join(timeout=5)
        raise AssertionError("Disposable control fixture exceeded bounded process wait")


def hold_then_crash(path, policy_values, ready, crash):
    store = GatewayControlStore.open_existing(Path(path), policy=Policy(**policy_values))
    ready.set()
    if not crash.wait(timeout=10):
        store.close()
        os._exit(79)
    os._exit(73)  # Deliberate harmless cooperative writer crash; no PID/TTL recovery.


def competing_open(path, policy_values, queue):
    try:
        with GatewayControlStore.open_existing(Path(path), policy=Policy(**policy_values)):
            queue.put("OPENED")
    except GatewayControlError as error:
        queue.put(error.code)


def crash_issue(path, policy_values, stage):
    def fault(event):
        if event == "issue_grant:" + stage:
            os._exit(74)
    with GatewayControlStore.open_existing(Path(path), policy=Policy(**policy_values), fault=fault) as store:
        issue(store)
    os._exit(78)


def crash_consume(path, policy_values, grant, stage):
    def fault(event):
        if event == "consume_grant:" + stage:
            os._exit(75)
    with GatewayControlStore.open_existing(Path(path), policy=Policy(**policy_values), fault=fault) as store:
        consume(store, grant, revision=2)
    os._exit(78)


def test_explicit_initialization_reopen_canonical_path_and_no_lazy_bootstrap(tmp_path, policy):
    path = tmp_path / "control.sqlite"
    expect("CONTROL_MISSING", lambda: GatewayControlStore.open_existing(path, policy=policy))
    assert not path.exists()
    with GatewayControlStore.initialize(path, policy=policy) as store:
        snapshot = store.snapshot()
        assert snapshot["revision"] == 1
        assert snapshot["status"] == "READY_CONTROL_ONLY"
        assert snapshot["policy"] == asdict(policy)
        assert not any(snapshot[key] for key in ("devices", "grants", "nonces", "operations"))
        with sqlite3.connect(path) as database:
            assert database.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        expect("CONTROL_BUSY", lambda: GatewayControlStore.open_existing(path, policy=policy))
    with GatewayControlStore.open_existing(path.parent / "." / path.name, policy=policy) as reopened:
        assert reopened.snapshot() == snapshot
    expect("CONTROL_CLOSED", reopened.snapshot)
    expect("CONTROL_EXISTS", lambda: GatewayControlStore.initialize(path, policy=policy))


@pytest.mark.parametrize("field,value", [
    ("singleton_wait_ms", True), ("sqlite_busy_timeout_ms", 0), ("grant_ttl_ms", -1),
    ("clock_skew_ms", -1), ("nonce_retention_ms", 100), ("grant_secret_bytes", 0),
    ("max_devices", False), ("max_grants", 1.0), ("max_nonces", float("inf")),
    ("max_operations", "32"), ("max_nonce_bytes", float("nan")),
    ("max_operation_id_bytes", 0), ("grant_ttl_ms", 2 ** 63),
])
def test_policy_requires_strict_primitives_safe_ranges_and_relationships(policy, field, value):
    values = {**asdict(policy), field: value}
    expect("CONTROL_INVALID", lambda: Policy(**values))
    incomplete = asdict(policy)
    del incomplete[field]
    with pytest.raises(TypeError): Policy(**incomplete)


@pytest.mark.parametrize("field,value", [("singleton_wait_ms", 60001), ("sqlite_busy_timeout_ms", 60001),
    ("grant_ttl_ms", 604800001), ("clock_skew_ms", 300001), ("nonce_retention_ms", 604800001),
    ("grant_secret_bytes", 31), ("grant_secret_bytes", 65), ("max_devices", 4097),
    ("max_grants", 65537), ("max_nonces", 65537), ("max_operations", 65537),
    ("max_nonce_bytes", 4097), ("max_operation_id_bytes", 1025)])
def test_policy_rejects_unbounded_allocations_storage_and_wait_profiles(policy, field, value):
    expect("CONTROL_INVALID", lambda: Policy(**{**asdict(policy), field: value}))


def test_accepted_policy_mechanism_ceiling_is_explicit_and_not_implicit_default(policy):
    maximum = replace(policy, singleton_wait_ms=60000, sqlite_busy_timeout_ms=60000,
        grant_ttl_ms=604800000, clock_skew_ms=300000, nonce_retention_ms=604800000,
        grant_secret_bytes=64, max_devices=4096, max_grants=65536, max_nonces=65536,
        max_operations=65536, max_nonce_bytes=4096, max_operation_id_bytes=1024)
    assert maximum.max_nonces == 65536
    with pytest.raises(TypeError): Policy()


def test_policy_mismatch_and_corrupt_or_unknown_state_fail_closed(tmp_path, policy):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy): pass
    expect("CONTROL_POLICY_MISMATCH", lambda: GatewayControlStore.open_existing(path,
        policy=replace(policy, max_devices=9)))
    path.write_bytes(b"not a sqlite database; caller-secret-must-not-leak")
    before = path.read_bytes()
    expect("CONTROL_CORRUPT", lambda: GatewayControlStore.open_existing(path, policy=policy))
    assert path.read_bytes() == before
    empty = tmp_path / "empty.sqlite"
    with sqlite3.connect(empty): pass
    expect("CONTROL_CORRUPT", lambda: GatewayControlStore.open_existing(empty, policy=policy))


@pytest.mark.parametrize("mutation", [
    "PRAGMA user_version=2",
    "ALTER TABLE devices ADD COLUMN unknown_authority TEXT",
    "CREATE TRIGGER unknown_effect AFTER INSERT ON nonces BEGIN UPDATE control SET revision=revision+1; END",
])
def test_unknown_schema_definition_fails_closed(tmp_path, policy, mutation):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy): pass
    with sqlite3.connect(path) as database:
        database.execute(mutation)
    expect("CONTROL_CORRUPT", lambda: GatewayControlStore.open_existing(path, policy=policy))


@pytest.mark.parametrize("field,value", [("state", "GRANT_ISSUED"), ("grant_id", None),
    ("expires_ms", None), ("route_generation", None)])
def test_corrupt_pair_receipt_cannot_be_returned_as_durable_replay(tmp_path, policy, field, value):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy) as store:
        paired(store)
    with sqlite3.connect(path) as database:
        raw = database.execute("SELECT receipt FROM operations WHERE operation_id='consume-a'").fetchone()[0]
        receipt = {**json.loads(raw), field: value}
        database.execute("UPDATE operations SET receipt=? WHERE operation_id='consume-a'",
            (json.dumps(receipt, sort_keys=True, separators=(",", ":")),))
    expect("CONTROL_CORRUPT", lambda: GatewayControlStore.open_existing(path, policy=policy))


def test_actual_cooperative_writer_denied_then_crash_releases_os_lock(tmp_path, policy):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy): pass
    context = multiprocessing.get_context("spawn")
    ready, crash, queue = context.Event(), context.Event(), context.Queue()
    owner = context.Process(target=hold_then_crash, args=(str(path), asdict(policy), ready, crash))
    owner.start()
    try:
        assert ready.wait(timeout=10)
        competitor = context.Process(target=competing_open, args=(str(path), asdict(policy), queue))
        competitor.start()
        join(competitor)
        assert competitor.exitcode == 0
        assert queue.get(timeout=5) == "CONTROL_BUSY"
        crash.set()
        join(owner)
        assert owner.exitcode == 73
        with GatewayControlStore.open_existing(path, policy=policy) as recovered:
            assert recovered.snapshot()["revision"] == 1
            assert recovered.snapshot()["status"] == "READY_CONTROL_ONLY"
    finally:
        if owner.is_alive():
            owner.kill()
            join(owner)
        queue.close()


def test_sqlite_busy_wait_is_bounded_and_does_not_partially_issue(store):
    before = store.snapshot()
    database = sqlite3.connect(store.path, isolation_level=None)
    try:
        database.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        expect("CONTROL_TRANSACTION_FAILED", lambda: issue(store))
        assert time.monotonic() - started < 2
    finally:
        database.rollback()
        database.close()
    assert store.snapshot() == before
    assert issue(store)["receipt"]["revision"] == 2


@pytest.mark.parametrize("operation", ["snapshot", "close"])
def test_cross_thread_access_denies_without_releasing_singleton_authority(store, operation):
    outcomes = []
    def competing_thread():
        try:
            getattr(store, operation)()
            outcomes.append("UNSAFE_SUCCESS")
        except GatewayControlError as error:
            outcomes.append(error.code)
    thread = threading.Thread(target=competing_thread)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive() and outcomes == ["CONTROL_BUSY"]
    assert store.snapshot()["revision"] == 1
    expect("CONTROL_BUSY", lambda: GatewayControlStore.open_existing(store.path, policy=store.policy))


def test_hardlinked_database_is_rejected_instead_of_using_alias_lock(tmp_path, policy):
    path, alias = tmp_path / "control.sqlite", tmp_path / "hardlink.sqlite"
    with GatewayControlStore.initialize(path, policy=policy): pass
    os.link(path, alias)
    expect("CONTROL_INVALID", lambda: GatewayControlStore.open_existing(alias, policy=policy))
    expect("CONTROL_INVALID", lambda: GatewayControlStore.open_existing(path, policy=policy))


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink spelling; Windows real cooperative writer test is platform-neutral")
def test_symlink_spelling_cannot_bypass_singleton_lock(tmp_path, policy):
    path, alias = tmp_path / "control.sqlite", tmp_path / "alias.sqlite"
    with GatewayControlStore.initialize(path, policy=policy):
        alias.symlink_to(path)
        expect("CONTROL_BUSY", lambda: GatewayControlStore.open_existing(alias, policy=policy))


def test_grant_secret_is_initial_only_never_in_db_snapshot_or_public_receipt(tmp_path, policy):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy) as store:
        issued = issue(store)
        secret = issued["secret"]
        assert isinstance(secret, str) and len(bytes.fromhex(secret)) == policy.grant_secret_bytes
        assert not issued["idempotent_recovered"]
        assert_no_secret(issued["receipt"], secret)
        assert_no_secret(store.snapshot(), secret)
        for file in tmp_path.iterdir():
            # Windows enforces the owner's locked byte while this writer lives.
            # Inspect database/WAL now and the lifetime lock after actual close.
            if file.is_file() and not file.name.endswith(".owner.lock"):
                assert secret.encode() not in file.read_bytes()
        paired_receipt = consume(store, issued)
        assert paired_receipt["receipt"]["route_generation"] == 1
        snapshot = store.snapshot()
    for file in tmp_path.iterdir():
        if file.is_file() and file.name.endswith(".owner.lock"):
            assert secret.encode() not in file.read_bytes()
    with GatewayControlStore.open_existing(path, policy=policy) as store:
        replay = issue(store, revision=1, now=1500)
        assert replay["idempotent_recovered"] is True
        assert replay["secret"] is None
        assert replay["receipt"] == issued["receipt"]
        assert store.snapshot() == snapshot
        replay_pair = consume(store, issued, revision=2, now=1600)
        assert replay_pair["idempotent_recovered"] is True
        assert replay_pair["receipt"] == paired_receipt["receipt"]
        assert store.snapshot() == snapshot


@pytest.mark.parametrize("device,key,secret,now,code", [
    (DEVICE_B, KEY_A, None, 1001, "CONTROL_GRANT_INVALID"),
    (DEVICE_A, KEY_B, None, 1001, "CONTROL_GRANT_INVALID"),
    (DEVICE_A, KEY_A, "0" * 64, 1001, "CONTROL_GRANT_INVALID"),
    (DEVICE_A, KEY_A, None, 2000, "CONTROL_GRANT_EXPIRED"),
])
def test_bad_expired_or_wrong_binding_grant_never_partially_consumes(store, device, key, secret, now, code):
    grant = issue(store)
    before = store.snapshot()
    expect(code, lambda: consume(store, grant, device=device, key=key, secret=secret, now=now))
    assert_control_unchanged(store, before)
    if code == "CONTROL_GRANT_EXPIRED":
        assert store.snapshot()["last_wall_ms"] == 2000
        expect("CONTROL_CLOCK_ROLLBACK", lambda: consume(store, grant, now=1001))
        assert_control_unchanged(store, before)
        return
    receipt = consume(store, grant)
    assert receipt["receipt"]["route_generation"] == 1
    used = store.snapshot()
    expect("CONTROL_GRANT_USED", lambda: consume(store, grant, operation="second-consumption", now=1002))
    assert_control_unchanged(store, used)


def test_durable_operation_conflict_and_original_cas_retry_after_reopen(tmp_path, policy):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy) as store:
        original = issue(store)
        consume(store, original)
        before = store.snapshot()
        expect("CONTROL_OPERATION_CONFLICT", lambda: issue(store, key=KEY_B, revision=1))
        assert store.snapshot() == before
    with GatewayControlStore.open_existing(path, policy=policy) as store:
        replay = issue(store, revision=1, now=9000)
        assert replay["receipt"] == original["receipt"] and replay["idempotent_recovered"]
        assert replay["secret"] is None
        assert store.snapshot() == before
        expect("CONTROL_REVISION_CONFLICT", lambda: issue(store, device=DEVICE_B, key=KEY_B,
            operation="new-stale-operation", revision=1, now=1002))
        assert_control_unchanged(store, before)


def test_revoke_repair_and_rotation_fence_old_generations(store):
    paired(store)
    revoked = store.revoke(DEVICE_A, expected_route_generation=1,
        expected_revision=store.snapshot()["revision"], operation_id="revoke-a", now_ms=1002)
    assert revoked["receipt"]["route_generation"] == 2
    expect("CONTROL_REVOKED", lambda: store.reserve_nonce(DEVICE_A, route_generation=2,
        nonce="revoked", request_sha256=DIGEST_A, timestamp_ms=1002, now_ms=1002))
    regrant = issue(store, generation=2, operation="repair-grant", now=1003)
    repaired = consume(store, regrant, operation="repair-consume", now=1004)
    assert repaired["receipt"]["route_generation"] == 3
    before = store.snapshot()
    expect("CONTROL_ROUTE_MISMATCH", lambda: store.rotate_key(DEVICE_A, KEY_B,
        expected_public_key=KEY_A, expected_route_generation=1, expected_revision=before["revision"],
        operation_id="wrong-generation", now_ms=1005))
    assert_control_unchanged(store, before)
    expect("CONTROL_ROUTE_MISMATCH", lambda: store.rotate_key(DEVICE_A, KEY_B,
        expected_public_key="c" * 64, expected_route_generation=3, expected_revision=before["revision"],
        operation_id="wrong-key", now_ms=1005))
    rotated = store.rotate_key(DEVICE_A, KEY_B, expected_public_key=KEY_A,
        expected_route_generation=3, expected_revision=before["revision"], operation_id="rotate-a", now_ms=1005)
    assert rotated["receipt"]["route_generation"] == 4
    expect("CONTROL_ROUTE_MISMATCH", lambda: store.reserve_nonce(DEVICE_A, route_generation=3,
        nonce="old-generation", request_sha256=DIGEST_A, timestamp_ms=1005, now_ms=1005))
    nonce = store.reserve_nonce(DEVICE_A, route_generation=4, nonce="current-generation",
        request_sha256=DIGEST_A, timestamp_ms=1005, now_ms=1005)
    assert nonce["route_generation"] == 4


def test_unconsumed_grant_has_original_route_cas_even_after_new_pairing(store):
    first = issue(store)
    second = issue(store, operation="second-grant", now=1001)
    consume(store, first, now=1002)
    before = store.snapshot()
    expect("CONTROL_ROUTE_MISMATCH", lambda: consume(store, second,
        operation="consume-stale-grant", now=1003))
    assert_control_unchanged(store, before)
    assert [entry["consumed"] for entry in store.snapshot()["grants"]].count(1) == 1


def test_nonce_verification_key_is_rechecked_with_route_before_admission(store):
    paired(store)
    before = store.snapshot()
    expect("CONTROL_ROUTE_MISMATCH", lambda: store.reserve_nonce(DEVICE_A,
        expected_public_key=KEY_B, route_generation=1, nonce="verified-for-wrong-key",
        request_sha256=DIGEST_A, timestamp_ms=1002, now_ms=1002))
    assert_control_unchanged(store, before)
    receipt = store.reserve_nonce(DEVICE_A, expected_public_key=KEY_A,
        route_generation=1, nonce="verified-for-wrong-key", request_sha256=DIGEST_A,
        timestamp_ms=1002, now_ms=1002)
    assert receipt["route_generation"] == 1
    assert len(store.snapshot()["nonces"]) == 1


def test_verified_pair_commits_initial_route_zero_nonce_and_replays_with_fresh_nonce(tmp_path, policy):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy) as store:
        grant = issue(store)
        original = wire_pair(store, grant)
        snapshot = store.snapshot()
        assert snapshot["revision"] == 3
        assert snapshot["grants"][0]["consumed"] == 1
        assert snapshot["devices"][0]["route_generation"] == 1
        assert snapshot["nonces"][0]["route_generation"] == 0
        assert snapshot["nonces"][0]["purpose"] == "PAIR"
        expect("CONTROL_INVALID", lambda: store.reserve_nonce(DEVICE_A,
            route_generation=0, nonce="ordinary-route-zero", request_sha256=DIGEST_A,
            timestamp_ms=1002, now_ms=1002))
    with GatewayControlStore.open_existing(path, policy=policy) as store:
        replay = wire_pair(store, grant, nonce="wire-pair-b", digest=DIGEST_B, now=1002)
        assert replay["idempotent_recovered"] and replay["receipt"] == original["receipt"]
        current = store.snapshot()
        assert current["revision"] == 4 and len(current["operations"]) == 2
        assert len(current["nonces"]) == 2
        for digest in (DIGEST_A, DIGEST_B):
            expect("CONTROL_REPLAY", lambda: wire_pair(store, grant, nonce="wire-pair-b", digest=digest, now=1002))
        assert store.snapshot() == current


@pytest.mark.parametrize("field,value,code", [("device", DEVICE_B, "CONTROL_GRANT_INVALID"),
    ("key", KEY_B, "CONTROL_GRANT_INVALID"), ("generation", 1, "CONTROL_ROUTE_MISMATCH"),
    ("revision", 1, "CONTROL_REVISION_CONFLICT"), ("operation", "consume-a", "CONTROL_INVALID"),
    ("operation", "nodepair:", "CONTROL_INVALID")])
def test_verified_pair_rejects_wrong_binding_without_any_half_consumption(store, field, value, code):
    grant = issue(store)
    before = store.snapshot()
    expect(code, lambda: wire_pair(store, grant, **{field: value}))
    assert_control_unchanged(store, before)
    assert not store.snapshot()["devices"] and not store.snapshot()["nonces"]


@pytest.mark.parametrize("transition", ["revoke", "rotate", "repair"])
def test_verified_pair_replay_cannot_repaint_new_authority(store, transition):
    grant = issue(store)
    wire_pair(store, grant)
    revision = store.snapshot()["revision"]
    if transition == "revoke":
        store.revoke(DEVICE_A, expected_route_generation=1, expected_revision=revision,
            operation_id="owner-revoke", now_ms=1002)
    elif transition == "rotate":
        store.rotate_key(DEVICE_A, KEY_B, expected_public_key=KEY_A, expected_route_generation=1,
            expected_revision=revision, operation_id="owner-rotate", now_ms=1002)
    else:
        regrant = issue(store, generation=1, operation="owner-repair-grant", now=1002)
        consume(store, regrant, operation="owner-repair-consume", now=1003)
    before = store.snapshot()
    expect("CONTROL_ROUTE_MISMATCH", lambda: wire_pair(store, grant, nonce="late-pair-retry", now=1004))
    assert_control_unchanged(store, before)


@pytest.mark.parametrize("stage", ["before_commit", "after_commit"])
def test_verified_pair_nonce_grant_route_and_receipt_share_commit_boundary(tmp_path, policy, stage):
    path = tmp_path / "control.sqlite"
    fired = []
    def fault(event):
        if event == "consume_verified_grant:" + stage and not fired:
            fired.append(event)
            raise OSError("unsafe raw secret/SQL/path")
    with GatewayControlStore.initialize(path, policy=policy, fault=fault) as store:
        grant = issue(store)
        expect("CONTROL_TRANSACTION_FAILED" if stage == "before_commit" else "CONTROL_COMMIT_UNCERTAIN",
            lambda: wire_pair(store, grant))
        snapshot = store.snapshot()
        committed = stage == "after_commit"
        assert bool(snapshot["devices"]) is committed
        assert bool(snapshot["nonces"]) is committed
        assert bool(snapshot["grants"][0]["consumed"]) is committed
        assert len(snapshot["operations"]) == 1 + int(committed)
        assert snapshot["revision"] == 2 + int(committed)
    with GatewayControlStore.open_existing(path, policy=policy) as store:
        assert store.snapshot() == snapshot
        replay = wire_pair(store, grant, nonce="fresh-after-reopen", now=1002)
        assert replay["idempotent_recovered"] is committed
        assert replay["receipt"]["route_generation"] == 1


@pytest.mark.parametrize("capacity", ["max_operations", "max_nonces"])
def test_verified_pair_capacity_does_not_half_consume_or_lose_receipt(tmp_path, policy, capacity):
    policy = replace(policy, **{capacity: 1})
    with GatewayControlStore.initialize(tmp_path / "control.sqlite", policy=policy) as store:
        grant = issue(store)
        if capacity == "max_operations":
            before = store.snapshot()
            expect("CONTROL_CAPACITY", lambda: wire_pair(store, grant))
            assert_control_unchanged(store, before)
            assert not store.snapshot()["devices"] and not store.snapshot()["nonces"]
        else:
            original = wire_pair(store, grant)
            before = store.snapshot()
            expect("CONTROL_CAPACITY", lambda: wire_pair(store, grant, nonce="capacity-new", now=1002))
            assert_control_unchanged(store, before)
            assert before["operations"][-1]["receipt"] == original["receipt"]


def test_admin_cannot_collide_with_reserved_verified_pair_namespace(store):
    before = store.snapshot()
    expect("CONTROL_INVALID", lambda: issue(store, operation="nodepair:consume-a"))
    assert store.snapshot() == before


def test_route_zero_nonce_is_pair_only_and_corruption_denies_reopen(tmp_path, policy):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy) as store:
        wire_pair(store, issue(store))
    with sqlite3.connect(path) as database:
        database.execute("UPDATE nonces SET purpose='NODE_ROUTE' WHERE route_generation=0")
    expect("CONTROL_CORRUPT", lambda: GatewayControlStore.open_existing(path, policy=policy))


@pytest.mark.parametrize("mutation", [
    "UPDATE devices SET public_key='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'",
    "UPDATE devices SET route_generation=2",
    "UPDATE grants SET consumed=0",
    "UPDATE grants SET public_key='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'",
])
def test_relational_control_corruption_cannot_rewrite_current_authority(tmp_path, policy, mutation):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy) as store:
        wire_pair(store, issue(store))
    with sqlite3.connect(path) as database:
        database.execute(mutation)
    expect("CONTROL_CORRUPT", lambda: GatewayControlStore.open_existing(path, policy=policy))


@pytest.mark.parametrize("mutation", ["duplicate_key", "alternate_serialization"])
def test_corrupt_receipt_json_cannot_hide_duplicate_keys_or_alternate_representation(tmp_path, policy, mutation):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy) as store:
        paired(store)
    with sqlite3.connect(path) as database:
        raw = database.execute("SELECT receipt FROM operations WHERE operation_id='consume-a'").fetchone()[0]
        if mutation == "duplicate_key":
            changed = '{"operation_id":"hidden-conflict",' + raw[1:]
        else:
            changed = json.dumps(json.loads(raw), indent=2)
        database.execute("UPDATE operations SET receipt=? WHERE operation_id='consume-a'", (changed,))
    expect("CONTROL_CORRUPT", lambda: GatewayControlStore.open_existing(path, policy=policy))


def test_nonce_replay_is_separate_from_operation_idempotency_and_durable(tmp_path, policy):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy) as store:
        paired(store)
        receipt = store.reserve_nonce(DEVICE_A, route_generation=1, nonce="nonce-a",
            request_sha256=DIGEST_A, timestamp_ms=1002, now_ms=1002)
        before = store.snapshot()
        assert receipt["route_generation"] == 1
        for digest in (DIGEST_A, DIGEST_B):
            expect("CONTROL_REPLAY", lambda: store.reserve_nonce(DEVICE_A, route_generation=1, nonce="nonce-a",
                request_sha256=digest, timestamp_ms=1002, now_ms=1002))
        assert store.snapshot() == before
    with GatewayControlStore.open_existing(path, policy=policy) as store:
        expect("CONTROL_REPLAY", lambda: store.reserve_nonce(DEVICE_A, route_generation=1, nonce="nonce-a",
            request_sha256=DIGEST_A, timestamp_ms=1002, now_ms=1002))
        assert store.snapshot() == before


@pytest.mark.parametrize("timestamp,now,code", [(900, 1002, "CONTROL_TIME_INVALID"),
    (1203, 1002, "CONTROL_TIME_INVALID"), (1000, 1000, "CONTROL_CLOCK_ROLLBACK")])
def test_nonce_stale_future_or_wall_rollback_denies_without_persisting(store, timestamp, now, code):
    paired(store)
    before = store.snapshot()
    expect(code, lambda: store.reserve_nonce(DEVICE_A, route_generation=1, nonce="bad-time",
        request_sha256=DIGEST_A, timestamp_ms=timestamp, now_ms=now))
    assert_control_unchanged(store, before)


def test_denied_expiry_wall_observation_survives_reopen_and_cannot_resurrect_grant(tmp_path, policy):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy) as store:
        grant = issue(store)
        expect("CONTROL_GRANT_EXPIRED", lambda: consume(store, grant, now=2000))
        state = store.snapshot()
        assert not state["devices"] and state["last_wall_ms"] == 2000
    with GatewayControlStore.open_existing(path, policy=policy) as store:
        expect("CONTROL_CLOCK_ROLLBACK", lambda: consume(store, grant, now=1001))
        assert store.snapshot() == state


@pytest.mark.parametrize("field,value", [("device_id", "dev_" + "A" * 32),
    ("public_key", "Bearer-private-key-must-not-appear"), ("generation", True),
    ("operation", "bad\0caller-secret"), ("operation", "x" * 65), ("now", 1.0)])
def test_invalid_control_inputs_are_bounded_errors_and_no_state_change(store, field, value):
    args = {"device": DEVICE_A, "key": KEY_A, "generation": None, "operation": "valid", "now": 1000}
    args[{"device_id": "device", "public_key": "key"}.get(field, field)] = value
    before = store.snapshot()
    expect("CONTROL_TIME_INVALID" if field == "now" else "CONTROL_INVALID", lambda: issue(store, **args))
    assert store.snapshot() == before


@pytest.mark.parametrize("field,value", [("nonce", ""), ("nonce", "x" * 65), ("nonce", "bad\0secret"),
    ("nonce", "\ud800"), ("request_sha256", "bad-secret"), ("route_generation", True),
    ("timestamp_ms", False), ("now_ms", float("nan"))])
def test_invalid_nonce_inputs_do_not_create_replay_records(store, field, value):
    paired(store)
    values = {"route_generation": 1, "nonce": "valid-nonce", "request_sha256": DIGEST_A,
              "timestamp_ms": 1002, "now_ms": 1002, field: value}
    before = store.snapshot()
    expect("CONTROL_TIME_INVALID" if field in {"timestamp_ms", "now_ms"} else "CONTROL_INVALID",
        lambda: store.reserve_nonce(DEVICE_A, **values))
    assert store.snapshot() == before


@pytest.mark.parametrize("field,value", [("timestamp_ms", -1), ("timestamp_ms", float("inf")),
    ("now_ms", -1), ("now_ms", True), ("now_ms", 2 ** 63)])
def test_nonce_bad_numeric_time_uses_bounded_typed_error(store, field, value):
    paired(store)
    values = {"expected_public_key": KEY_A, "route_generation": 1, "nonce": "valid-nonce",
              "request_sha256": DIGEST_A, "timestamp_ms": 1002, "now_ms": 1002, field: value}
    before = store.snapshot()
    expect("CONTROL_TIME_INVALID", lambda: store.reserve_nonce(DEVICE_A, **values))
    assert store.snapshot() == before


@pytest.mark.parametrize("timestamp", [902, 1102])
def test_nonce_clock_window_boundaries_are_inclusive_with_complete_retention(store, timestamp):
    paired(store)
    store.reserve_nonce(DEVICE_A, expected_public_key=KEY_A, route_generation=1,
        nonce="boundary-nonce", request_sha256=DIGEST_A, timestamp_ms=timestamp, now_ms=1002)
    row = store.snapshot()["nonces"][0]
    assert row["retain_until_ms"] >= max(1002 + store.policy.nonce_retention_ms,
        timestamp + store.policy.clock_skew_ms)


@pytest.mark.parametrize("capacity", ["max_grants", "max_operations", "max_nonces", "max_devices"])
def test_capacity_never_evicts_committed_operations_or_acceptable_replay_proof(tmp_path, policy, capacity):
    limits = {"max_grants": 1, "max_operations": 2, "max_nonces": 1, "max_devices": 1}
    policy = replace(policy, **{capacity: limits[capacity]})
    with GatewayControlStore.initialize(tmp_path / "control.sqlite", policy=policy) as store:
        grant = issue(store)
        consume(store, grant)
        before = store.snapshot()
        if capacity == "max_nonces":
            store.reserve_nonce(DEVICE_A, route_generation=1, nonce="first", request_sha256=DIGEST_A,
                timestamp_ms=1002, now_ms=1002)
            before = store.snapshot()
            expect("CONTROL_CAPACITY", lambda: store.reserve_nonce(DEVICE_A, route_generation=1,
                nonce="second", request_sha256=DIGEST_A, timestamp_ms=1300, now_ms=1300))
            expect("CONTROL_REPLAY", lambda: store.reserve_nonce(DEVICE_A, route_generation=1,
                nonce="first", request_sha256=DIGEST_A, timestamp_ms=1300, now_ms=1300))
        elif capacity == "max_devices":
            other = issue(store, device=DEVICE_B, key=KEY_B, operation="other-issue", now=1002)
            before = store.snapshot()
            expect("CONTROL_CAPACITY", lambda: consume(store, other, device=DEVICE_B, key=KEY_B,
                operation="other-consume", now=1003))
        else:
            expect("CONTROL_CAPACITY", lambda: issue(store, device=DEVICE_B, key=KEY_B,
                operation="another-grant", now=3000))
        assert_control_unchanged(store, before)
        before = store.snapshot()
        replay = issue(store, revision=1, now=4000)
        assert replay["idempotent_recovered"] and replay["secret"] is None
        assert store.snapshot() == before
        assert not any(hasattr(store, name) for name in ("prune", "force_clear", "mark_ready"))


@pytest.mark.parametrize("stage", ["before_commit", "after_commit"])
def test_pairing_commit_fault_never_half_consumes_grant_or_publishes_partial_route(tmp_path, policy, stage):
    path = tmp_path / "control.sqlite"
    fired = []
    def fault(event):
        if event == "consume_grant:" + stage and not fired:
            fired.append(event)
            raise OSError("caller secret/sql diagnostic must not leak")
    with GatewayControlStore.initialize(path, policy=policy, fault=fault) as store:
        grant = issue(store)
        before = store.snapshot()
        expect("CONTROL_TRANSACTION_FAILED" if stage == "before_commit" else "CONTROL_COMMIT_UNCERTAIN",
            lambda: consume(store, grant, revision=2))
        state = store.snapshot()
        if stage == "before_commit":
            assert_control_unchanged(store, before)
            assert state["devices"] == []
        else:
            assert state["revision"] == 3
            assert len(state["devices"]) == 1
            assert len(state["operations"]) == 2
    with GatewayControlStore.open_existing(path, policy=policy) as reopened:
        assert reopened.snapshot() == state
        receipt = consume(reopened, grant, revision=2, now=1002)
        assert receipt["idempotent_recovered"] is (stage == "after_commit")
        assert receipt["receipt"]["route_generation"] == 1
        expect("CONTROL_GRANT_USED", lambda: consume(reopened, grant, operation="pairing-duplicate", now=1002))


@pytest.mark.parametrize("stage", ["before_commit", "after_commit"])
def test_transaction_fault_gives_original_or_complete_receipt_and_reopen(tmp_path, policy, stage):
    path = tmp_path / "control.sqlite"
    fired = []
    def fault(event):
        if event == "issue_grant:" + stage and not fired:
            fired.append(event)
            raise OSError("unsafe caller/sql/path/secret must not leak")
    with GatewayControlStore.initialize(path, policy=policy, fault=fault) as store:
        expect("CONTROL_TRANSACTION_FAILED" if stage == "before_commit" else "CONTROL_COMMIT_UNCERTAIN",
            lambda: issue(store))
        snapshot = store.snapshot()
        assert snapshot["revision"] == (1 if stage == "before_commit" else 2)
        assert len(snapshot["grants"]) == len(snapshot["operations"]) == (0 if stage == "before_commit" else 1)
    with GatewayControlStore.open_existing(path, policy=policy) as store:
        assert store.snapshot() == snapshot
        retried = issue(store, revision=1)
        assert retried["idempotent_recovered"] is (stage == "after_commit")
        assert (retried["secret"] is None) is (stage == "after_commit")


@pytest.mark.parametrize("stage", ["before_commit", "after_commit"])
def test_process_interruption_commit_boundary_preserves_atomic_grant_and_operation(tmp_path, policy, stage):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy): pass
    child = multiprocessing.get_context("spawn").Process(target=crash_issue, args=(str(path), asdict(policy), stage))
    child.start()
    join(child)
    assert child.exitcode == 74
    with GatewayControlStore.open_existing(path, policy=policy) as store:
        state = store.snapshot()
        count = 0 if stage == "before_commit" else 1
        assert len(state["grants"]) == len(state["operations"]) == count
        assert state["revision"] == 1 + count
        retry = issue(store, revision=1)
        assert retry["idempotent_recovered"] is (stage == "after_commit")
        assert (retry["secret"] is None) is (stage == "after_commit")


@pytest.mark.parametrize("stage", ["before_commit", "after_commit"])
def test_process_interruption_pair_commit_never_splits_grant_route_and_receipt(tmp_path, policy, stage):
    path = tmp_path / "control.sqlite"
    with GatewayControlStore.initialize(path, policy=policy) as store:
        grant = issue(store)
    child = multiprocessing.get_context("spawn").Process(target=crash_consume,
        args=(str(path), asdict(policy), grant, stage))
    child.start()
    join(child)
    assert child.exitcode == 75
    with GatewayControlStore.open_existing(path, policy=policy) as store:
        state = store.snapshot()
        committed = stage == "after_commit"
        assert bool(state["devices"]) is committed
        assert bool(state["grants"][0]["consumed"]) is committed
        assert len(state["operations"]) == 1 + int(committed)
        result = consume(store, grant, revision=2)
        assert result["idempotent_recovered"] is committed
        assert result["receipt"]["route_generation"] == 1


@pytest.mark.parametrize("stage", ["before_commit", "after_commit"])
def test_nonce_commit_fault_never_publishes_half_replay_proof(tmp_path, policy, stage):
    path = tmp_path / "control.sqlite"
    fired = []
    def fault(event):
        if event == "reserve_nonce:" + stage and not fired:
            fired.append(event)
            raise OSError("unsafe caller/SQL diagnostic")
    with GatewayControlStore.initialize(path, policy=policy, fault=fault) as store:
        paired(store)
        before = store.snapshot()
        values = {"expected_public_key": KEY_A, "route_generation": 1, "nonce": "fault-nonce",
            "request_sha256": DIGEST_A, "timestamp_ms": 1002, "now_ms": 1002}
        expect("CONTROL_TRANSACTION_FAILED" if stage == "before_commit" else "CONTROL_COMMIT_UNCERTAIN",
            lambda: store.reserve_nonce(DEVICE_A, **values))
        state = store.snapshot()
        assert len(state["nonces"]) == int(stage == "after_commit")
        assert state["revision"] == before["revision"] + int(stage == "after_commit")
    with GatewayControlStore.open_existing(path, policy=policy) as store:
        assert store.snapshot() == state
        if stage == "after_commit":
            expect("CONTROL_REPLAY", lambda: store.reserve_nonce(DEVICE_A, **values))
        else:
            store.reserve_nonce(DEVICE_A, **values)


@pytest.mark.parametrize("operation", ["initialize", "restore"])
@pytest.mark.parametrize("stage", ["before_commit", "after_commit"])
def test_database_publication_fault_only_exposes_complete_or_fenced_state(tmp_path, policy, operation, stage):
    destination = tmp_path / "destination.sqlite"
    backup = tmp_path / "backup.sqlite"
    if operation == "restore":
        with GatewayControlStore.initialize(backup, policy=policy) as store:
            paired(store)
    def fault(event):
        if event == operation + ":" + stage:
            raise OSError("unsafe full path/SQL diagnostic")
    action = (lambda: GatewayControlStore.initialize(destination, policy=policy, fault=fault)) if operation == "initialize" else (
        lambda: GatewayControlStore.restore(backup, destination, policy=policy, fault=fault))
    expect("CONTROL_TRANSACTION_FAILED" if stage == "before_commit" else "CONTROL_COMMIT_UNCERTAIN", action)
    if stage == "before_commit":
        assert not destination.exists()
        with GatewayControlStore.initialize(destination, policy=policy) as store:
            assert store.snapshot()["revision"] == 1
    else:
        with GatewayControlStore.open_existing(destination, policy=policy) as store:
            state = store.snapshot()
            assert state["status"] == ("READY_CONTROL_ONLY" if operation == "initialize" else "RECONCILIATION_REQUIRED")
            assert state["revision"] == (1 if operation == "initialize" else 4)
    assert not any(path.name.endswith((".initialize", ".restore")) for path in tmp_path.iterdir())


def test_sqlite_backup_is_consistent_and_supported_restore_always_fences_admission(tmp_path, policy):
    path, backup, destination = tmp_path / "control.sqlite", tmp_path / "backup.sqlite", tmp_path / "restored.sqlite"
    with GatewayControlStore.initialize(path, policy=policy) as store:
        grant, receipt = paired(store)
        store.reserve_nonce(DEVICE_A, route_generation=1, nonce="retained-nonce", request_sha256=DIGEST_A,
            timestamp_ms=1002, now_ms=1002)
        original = store.snapshot()
        store.backup(backup)
        assert_no_secret(original, grant["secret"])
    with GatewayControlStore.open_existing(backup, policy=policy) as snapshot_store:
        assert snapshot_store.snapshot() == original
    with GatewayControlStore.restore(backup, destination, policy=policy) as restored:
        fenced = restored.snapshot()
        assert fenced["status"] == "RECONCILIATION_REQUIRED"
        for key in ("devices", "grants", "nonces", "operations"):
            assert fenced[key] == original[key]
        expect("CONTROL_RECONCILIATION_REQUIRED", lambda: issue(restored, device=DEVICE_B,
            key=KEY_B, operation="restored-new-issue", now=1003))
        expect("CONTROL_RECONCILIATION_REQUIRED", lambda: issue(restored, revision=1))
        assert not any(hasattr(restored, name) for name in ("force_clear", "mark_ready", "clear_reconciliation"))
    with GatewayControlStore.open_existing(destination, policy=policy) as reopened:
        assert reopened.snapshot()["status"] == "RECONCILIATION_REQUIRED"
        expect("CONTROL_RECONCILIATION_REQUIRED", lambda: reopened.reserve_nonce(DEVICE_A,
            route_generation=1, nonce="after-restore", request_sha256=DIGEST_A, timestamp_ms=1003, now_ms=1003))


def test_backup_restore_reject_corrupt_and_policy_mismatch_without_destination(tmp_path, policy):
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"secret malformed backup")
    destination = tmp_path / "restored.sqlite"
    expect("CONTROL_CORRUPT", lambda: GatewayControlStore.restore(corrupt, destination, policy=policy))
    assert not destination.exists()
    backup = tmp_path / "valid.sqlite"
    with GatewayControlStore.initialize(backup, policy=policy): pass
    expect("CONTROL_POLICY_MISMATCH", lambda: GatewayControlStore.restore(backup, destination,
        policy=replace(policy, max_nonces=18)))
    assert not destination.exists()


def test_all_85_actual_mcp_schemas_remain_at_c1_baseline(tmp_path, monkeypatch):
    from test_tip055a_runtime_forensics_identity import make_terminal, write_config
    from vibemql5.core.facade import ToolFacade
    from vibemql5.adapters.mcp import create_server
    from vibemql5.contracts import MCP_TOOL_NAMES, MCP_TOOL_COUNT, MCP_TOOL_CATALOG_SHA256
    write_config(tmp_path, [make_terminal(tmp_path)])
    monkeypatch.setattr(ToolFacade, "reconcile_cancelled_jobs", lambda *_args, **_kwargs: {})
    tools = create_server(tmp_path)._tool_manager._tools
    assert tuple(tools) == MCP_TOOL_NAMES and len(tools) == MCP_TOOL_COUNT == 85
    assert hashlib.sha256(("\n".join(tools) + "\n").encode()).hexdigest() == MCP_TOOL_CATALOG_SHA256
    generated = {name: tool.parameters for name, tool in tools.items()}
    assert hashlib.sha256(json.dumps(generated, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == MCP_SCHEMAS_C1_SHA256
