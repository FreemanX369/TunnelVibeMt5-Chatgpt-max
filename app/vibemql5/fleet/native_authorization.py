"""Signed gateway authorization for one exact native phase and journal sequence."""
from __future__ import annotations

import copy
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .job_journal import JournalError, canonical, digest, target as validate_target, _id, _integer

DOMAIN = b"fleet.native.authorization/1\n"
PHASES = {"reserve", "deploy", "start", "test", "capture", "cancel", "result"}
FIELDS = {"audience", "request_sha256", "target", "phase", "node_operation_id", "global_job_id",
          "local_job_id", "session_id", "sequence", "challenge", "event", "process_sha256"}
_SEAL = object()

# These events come only from the installed finite native producer. The ranks
# allow bounded interleaved copies and report targets, without a caller worker.
EVENTS = {
    "snapshot_prepare": ("deploy", 1, 1), "compile_run_prepare": ("deploy", 2, 1),
    "deploy_source_prepare": ("deploy", 3, 1), "deploy_source_copy": ("deploy", 4, 1),
    "deploy_include_prepare": ("deploy", 5, 1025), "deploy_include_copy": ("deploy", 5, 1024),
    "compile_output_reset": ("deploy", 6, 2), "process_create": (None, 7, 1),
    "process_resume": (None, 8, 1), "compile_log_capture": ("capture", 9, 1),
    "compile_ex5_capture": ("capture", 10, 1), "compile_result_publish": ("deploy", 11, 1),
    "tester_run_prepare": ("test", 12, 1), "tester_set_prepare": ("test", 13, 2),
    "tester_set_copy": ("test", 13, 2), "tester_report_prepare": ("test", 14, 14),
    "tester_report_reset": ("test", 14, 14), "tester_ini_prepare": ("test", 15, 1),
    "tester_capture": ("capture", 18, 100000), "tester_terminate": ("cancel", 19, 1),
    "tester_report_capture": ("capture", 20, 1), "tester_result_publish": ("test", 21, 1),
    "owned_terminate": ("cancel", 0, 1), "compiler_terminate": ("cancel", 0, 1),
    "result_promote": ("result", 22, 1),
}


def effect_event(phase, event):
    if event == "phase_admission":
        if phase not in PHASES: raise JournalError("NATIVE_EFFECT_EVENT_INVALID")
        return None
    if not isinstance(event, str) or len(event) > 64:
        raise JournalError("NATIVE_EFFECT_EVENT_INVALID")
    match = re.fullmatch(r"([a-z_]+):([0-9]{4,6})", event)
    if match is None or match[1] not in EVENTS:
        raise JournalError("NATIVE_EFFECT_EVENT_INVALID")
    base, ordinal = match[1], int(match[2]); expected, rank, limit = EVENTS[base]
    if ordinal < 1 or ordinal > limit or event != base + ":" + str(ordinal).zfill(4):
        raise JournalError("NATIVE_EFFECT_EVENT_INVALID")
    if base in {"process_create", "process_resume"}:
        if phase not in {"deploy", "test"}: raise JournalError("NATIVE_EFFECT_EVENT_INVALID")
        rank += 9 if phase == "test" else 0
    elif phase != expected:
        raise JournalError("NATIVE_EFFECT_EVENT_INVALID")
    return {"base": base, "ordinal": ordinal, "rank": rank,
            "lane": "cancel" if base in {"owned_terminate", "compiler_terminate"} else "native"}


