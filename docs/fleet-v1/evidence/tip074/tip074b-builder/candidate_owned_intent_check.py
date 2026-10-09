"""Fresh read-only verification of actual fixed owned-run persisted intents."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sqlite3
import sys
from vibemql5.fleet import wire
OUT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('candidate_intent_parent', OUT.parents[1] / 'tip073-candidate/app/vibemql5/fleet/wire.py')
parent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = parent
spec.loader.exec_module(parent)
paths = list((OUT / 'actual-owned-cost-tmp').rglob('node-transport.sqlite'))
assert len(paths) == 1
with sqlite3.connect('file:' + str(paths[0]) + '?mode=ro', uri=True) as db:
    rows = db.execute('SELECT intent,request_sha256,state FROM requests').fetchall()
    policy = json.loads(db.execute('SELECT policy FROM metadata').fetchone()[0])
observed = []
for ordinal, (raw, stored, state) in enumerate(rows):
    value = json.loads(raw)
    original, fixed = parent.encode_body(value, (1 << 31) - 1), wire.encode_body(value, (1 << 31) - 1)
    assert original == fixed and parent.logical_digest(value) == wire.logical_digest(value) == stored
    observed.append({'ordinal': ordinal + 1, 'canonical_bytes': len(fixed), 'parent_fixed_stored_digest': stored,
                     'state': state, 'exact_canonical_bytes_equal': True})
assert len(rows) < policy['max_records']
receipt = {'schema': 'candidate-owned-fresh-intents/1', 'candidate_owned_intent_rows': len(rows), 'policy': policy,
           'below_unchanged_record_capacity': True, 'all_canonical_bytes_and_stored_hashes_identical': True,
           'pending_rows': sum(row[2] == 'PENDING' for row in rows), 'observed': observed}
(OUT / 'candidate-owned-intents.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({key: value for key, value in receipt.items() if key != 'observed'}))
