"""Bounded canonical wire controls for plain strings and custom iteration."""
import hashlib
import json

import pytest

from vibemql5.fleet.wire import WireError, decode_body, encode_body, logical_digest


def invalid(callback, value, code="WIRE_INVALID"):
    with pytest.raises(WireError) as caught:
        callback(value)
    assert caught.value.code == code


def test_canonical_ascii_and_unicode_boundaries_roundtrip_and_digest():
    value = {"ascii": ["", "plain", "\x00\x7f"],
             "unicode": ["tiếng Việt", "\ud7ff", "\ue000", "\U0010ffff"],
             "键": {"value": "\U0001f600"}}
    expected = (b'{"ascii":["","plain","\\u0000\\u007f"],'
                b'"unicode":["ti\\u1ebfng Vi\\u1ec7t","\\ud7ff","\\ue000","\\udbff\\udfff"],'
                b'"\\u952e":{"value":"\\ud83d\\ude00"}}')
    assert encode_body(value, len(expected)) == expected
    assert decode_body(expected, len(expected)) == value
    assert logical_digest(value) == hashlib.sha256(expected).hexdigest()


def test_surrogates_at_each_position_and_nested_key_or_value_are_rejected():
    for surrogate in ("\ud800", "\udbff", "\udc00", "\udfff"):
        for text in (surrogate + "after", "before" + surrogate + "after", "before" + surrogate):
            for value in ({"outer": [{"value": text}]}, {text: "ordinary"}):
                invalid(lambda item: encode_body(item, 4096), value)
                invalid(logical_digest, value)
                body = json.dumps(value, ensure_ascii=True).encode("ascii")
                invalid(lambda item: decode_body(item, 4096), body)


def test_scalar_types_numbers_and_finite_container_limits():
    for value in (float("nan"), float("inf"), float("-inf"), 1 << 63, (), object(), {1: "value"}):
        invalid(lambda item: encode_body(item, 4096), value)
        invalid(logical_digest, value)
    valid = {"values": [None, True, False, -(1 << 63) + 1, (1 << 63) - 1, .25]}
    body = encode_body(valid, 4096)
    assert decode_body(body, 4096) == valid
    assert logical_digest(valid) == hashlib.sha256(body).hexdigest()
    assert encode_body([None] * 10000, 50001) == b"[" + b"null," * 9999 + b"null]"
    invalid(lambda item: encode_body(item, 50006), [None] * 10001)
    at_limit = None
    for _ in range(32):
        at_limit = [at_limit]
    assert encode_body(at_limit, 68) == b"[" * 32 + b"null" + b"]" * 32
    invalid(logical_digest, [at_limit])


def test_decode_and_encode_size_and_invalid_json_controls():
    body = b'{"value":"ascii"}'
    assert encode_body({"value": "ascii"}, len(body)) == body
    invalid(lambda item: encode_body(item, len(body) - 1), {"value": "ascii"}, "WIRE_TOO_LARGE")
    invalid(lambda item: decode_body(item, len(body) - 1), body, "WIRE_TOO_LARGE")
    for raw in (b'{"a":"\\ud800"}', b'{"a":NaN}', b'{"a":1,"a":2}', b'{"a":"\xff"}', b'[]'):
        invalid(lambda item: decode_body(item, 4096), raw)


def test_ascii_str_subclass_keeps_its_custom_surrogate_iteration():
    class SurrogateIteration(str):
        def __iter__(self):
            return iter("\ud800")

    value = SurrogateIteration("ordinary")
    invalid(lambda item: encode_body(item, 4096), value)
    invalid(logical_digest, value)


def test_nonascii_str_subclass_keeps_its_custom_ordinary_iteration():
    class OrdinaryIteration(str):
        def __iter__(self):
            return iter("ordinary")

    value = OrdinaryIteration("\ud800")
    expected = b'"\\ud800"'
    assert encode_body(value, 4096) == expected
    assert logical_digest(value) == hashlib.sha256(expected).hexdigest()
    invalid(lambda item: decode_body(item, 4096), b'{"value":' + expected + b'}')


def test_str_subclass_iteration_error_is_preserved_without_ascii_method_call():
    error = RuntimeError("owned iteration failure")

    class RaisingIteration(str):
        def isascii(self):
            raise AssertionError("subclass predicate must not run")

        def __iter__(self):
            raise error

    for callback in (lambda item: encode_body(item, 4096), logical_digest):
        with pytest.raises(RuntimeError) as caught:
            callback(RaisingIteration("ordinary"))
        assert caught.value is error
