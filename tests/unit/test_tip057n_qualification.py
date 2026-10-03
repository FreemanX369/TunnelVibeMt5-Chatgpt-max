"""Signed metadata validation only; all evidence below is a fictitious operator claim.

Positive metadata tests do not certify controls or activate production on Linux.
No real MT5/native qualification file is installed outside temporary fixtures.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from vibemql5.fleet.identity import normalize_path
from vibemql5.fleet.native_qualification import (CONTROLS, DOMAIN, QualificationError,
    file_hash, source_manifest, validate_approval, load_installation, RUNTIME_DOMAIN, validate_runtime, scoped_installation_match, qualification_path)
from vibemql5.fleet.project_targets import canonical
from test_tip061a_057n import node, freeze, ref, logical_fixture
from vibemql5.fleet.native import native_request


@pytest.fixture
def approval_fixture(node):
    root=node["root"]; placement=freeze(node,target={**ref(node["registry"]),"route_generation":1})
    payload=source_manifest(); payload_sha=hashlib.sha256(canonical(payload)).hexdigest()
    key=Ed25519PrivateKey.generate(); public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex()
    evidence_root=root/"state/fleet/native-qualification-evidence"; evidence_root.mkdir(parents=True)
    controls={}
    for case in CONTROLS:
        path=evidence_root/(case+".json")
        # This is a fabricated signed claim, deliberately not a physical test.
        path.write_bytes(canonical({"schema":"fleet.native.control/1","case":case,"evidence":"REAL_MT5",
            "result":"PASS","target":placement["target"],"payload_sha256":payload_sha,
            "fixture_label":"FICTITIOUS_OPERATOR_METADATA_ONLY"}))
        controls[case]={"path":normalize_path(str(path)),"sha256":file_hash(path)}
    binding=placement["binding"]; metaeditor=normalize_path(node["terminals"][0].metaeditor_path)
    include=Path(binding["data_root"])/"MQL5/Include"; include.mkdir(parents=True)
    agents=Path(binding["data_root"])/"Tester"; agents.mkdir()
    install={"authority_root":normalize_path(str(root)),"target":placement["target"],"binding":binding,
        "metaeditor":metaeditor,"terminal_build":6230,"compiler_build":6230,
        "binary_hashes":{binding["executable"]:file_hash(binding["executable"]),metaeditor:file_hash(metaeditor)},
        "python":normalize_path(str(Path(sys.executable).resolve())),"python_sha256":file_hash(Path(sys.executable).resolve()),
        "windows_build":26000,"session_id":1,"gateway_public_key":"a"*64,"gateway_audience":"https://fixture-node:8443",
        "include_root":normalize_path(str(include)),"agent_root":normalize_path(str(agents))}
    body={"schema":"fleet.native.operator-approval/1","scope":"DEDICATED_TESTER_SYNC_OWNED",
        "approved_at_ms":1000,"expires_at_ms":2000,"payload":payload,"installation":install,"controls":controls,
        "policy":{"compile_timeout_seconds":10,"test_timeout_seconds":20,"resource_max_records":32,"resource_wait_ms":50}}
    def sign(value): return {"body":value,"signature":key.sign(DOMAIN+canonical(value)).hex()}
    raw=node["source"].read_bytes()
    request=native_request(placement,logical_fixture(),[{"path":"Experts/DemoEA.mq5","sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}])
    return {"node":node,"body":body,"envelope":sign(body),"sign":sign,"public":public,"payload":payload,"request":request,"sign_runtime":lambda value:{"body":value,"signature":key.sign(RUNTIME_DOMAIN+canonical(value)).hex()}}


def test_verified_signature_metadata_does_not_activate_nonwindows_runtime(approval_fixture):
    fixture=approval_fixture
    assert validate_approval(fixture["envelope"],fixture["public"],expected_payload=fixture["payload"],now_ms=1001)==fixture["body"]
    if os.name=="nt": return  # Installed binary versions still fixture bytes, never approved real effects.
    root=fixture["node"]["root"]
    (root/"config/fleet-native-trust.json").write_bytes(canonical({"schema":"fleet.native.trust/1","operator_public_key":fixture["public"]}))
    (root/"state/fleet/native-qualification.json").write_bytes(canonical(fixture["envelope"]))
    with pytest.raises(QualificationError,match="^NATIVE_QUALIFICATION_UNAVAILABLE$"):
        load_installation(root,fixture["request"],now_ms=1001)


@pytest.mark.parametrize("mutation", [lambda body: body["installation"].update(session_id=0),
    lambda body: body["installation"].update(terminal_build=True),
    lambda body: body["installation"]["target"].pop("route_generation"),
    lambda body: body["policy"].update(test_timeout_seconds=0),
    lambda body: body.update(scope="SYNTHETIC_NATIVE_ONLY"),
    lambda body: body["controls"].pop("PARENT_CRASH"),
    lambda body: body.update(unknown_qualified=True)])
def test_signed_but_incomplete_or_invalid_physical_contract_is_denied(approval_fixture,mutation):
    fixture=approval_fixture; body=copy.deepcopy(fixture["body"]); mutation(body)
    with pytest.raises(QualificationError,match="^NATIVE_QUALIFICATION_UNAVAILABLE$"):
        validate_approval(fixture["sign"](body),fixture["public"],expected_payload=fixture["payload"],now_ms=1001)


@pytest.mark.parametrize("fault",["wrong_signer","signature_tamper","expiry","binary_drift","synthetic_control"])
def test_operator_provenance_expiry_runtime_and_fixture_claim_cannot_enable_native(approval_fixture,fault):
    fixture=approval_fixture; envelope=copy.deepcopy(fixture["envelope"]); public=fixture["public"]; now=1001
    if fault=="wrong_signer": public="b"*64
    elif fault=="signature_tamper": envelope["signature"]="0"*128
    elif fault=="expiry": now=2000
    elif fault=="binary_drift": Path(fixture["body"]["installation"]["binding"]["executable"]).write_bytes(b"SYNTHETIC_BINARY_DRIFT")
    else:
        receipt=fixture["body"]["controls"]["EXACT_CLEANUP"]
        path=Path(receipt["path"]); value=json.loads(path.read_bytes()); value["evidence"]="SYNTHETIC_NATIVE_ONLY"; path.write_bytes(canonical(value))
        envelope["body"]["controls"]["EXACT_CLEANUP"]["sha256"]=file_hash(path); envelope=fixture["sign"](envelope["body"])
    with pytest.raises(QualificationError,match="^NATIVE_QUALIFICATION_UNAVAILABLE$"):
        validate_approval(envelope,public,expected_payload=fixture["payload"],now_ms=now)


@pytest.fixture
def shared_runtime_fixture(approval_fixture):
    fixture=approval_fixture; body=fixture["body"]; first=body["installation"]
    rows=[]
    for index,terminal in enumerate(fixture["node"]["terminals"]):
        identity=fixture["node"]["registry"]["terminals"][index]
        binding={"executable":identity["binding"]["terminal_canonical_path"],"data_root":identity["binding"]["data_canonical_path"]}
        include=Path(binding["data_root"])/"MQL5/Include"; include.mkdir(parents=True,exist_ok=True)
        agent=Path(binding["data_root"])/"Tester"; agent.mkdir(exist_ok=True)
        editor=normalize_path(terminal.metaeditor_path)
        rows.append({"terminal_id":identity["terminal_id"],"terminal_generation":identity["terminal_generation"],
            "binding":binding,"metaeditor":editor,"binary_hashes":{binding["executable"]:file_hash(binding["executable"]),editor:file_hash(editor)},
            "terminal_build":6230,"compiler_build":6230,"include_root":normalize_path(str(include)),"agent_root":normalize_path(str(agent))})
    runtime={"schema":"fleet.native.runtime/1",**{k:first[k] for k in ("authority_root","python","python_sha256","windows_build","session_id")},
        "candidate_sha256":hashlib.sha256(canonical(fixture["payload"])).hexdigest(),"payload":fixture["payload"],"terminals":rows}
    return fixture,runtime


def test_signed_shared_runtime_has_two_exact_target_approvals_and_deterministic_selection(shared_runtime_fixture):
    fixture,runtime=shared_runtime_fixture
    verified=validate_runtime(fixture["sign_runtime"](runtime),fixture["public"],root=fixture["node"]["root"],expected_payload=fixture["payload"])
    assert len(verified["terminals"])==2
    assert scoped_installation_match(fixture["body"],verified)==runtime["terminals"][0]
    other=copy.deepcopy(fixture["body"])
    row=runtime["terminals"][1]
    other["installation"].update({k:row[k] for k in ("binding","metaeditor","binary_hashes","terminal_build","compiler_build","include_root","agent_root")})
    other["installation"]["target"].update(terminal_id=row["terminal_id"],terminal_generation=row["terminal_generation"])
    assert scoped_installation_match(other,verified)==row
    paths=[qualification_path(fixture["node"]["root"],body["installation"]["target"],scoped=True) for body in (fixture["body"],other)]
    assert paths[0]!=paths[1] and all(path.parent.name=="native-qualifications" for path in paths)
    assert qualification_path(fixture["node"]["root"],other["installation"]["target"],scoped=False).name=="native-qualification.json"


@pytest.mark.parametrize("fault",["duplicate_id","duplicate_physical","candidate_drift","runtime_drift","approval_mismatch","signature_tamper"])
def test_shared_runtime_duplicates_drift_and_cross_target_approval_never_qualify(shared_runtime_fixture,fault):
    fixture,runtime=shared_runtime_fixture; runtime=copy.deepcopy(runtime)
    if fault=="duplicate_id":runtime["terminals"][1]["terminal_id"]=runtime["terminals"][0]["terminal_id"]
    elif fault=="duplicate_physical":runtime["terminals"][1]["binding"]=runtime["terminals"][0]["binding"]
    elif fault=="candidate_drift":runtime["candidate_sha256"]="0"*64
    elif fault=="runtime_drift":Path(runtime["terminals"][1]["metaeditor"]).write_bytes(b"SYNTHETIC_RUNTIME_DRIFT")
    elif fault=="approval_mismatch":
        other=copy.deepcopy(fixture["body"]); other["installation"]["target"]["terminal_generation"]+=1
        with pytest.raises(QualificationError):scoped_installation_match(other,runtime)
        return
    envelope=fixture["sign_runtime"](runtime)
    if fault=="signature_tamper":envelope["signature"]="0"*128
    with pytest.raises(QualificationError):validate_runtime(envelope,fixture["public"],root=fixture["node"]["root"],expected_payload=fixture["payload"])


def test_scoped_missing_exact_approval_never_falls_back_to_singleton(approval_fixture):
    fixture=approval_fixture; root=fixture["node"]["root"]
    (root/"config/fleet-native-trust.json").write_bytes(canonical({"schema":"fleet.native.trust/1","operator_public_key":fixture["public"]}))
    (root/"state/fleet/native-qualification.json").write_bytes(canonical(fixture["envelope"]))
    (root/"state/fleet/scoped-install.json").write_bytes(b"PRIVATE_MISSING_RECORD_CASE")
    with pytest.raises(QualificationError):load_installation(root,fixture["request"],now_ms=1001)
    assert not qualification_path(root,fixture["request"]["placement"]["target"],scoped=True).exists()


@pytest.mark.skipif(os.name=="nt",reason="POSIX_PERMISSIONS_ONLY; Windows retained-handle ACL gate separate")
@pytest.mark.parametrize("fault",["writable_trust","public_approval","symlink_trust"])
def test_installed_trust_and_approval_require_protected_owner_files(approval_fixture,fault):
    from vibemql5.fleet.native_qualification import _read_installed
    fixture=approval_fixture;root=fixture["node"]["root"]
    trust=root/"config/fleet-native-trust.json";approval=root/"state/fleet/native-qualification.json"
    trust.write_bytes(canonical({"schema":"fleet.native.trust/1","operator_public_key":fixture["public"]}));trust.chmod(0o600)
    approval.write_bytes(canonical(fixture["envelope"]));approval.chmod(0o600)
    assert _read_installed(trust)["operator_public_key"]==fixture["public"]
    assert _read_installed(approval)==fixture["envelope"]
    if fault=="writable_trust":trust.chmod(0o666);path=trust
    elif fault=="public_approval":approval.chmod(0o644);path=approval
    else:
        alternate=root/"config/alternate-native-trust.json";trust.rename(alternate);trust.symlink_to(alternate);path=trust
    with pytest.raises(QualificationError,match="^NATIVE_QUALIFICATION_UNAVAILABLE$"):_read_installed(path)
