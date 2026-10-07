"""Isolated scalar scan prototype; actual fresh intent hashes remain identical."""
from pathlib import Path
import hashlib
import inspect
import json
import re
import sqlite3
import statistics
import time

from vibemql5.fleet import wire

OUT = Path(__file__).parent
tree_source = inspect.getsource(wire._tree)
needle = 'any(0xD800 <= ord(char) <= 0xDFFF for char in value)'
assert tree_source.count(needle) == 1
prototype_source = tree_source.replace(needle,
    '(_surrogate.search(value) is not None if type(value) is str else ' + needle + ')')
namespace = dict(wire.__dict__, _surrogate=re.compile(r'[\ud800-\udfff]'))
exec(compile(prototype_source, 'owned-scalar-prototype', 'exec'), namespace)
exec(compile(inspect.getsource(wire.encode_body), 'owned-encode-prototype', 'exec'), namespace)
exec(compile(inspect.getsource(wire.logical_digest), 'owned-digest-prototype', 'exec'), namespace)
prototype_tree, prototype_digest = namespace['_tree'], namespace['logical_digest']

class RetainedIteration(str):
    def __iter__(self):
        return iter('\ud800')

class OrdinaryIteration(str):
    def __iter__(self):
        return iter('ordinary')

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

def observe(callback, value):
    try:
        result = callback(value)
    except wire.WireError as error:
        return 'ERROR:' + error.code
    else:
        return 'RETURNED:' + str(result)

results = []
for ordinal, value in enumerate(controls):
    original, proposed = observe(wire.logical_digest, value), observe(prototype_digest, value)
    assert original == proposed
    results.append({'ordinal': ordinal + 1, 'original': original, 'prototype': proposed})

paths = list((OUT / 'actual-owned-cost-tmp').rglob('node-transport.sqlite'))
assert len(paths) == 1
with sqlite3.connect('file:' + str(paths[0]) + '?mode=ro', uri=True) as db:
    rows = db.execute('SELECT intent,request_sha256 FROM requests').fetchall()
actual = [json.loads(row[0]) for row in rows]
assert actual
for value, row in zip(actual, rows):
    assert wire.logical_digest(value) == prototype_digest(value) == row[1]

def elapsed(callback, repeats=4):
    begun = time.monotonic()
    for _ in range(repeats):
        for value in actual:
            callback(value)
    return time.monotonic() - begun

timings = []
for iteration in range(6):
    if iteration % 2:
        proposed, original = elapsed(prototype_digest), elapsed(wire.logical_digest)
    else:
        original, proposed = elapsed(wire.logical_digest), elapsed(prototype_digest)
    timings.append({'iteration': iteration + 1, 'original_seconds': original,
                    'prototype_seconds': proposed, 'ratio': original / proposed})
receipt = {'schema': 'owned-plain-string-scan/1', 'physical_windows': 'NOT_RUN',
           'production_source_changed': False, 'controls': results, 'actual_intent_rows': len(actual),
           'fresh_actual_intent_hashes_identical': True, 'benchmark_per_side_per_iteration': len(actual) * 4,
           'timings': timings, 'median_ratio': statistics.median(row['ratio'] for row in timings),
           'original_function_sha256': hashlib.sha256(tree_source.encode()).hexdigest(),
           'isolated_prototype_source': prototype_source,
           'limitations': ['Hashes operate on freshly-read owned intents; no ledger result is cached.',
                           'Microbenchmark is Linux only and does not establish the original Windows cause.',
                           'End-to-end profile must be independently measured before shipping a correction.']}
(OUT / 'unicode-tree-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({key: value for key, value in receipt.items()
                  if key in ('actual_intent_rows', 'median_ratio', 'fresh_actual_intent_hashes_identical')}))
