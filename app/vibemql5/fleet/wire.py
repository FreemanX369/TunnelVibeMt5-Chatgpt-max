"""Finite Ed25519 node wire protocol. In-process proofs are never deserialized."""
from __future__ import annotations

import hashlib
import ipaddress
import base64
import json
import math
import re
from dataclasses import dataclass
from urllib.parse import urlsplit
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

PATHS = frozenset({"/fleet/v1/pair", "/fleet/v1/heartbeat", "/fleet/v1/poll", "/fleet/v1/results", "/fleet/v1/native/start", "/fleet/v1/reconcile", "/fleet/v1/read-authorize", "/fleet/v1/writers/authorize", "/fleet/v1/capacity/register", "/fleet/v1/jobs/recovery-witness"})
HEADERS = ("x-vibe-device", "x-vibe-key", "x-vibe-route", "x-vibe-time", "x-vibe-nonce", "x-vibe-signature")
_DEVICE = re.compile(r"dev_[0-9a-f]{32}\Z")
_KEY = re.compile(r"[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[0-9a-f]{32,128}\Z")
_NUMBER = re.compile(r"0|[1-9][0-9]{0,18}\Z")
_SEAL = object()


class WireError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def integer(value, *, minimum=0, maximum=(1 << 63) - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise WireError("WIRE_INVALID")
    return value


def fields(value, required):
    if type(value) is not dict or set(value) != set(required):
        raise WireError("WIRE_INVALID")
    return value


def text(value, maximum):
    if type(value) is not str or not value or value != value.strip() or any(ord(c) < 32 for c in value):
        raise WireError("WIRE_INVALID")
    try:
        if len(value.encode("utf-8")) > maximum:
            raise WireError("WIRE_TOO_LARGE")
    except UnicodeError:
        raise WireError("WIRE_INVALID") from None
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WireError("WIRE_INVALID")
        result[key] = value
    return result


def _tree(value, depth=0):
    if depth > 32:
        raise WireError("WIRE_INVALID")
    if isinstance(value, str):
        if not (type(value) is str and value.isascii()) and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise WireError("WIRE_INVALID")
    elif type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise WireError("WIRE_INVALID")
            _tree(key, depth + 1); _tree(child, depth + 1)
    elif type(value) is list:
        if len(value) > 10000:
            raise WireError("WIRE_INVALID")
        for child in value:
            _tree(child, depth + 1)
    elif type(value) in (int, float):
        try:
            if not math.isfinite(value) or abs(value) > (1 << 63) - 1:
                raise ValueError()
        except (ValueError, OverflowError):
            raise WireError("WIRE_INVALID") from None
    elif value is not None and type(value) is not bool:
        raise WireError("WIRE_INVALID")


def decode_body(body, maximum):
    if type(body) is not bytes or len(body) > maximum:
        raise WireError("WIRE_TOO_LARGE")
    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(WireError("WIRE_INVALID")))
        if type(value) is not dict:
            raise WireError("WIRE_INVALID")
        _tree(value)
        encode_body(value, maximum)
        return value
    except (UnicodeError, ValueError, RecursionError, TypeError):
        raise WireError("WIRE_INVALID") from None


def encode_body(value, maximum):
    _tree(value)
    try:
        body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                          allow_nan=False).encode("ascii")
    except (ValueError, TypeError, RecursionError):
        raise WireError("WIRE_INVALID") from None
    if len(body) > maximum:
        raise WireError("WIRE_TOO_LARGE")
    return body


def logical_digest(value):
    """Digest a finite logical request supplied by a domain adapter, never headers."""
    return hashlib.sha256(encode_body(value, (1 << 31) - 1)).hexdigest()


def https_origin(value):
    if type(value) is not str or len(value) > 512 or not value.isascii():
        raise WireError("WIRE_ORIGIN_INVALID")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                or "%" in parsed.netloc or parsed.hostname.endswith(".")):
            raise ValueError()
        port = parsed.port
        host = parsed.hostname.lower()
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        if ":" in host:
            ipaddress.IPv6Address(host)
            host = "[" + host + "]"
        elif len(host) > 253 or any(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is None for label in host.split(".")):
            raise ValueError()
        canonical = "https://" + host + (":" + str(port) if port is not None and port != 443 else "")
        if canonical != value:
            raise ValueError()
        return value
    except (ValueError, UnicodeError):
        raise WireError("WIRE_ORIGIN_INVALID") from None