def completion_receipt(value):
    fields = {"schema", "grant_sha256", "phase", "event", "sequence", "challenge", "outcome", "evidence"}
    if (not isinstance(value, dict) or set(value) != fields
            or value["schema"] != "fleet.native-effect-completion/1"
            or value["outcome"] not in {"COMPLETED", "NOT_ATTEMPTED"}
            or len(canonical(value)) > 2048):
        raise JournalError("NATIVE_EFFECT_COMPLETION_INVALID")
    effect_event(value["phase"], value["event"]); _integer(value["sequence"])
    evidence = value["evidence"]
    if (not isinstance(evidence, dict) or set(evidence) != {"kind", "sha256"}
            or evidence["kind"] not in {"PRODUCER_RETURNED", "NO_NATIVE_ATTEMPT"}
            or (value["outcome"] == "NOT_ATTEMPTED") != (evidence["kind"] == "NO_NATIVE_ATTEMPT")
            or not isinstance(evidence["sha256"], str) or re.fullmatch(r"[a-f0-9]{64}", evidence["sha256"]) is None
            or not isinstance(value["grant_sha256"], str) or re.fullmatch(r"[a-f0-9]{64}", value["grant_sha256"]) is None
            or not isinstance(value["challenge"], str) or re.fullmatch(r"[a-f0-9]{32}", value["challenge"]) is None):
        raise JournalError("NATIVE_EFFECT_COMPLETION_INVALID")
    return copy.deepcopy(value)


def advance_effect(history, phase, event):
    current = effect_event(phase, event)
    if current is None: return
    parsed = [(row, effect_event(row["phase"], row["event"])) for row in history]
    same = [row for row, item in parsed if item["lane"] == current["lane"]]
    previous = [item for _row, item in parsed if item["lane"] == current["lane"]]
    count = sum(row["phase"] == phase and item["base"] == current["base"] for row, item in parsed)
    if current["ordinal"] != count + 1 or (previous and current["rank"] < previous[-1]["rank"]):
        raise JournalError("NATIVE_EFFECT_GRAPH_INVALID")
    if not previous and current["lane"] == "native" and current["base"] != "snapshot_prepare":
        raise JournalError("NATIVE_EFFECT_GRAPH_INVALID")
    if same and same[-1].get("completion") is None:
        raise JournalError("NATIVE_EFFECT_UNRESOLVED")


def _binding(value):
    if isinstance(value, dict) and set(value) <= FIELDS and FIELDS - set(value) <= {"event", "process_sha256"}:
        value = {"event": "phase_admission", "process_sha256": None, **value}
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise JournalError("NATIVE_AUTHORIZATION_INVALID")
    validate_target(value["target"])
    if value["phase"] not in PHASES:
        raise JournalError("NATIVE_AUTHORIZATION_INVALID")
    effect_event(value["phase"], value["event"])
    if value["phase"] == "cancel":
        if not isinstance(value["process_sha256"], str) or re.fullmatch(r"[a-f0-9]{64}", value["process_sha256"]) is None:
            raise JournalError("NATIVE_AUTHORIZATION_INVALID")
    elif value["process_sha256"] is not None:
        raise JournalError("NATIVE_AUTHORIZATION_INVALID")
    for name in ("node_operation_id", "global_job_id", "local_job_id", "session_id"):
        _id(value[name])
    _integer(value["sequence"])
    if (not isinstance(value["audience"], str) or not value["audience"] or len(value["audience"]) > 256
            or not value["audience"].isascii() or any(c in value["audience"] for c in "\n\r\0")
            or not isinstance(value["request_sha256"], str) or re.fullmatch(r"[a-f0-9]{64}", value["request_sha256"]) is None
            or not isinstance(value["challenge"], str) or re.fullmatch(r"[a-f0-9]{32}", value["challenge"]) is None):
        raise JournalError("NATIVE_AUTHORIZATION_INVALID")
    return copy.deepcopy(value)


