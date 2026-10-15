"""Read-only signed history fixtures; default real native stays unqualified."""
import copy

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from test_tip061a_057n import node
from test_tip060_journal import received, verifier, authorize, POLICY, fixture
from vibemql5.fleet.job_journal import JournalError, GatewayJobJournal, NodeJobJournal, terminal_closure
from vibemql5.fleet.native import RoutedNativeAdapter


def setup_history(node, tmp_path):
    gateway, journal, row, _ = received(node, tmp_path)
    final = journal.execute(row["global_job_id"], RoutedNativeAdapter(node["root"]),
        authorization_verifier=verifier(gateway), start_authorize=authorize(gateway))
    assert final["state"] == "FAILED" and final["result"]["reason_code"] == "NATIVE_QUALIFICATION_UNAVAILABLE"
    before = gateway.get(row["global_job_id"])
    issued = gateway.request_terminal_recovery("history-op", row["global_job_id"], device_id=row["target"]["device_id"],
        current_route_generation=2, current_session_id="replacement-session")
    command = gateway.poll_terminal_recoveries(row["target"]["device_id"], route_generation=2,
        session_id="replacement-session", max_commands=1)[0]
    return gateway, journal, row, before, issued, command


def test_known_terminal_after_new_session_is_historical_only_and_lost_ack_replays_exact(node, tmp_path):
    gateway, journal, row, before, issued, command = setup_history(node, tmp_path)
    key = Ed25519PrivateKey.generate(); public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    signed = journal.terminal_recovery_witness(command, private_key=key)
    assert journal.terminal_recovery_witness(command, private_key=key) == signed
    result = gateway.commit_terminal_recovery(signed, registered_public_key=public,
        current_route_generation=2, current_session_id="replacement-session")
    assert result["classification"] == "HISTORICAL_QUARANTINED"
    assert result["original"]["target"]["route_generation"] == 1
    assert result["original"]["session_id"] == "session-a" and result["current"]["session_id"] == "replacement-session"
    assert gateway.get(row["global_job_id"]) == before
    assert gateway.commit_terminal_recovery(signed, registered_public_key=public,
        current_route_generation=2, current_session_id="replacement-session") == result
    assert gateway.poll_terminal_recoveries(row["target"]["device_id"], route_generation=2,
        session_id="replacement-session", max_commands=1) == []
    journal.close(); gateway.close()
    with NodeJobJournal(tmp_path / "node.sqlite", **POLICY) as reopened:
        assert reopened.terminal_recovery_witness(command, private_key=key) == signed
    with GatewayJobJournal(tmp_path / "gateway.sqlite", **POLICY) as reopened:
        assert reopened.get(row["global_job_id"]) == before
        assert reopened.commit_terminal_recovery(signed, registered_public_key=public,
            current_route_generation=2, current_session_id="replacement-session") == result


@pytest.mark.parametrize("change", ["old_route", "old_session", "key", "body", "cross_device", "changed_op"])
def test_history_wrong_current_scope_or_changed_challenge_denied(node, tmp_path, change):
    gateway, journal, row, before, _issued, command = setup_history(node, tmp_path)
    key = Ed25519PrivateKey.generate(); public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    signed = journal.terminal_recovery_witness(command, private_key=key)
    args = {"registered_public_key": public, "current_route_generation": 2, "current_session_id": "replacement-session"}
    if change == "old_route": args["current_route_generation"] = 1
    elif change == "old_session": args["current_session_id"] = "session-a"
    elif change == "key": args["registered_public_key"] = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    elif change == "body": signed = copy.deepcopy(signed); signed["body"]["challenge"] = "0" * 32
    elif change == "cross_device":
        with pytest.raises(JournalError):
            gateway.request_terminal_recovery("cross-device", row["global_job_id"], device_id="dev_" + "f" * 32,
                current_route_generation=2, current_session_id="replacement-session")
        journal.close(); gateway.close(); return
    else:
        with pytest.raises(JournalError, match="IDEMPOTENCY_CONFLICT"):
            gateway.request_terminal_recovery("history-op", row["global_job_id"], device_id=row["target"]["device_id"],
                current_route_generation=3, current_session_id="different-session")
        journal.close(); gateway.close(); return
    with pytest.raises(JournalError): gateway.commit_terminal_recovery(signed, **args)
    assert gateway.get(row["global_job_id"]) == before
    journal.close(); gateway.close()


