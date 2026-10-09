"""Compare actual parent and fixed modules, fresh owned hashes, and finite cost."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sqlite3
import statistics
import sys
import time

from vibemql5.fleet import wire

OUT = Path(__file__).parent
BASE = OUT.parents[1]
PARENT = BASE / 'tip073-candidate/app/vibemql5/fleet/wire.py'
spec = importlib.util.spec_from_file_location('owned_parent_wire', PARENT)
parent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = parent
spec.loader.exec_module(parent)

class RetainedIteration(str):
    def __iter__(self):
        return iter('\ud800')

class OrdinaryIteration(str):
    def __iter__(self):
        return iter('ordinary')

class RaisingIteration(str):
    error = RuntimeError('owned iteration failure')
    def isascii(self):
        raise AssertionError('subclass predicate must not run')
    def __iter__(self):
        raise self.error

controls = [None, True, False, 0, (1 << 63) - 1, 1 << 63, .25, float('inf'), float('nan'),
            '', 'ordinary-ascii', 'tiếng Việt', chr(0xD7FF), chr(0xE000), chr(0x10FFFF),
            chr(0xD800), chr(0xDBFF), chr(0xDC00), chr(0xDFFF), 'prefix\ud800suffix',
            {'x': ['ordinary', 'tiếng Việt']}, {'\ud800': 1}, {'x': '\udfff'},
            RetainedIteration('ordinary'), OrdinaryIteration('\ud800'), (), object(),
            ['x'] * 10001]
deep = None
for _ in range(34):
    deep = [deep]
controls.append(deep)
controls.append(RaisingIteration('ordinary'))

def observe(callback, value, module):
    try:
        result = callback(value)
    except module.WireError as error:
        return {'error_type': type(error).__name__, 'error_code': error.code, 'message': str(error)}
    except RuntimeError as error:
        assert error is RaisingIteration.error
        return {'error_type': type(error).__name__, 'message': str(error), 'original_error_identity': True}
    if type(result) is bytes:
        return {'bytes_hex': result.hex(), 'bytes': len(result), 'sha256': hashlib.sha256(result).hexdigest()}
    return {'result': result}

results = []
for ordinal, value in enumerate(controls):
    before_bytes = observe(lambda item: parent.encode_body(item, (1 << 31) - 1), value, parent)
    after_bytes = observe(lambda item: wire.encode_body(item, (1 << 31) - 1), value, wire)
    before_digest = observe(parent.logical_digest, value, parent)
    after_digest = observe(wire.logical_digest, value, wire)
    assert before_bytes == after_bytes and before_digest == after_digest
    # The first 29 are exactly the external prototype controls; ordinal 30 adds exception identity.
    results.append({'ordinal': ordinal + 1, 'parent_bytes': before_bytes, 'fixed_bytes': after_bytes,
                    'parent_digest': before_digest, 'fixed_digest': after_digest})

# Observe actual decoding errors and valid canonical bytes too; no behavior cloning.
raws = [b'{"v":"ascii"}', b'{"v":"\\ud7ff\\ue000\\udbff\\udfff"}',
        b'{"v":"\\ud800"}', b'{"v":NaN}', b'{"v":1,"v":2}', b'[]', b'{"v":"\xff"}']
decode_rows = []
for ordinal, raw in enumerate(raws):
    def decoded(module):
        try:
            value = module.decode_body(raw, 4096)
            return {'canonical_hex': module.encode_body(value, 4096).hex(), 'digest': module.logical_digest(value)}
        except module.WireError as error:
            return {'error_type': type(error).__name__, 'error_code': error.code, 'message': str(error)}
    before, after = decoded(parent), decoded(wire)
    assert before == after
    decode_rows.append({'ordinal': ordinal + 1, 'input_hex': raw.hex(), 'parent': before, 'fixed': after})

paths = list((BASE / 'deepfix-20261007-1903/runtime-cost-builder/actual-owned-cost-tmp').rglob('node-transport.sqlite'))
assert len(paths) == 1
with sqlite3.connect('file:' + str(paths[0]) + '?mode=ro', uri=True) as db:
    rows = db.execute('SELECT intent,request_sha256 FROM requests').fetchall()
actual = [json.loads(row[0]) for row in rows]
assert len(actual) == 247
intent_rows = []
for ordinal, (value, row) in enumerate(zip(actual, rows)):
    before, after = parent.encode_body(value, (1 << 31) - 1), wire.encode_body(value, (1 << 31) - 1)
    digest_before, digest_after = parent.logical_digest(value), wire.logical_digest(value)
    assert before == after and digest_before == digest_after == row[1]
    intent_rows.append({'ordinal': ordinal + 1, 'canonical_bytes': len(before),
                        'parent_digest': digest_before, 'fixed_digest': digest_after, 'stored_digest': row[1],
                        'exact_canonical_bytes_equal': True})

def elapsed(callback):
    begun = time.monotonic()
    for _ in range(4):
        for value in actual:
            callback(value)
    return time.monotonic() - begun

timings = []
for iteration in range(6):
    if iteration % 2:
        after, before = elapsed(wire.logical_digest), elapsed(parent.logical_digest)
    else:
        before, after = elapsed(parent.logical_digest), elapsed(wire.logical_digest)
    timings.append({'iteration': iteration + 1, 'parent_seconds': before,
                    'fixed_seconds': after, 'ratio': before / after})
receipt = {'schema': 'actual-source-plainstr-ascii/1', 'parent': 'ef31be719b090c14effa96e69c08d405ac0ceceb',
           'physical_windows': 'NOT_RUN', 'parent_source_sha256': hashlib.sha256(PARENT.read_bytes()).hexdigest(),
           'fixed_source_sha256': hashlib.sha256(Path(wire.__file__).read_bytes()).hexdigest(),
           'controls': results, 'decode_controls': decode_rows, 'actual_intent_rows': intent_rows,
           'fresh_actual_intent_hashes_identical': True, 'exact_actual_canonical_bytes_equal': True,
           'benchmark_per_side_per_iteration': len(actual) * 4, 'timings': timings,
           'median_ratio': statistics.median(row['ratio'] for row in timings),
           'limitations': ['Linux finite microbenchmark; no physical Windows cause or CI gate qualification.',
                           'Every input read from the original owned journal afresh; source production queries unchanged.']}
(OUT / 'actual-source-equivalence.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({'controls': len(controls), 'decode_controls': len(decode_rows), 'intent_rows': len(actual),
                  'median_ratio': receipt['median_ratio'], 'exact_bytes_and_errors_equal': True}))