class NativeAuthorization:
    __slots__ = ("_body", "_clock", "_seal", "_signer_public_key", "_grant_sha256")

    def __init__(self, body, clock, seal, signer_public_key, grant_sha256=None):
        if seal is not _SEAL:
            raise JournalError("NATIVE_AUTHORIZATION_UNVERIFIED")
        self._body, self._clock, self._seal = copy.deepcopy(body), clock, seal
        self._signer_public_key = signer_public_key
        self._grant_sha256 = grant_sha256

    @property
    def signer_public_key(self):
        return self._signer_public_key

    @property
    def audience(self):
        return self._body["audience"]

    @property
    def binding(self):
        return {k: copy.deepcopy(self._body[k]) for k in FIELDS}

    @property
    def grant_sha256(self):
        return self._grant_sha256

    def require(self, **expected):
        if self._seal is not _SEAL or _binding(expected) != {k: self._body[k] for k in FIELDS}:
            raise JournalError("NATIVE_AUTHORIZATION_MISMATCH")
        now = self._clock()
        _integer(now, positive=False)
        if not self._body["issued_ms"] <= now < self._body["expires_ms"]:
            raise JournalError("NATIVE_AUTHORIZATION_EXPIRED")
        return copy.deepcopy(self._body)


class NativeAuthorizationVerifier:
    def __init__(self, public_key_hex, audience, *, clock_ms):
        try:
            if not isinstance(public_key_hex, str) or re.fullmatch(r"[a-f0-9]{64}", public_key_hex) is None:
                raise ValueError()
            self.key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        except (ValueError, TypeError):
            raise JournalError("NATIVE_AUTHORIZATION_TRUST_INVALID") from None
        if not callable(clock_ms) or not isinstance(audience, str) or not audience:
            raise JournalError("NATIVE_AUTHORIZATION_TRUST_INVALID")
        self.audience, self.clock = audience, clock_ms
        self.public_key = public_key_hex

    def verify(self, grant, **expected):
        expected = _binding(expected)
        try:
            if (not isinstance(grant, dict) or set(grant) != {"body", "signature"}
                    or not isinstance(grant["signature"], str) or re.fullmatch(r"[a-f0-9]{128}", grant["signature"]) is None):
                raise ValueError()
            body = grant["body"]
            if (not isinstance(body, dict) or set(body) != FIELDS | {"schema", "authorization_id", "issued_ms", "expires_ms"}
                    or body["schema"] != "fleet.native.authorization/1" or body["audience"] != self.audience):
                raise ValueError()
            self.key.verify(bytes.fromhex(grant["signature"]), DOMAIN + canonical(body))
            _id(body["authorization_id"]); _integer(body["issued_ms"], positive=False); _integer(body["expires_ms"])
            if body["expires_ms"] <= body["issued_ms"]:
                raise ValueError()
            proof = NativeAuthorization(body, self.clock, _SEAL, self.public_key, digest(grant))
            proof.require(**expected)
            return proof
        except (ValueError, TypeError, KeyError, InvalidSignature):
            raise JournalError("NATIVE_AUTHORIZATION_UNVERIFIED") from None


class GatewayNativeSigner:
    def __init__(self, private_key, audience, *, max_authorization_ms):
        if not isinstance(private_key, Ed25519PrivateKey):
            raise JournalError("NATIVE_SIGNING_KEY_INVALID")
        _integer(max_authorization_ms)
        if max_authorization_ms > 30000:
            raise JournalError("NATIVE_AUTHORIZATION_POLICY_INVALID")
        self.key, self.audience, self.max_ms = private_key, audience, max_authorization_ms

    def issue(self, *, issued_ms, expires_ms, authorization_id, **binding):
        binding = _binding(binding)
        _integer(issued_ms, positive=False); _integer(expires_ms); _id(authorization_id)
        if binding["audience"] != self.audience or not issued_ms < expires_ms <= issued_ms + self.max_ms:
            raise JournalError("NATIVE_AUTHORIZATION_POLICY_INVALID")
        body = {"schema": "fleet.native.authorization/1", "authorization_id": authorization_id,
                "issued_ms": issued_ms, "expires_ms": expires_ms, **binding}
        return {"body": body, "signature": self.key.sign(DOMAIN + canonical(body)).hex()}