def test_nonterminal_unknown_or_missing_actual_closure_cannot_make_history(node, tmp_path):
    gateway, journal, row, _ = received(node, tmp_path)
    journal.execute(row["global_job_id"], fixture(node, []), authorization_verifier=verifier(gateway), start_authorize=authorize(gateway))
    gateway.request_terminal_recovery("history", row["global_job_id"], device_id=row["target"]["device_id"],
        current_route_generation=2, current_session_id="replacement-session")
    command = gateway.poll_terminal_recoveries(row["target"]["device_id"], route_generation=2,
        session_id="replacement-session", max_commands=1)[0]
    key = Ed25519PrivateKey.generate()
    with pytest.raises(JournalError, match="HISTORICAL_WITNESS_UNRESOLVED"):
        journal.terminal_recovery_witness(command, private_key=key)
    with journal.transaction():
        rec = journal._row(row["global_job_id"]); rec["state"] = "UNKNOWN"; journal._save(rec)
    with pytest.raises(JournalError): journal.terminal_recovery_witness(command, private_key=key)
    with journal.transaction():
        rec = journal._row(row["global_job_id"]); rec["state"] = "SUCCEEDED"; rec.pop("terminal_closure", None); journal._save(rec)
    with pytest.raises(JournalError, match="TERMINAL_CLOSURE_UNPROVEN"):
        journal.terminal_recovery_witness(command, private_key=key)
    journal.close(); gateway.close()


def test_history_challenge_and_witness_response_loss_keep_one_durable_identity(node, tmp_path):
    gateway, journal, row, before, issued, command = setup_history(node, tmp_path)
    def lose(point):
        if point == "after_commit": raise RuntimeError("fixture lost response")
    key = Ed25519PrivateKey.generate(); journal.fault = lose
    with pytest.raises(RuntimeError): journal.terminal_recovery_witness(command, private_key=key)
    journal.fault = None
    signed = journal.terminal_recovery_witness(command, private_key=key)
    gateway.fault = lose
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    with pytest.raises(RuntimeError):
        gateway.commit_terminal_recovery(signed, registered_public_key=public,
            current_route_generation=2, current_session_id="replacement-session")
    gateway.fault = None
    result = gateway.commit_terminal_recovery(signed, registered_public_key=public,
        current_route_generation=2, current_session_id="replacement-session")
    assert result["witness_sha256"] == gateway.request_terminal_recovery("history-op", row["global_job_id"],
        device_id=row["target"]["device_id"], current_route_generation=2, current_session_id="replacement-session")["witness_sha256"]
    assert gateway.get(row["global_job_id"]) == before
    journal.close(); gateway.close()


def scoped_closed_claim():
    """Pure historical DTO fixture; no local process or physical proof is minted."""
    target = {'schema': 'fleet.target/1', 'device_id': 'dev_' + 'a' * 32,
        'route_generation': 1, 'terminal_id': 'term_' + 'b' * 32, 'terminal_generation': 1}
    rec = {'local_job_id': 'BT-20261003-010000-ABC123', 'request_sha256': 'c' * 64, 'target': target}
    process = {'pid': 123, 'creation': '123456', 'image': r'C:\MT5\terminal64.exe'}
    token = 'd' * 32
    closed = {'schema': 'fleet.scoped-ownership/1', 'operation_id': 'native-test', 'token': token,
        'reservation_id': 'scope_' + token, 'profile_sha256': 'e' * 64, 'epoch': 'f' * 32,
        'request': {'kind': 'tester', 'terminal_id': target['terminal_id'], 'terminal_generation': 1,
            'resources': [{'kind': kind, 'path': 'C:\\MT5\\' + kind, 'physical_key': '1:' + str(index)}
                for index, kind in enumerate(('executable', 'data_root', 'include_root', 'agent_root'))]},
        'status': 'RELEASED', 'phase': 'CLOSED', 'generation': 1,
        'parent': {'pid': 124, 'creation': '123457', 'image': r'C:\Python\python.exe'},
        'worker': None, 'descendants': 'NONE', 'evidence': 'SIGNED_PHYSICAL_CAPACITY_PROFILE'}
    claim = {'schema': 'fleet.native.closure/1', **rec, 'evidence': 'OPERATOR_APPROVED_REAL_NATIVE',
        'phases': [{'phase': 'test', 'ownership_record': closed, 'process': process,
                    'descendants': 'EXACT_DESCENDANTS_EXITED'}], 'lease_release': 'RETURNED'}
    return rec, claim


def test_pure_historical_closed_dto_accepts_windows_paths_on_gateway_without_process_access():
    rec, claim = scoped_closed_claim()
    assert terminal_closure(claim, rec) == claim


@pytest.mark.parametrize('change', ['unknown_resource', 'duplicate_kind', 'relative_root', 'control_path',
                                  'physical_key', 'epoch', 'real_without_process'])
def test_pure_historical_closed_dto_rejects_nested_unknown_or_ambiguous_claim(change):
    rec, claim = scoped_closed_claim(); row = claim['phases'][0]
    resource = row['ownership_record']['request']['resources'][0]
    if change == 'unknown_resource': resource['secret'] = 'must-not-persist'
    elif change == 'duplicate_kind': resource['kind'] = 'data_root'
    elif change == 'relative_root': resource['path'] = r'\relative'
    elif change == 'control_path': resource['path'] = 'C:\\MT5\\data\troot'
    elif change == 'physical_key': resource['physical_key'] = 'invented'
    elif change == 'epoch': row['ownership_record']['epoch'] = 'embedded secret\n'
    else: row['process'] = None; row['descendants'] = 'NONE'
    with pytest.raises(JournalError): terminal_closure(claim, rec)