def _canonical(method, path, body, device, key, route, timestamp, nonce, audience):
    https_origin(audience)
    if method != "POST" or path not in PATHS:
        raise WireError("WIRE_INVALID")
    if type(device) is not str or not _DEVICE.fullmatch(device) or type(key) is not str or not _KEY.fullmatch(key):
        raise WireError("WIRE_INVALID")
    integer(route); integer(timestamp)
    if (path != "/fleet/v1/pair" and route == 0) or type(nonce) is not str or not _NONCE.fullmatch(nonce):
        raise WireError("WIRE_INVALID")
    if type(body) is not bytes:
        raise WireError("WIRE_INVALID")
    return ("fleet.wire/1\n" + "\n".join((method, path, hashlib.sha256(body).hexdigest(),
            device, key, str(route), str(timestamp), nonce, audience)) + "\n").encode("ascii")


@dataclass(frozen=True, init=False)
class VerifiedNodeRequest:
    device_id: str
    public_key: str
    route_generation: int
    timestamp_ms: int
    nonce: str
    request_sha256: str
    path: str
    _body_bytes: bytes
    _max_body_bytes: int
    _audience: str
    _header_pairs: tuple
    _seal: object

    def __init__(self, *, _seal, **values):
        if _seal is not _SEAL:
            raise WireError("WIRE_UNVERIFIED")
        for name, value in {**values, "_seal": _seal}.items():
            object.__setattr__(self, name, value)


    def recovery_evidence(self):
        if self.path != "/fleet/v1/reconcile" or self._seal is not _SEAL:
            raise WireError("WIRE_RECOVERY_ONLY")
        return {"method": "POST", "path": self.path,
                "header_pairs": [list(pair) for pair in self._header_pairs],
                "body_base64": base64.b64encode(self._body_bytes).decode("ascii"),
                "audience": self._audience}

    @property
    def audience(self):
        return self._audience

    @property
    def body(self):
        # A fresh projection prevents mutation after signature verification from
        # changing the request admitted by the controller. Bytes are immutable.
        return decode_body(self._body_bytes, self._max_body_bytes)


def verified(value):
    return type(value) is VerifiedNodeRequest and value._seal is _SEAL


def sign_request(key, *, device_id, route_generation, timestamp_ms, nonce, path, body, audience):
    if not isinstance(key, Ed25519PrivateKey):
        raise WireError("WIRE_INVALID")
    public = key.public_key().public_bytes_raw().hex()
    canonical = _canonical("POST", path, body, device_id, public, route_generation, timestamp_ms, nonce, audience)
    return dict(zip(HEADERS, (device_id, public, str(route_generation), str(timestamp_ms), nonce,
                             key.sign(canonical).hex())))


def verify_request(method, path, header_pairs, body, *, audience, max_body_bytes, expected_public_key=None):
    headers = {}
    for name, value in header_pairs:
        name = name.lower()
        if name.startswith("x-vibe-"):
            if name not in HEADERS or name in headers:
                raise WireError("WIRE_INVALID")
            headers[name] = value
    if set(headers) != set(HEADERS):
        raise WireError("WIRE_INVALID")
    for name in ("x-vibe-route", "x-vibe-time"):
        if type(headers[name]) is not str or not _NUMBER.fullmatch(headers[name]):
            raise WireError("WIRE_INVALID")
    route, timestamp = int(headers["x-vibe-route"]), int(headers["x-vibe-time"])
    key, device, nonce = headers["x-vibe-key"], headers["x-vibe-device"], headers["x-vibe-nonce"]
    canonical = _canonical(method, path, body, device, key, route, timestamp, nonce, audience)
    signature = headers["x-vibe-signature"]
    if type(signature) is not str or re.fullmatch(r"[0-9a-f]{128}", signature) is None:
        raise WireError("WIRE_INVALID")
    if expected_public_key is not None and key != expected_public_key:
        raise WireError("WIRE_KEY_MISMATCH")
    parsed = decode_body(body, max_body_bytes)
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key)).verify(bytes.fromhex(signature), canonical)
    except (ValueError, InvalidSignature):
        raise WireError("WIRE_SIGNATURE_INVALID") from None
    return VerifiedNodeRequest(_seal=_SEAL, device_id=device, public_key=key,
        route_generation=route, timestamp_ms=timestamp, nonce=nonce,
        request_sha256=hashlib.sha256(canonical).hexdigest(), path=path,
        _body_bytes=body, _max_body_bytes=max_body_bytes,
        _audience=audience, _header_pairs=tuple((name, headers[name]) for name in HEADERS))
