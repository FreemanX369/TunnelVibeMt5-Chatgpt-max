"""Freeze bounded Builder evidence; source and assertions are verified read-only."""
from pathlib import Path
import hashlib
import json
import subprocess
OUT = Path(__file__).parent
BASE = OUT.parents[1]
PARENT = BASE / 'tip073-candidate'
FIXED = BASE / 'tip074b-builder'
parent = json.loads((OUT / 'source-parent217.json').read_text())
fixed = json.loads((OUT / 'source-fixed218.json').read_text())
for root, expected in ((PARENT, parent), (FIXED, fixed)):
    assert {key: hashlib.sha256((root / key).read_bytes()).hexdigest() for key in expected} == expected
assert subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=FIXED, capture_output=True, text=True, check=True).stdout.strip() == 'ef31be719b090c14effa96e69c08d405ac0ceceb'
status = subprocess.run(['git', 'status', '--short'], cwd=FIXED, capture_output=True, text=True, check=True).stdout
assert set(status.splitlines()) == {' M app/vibemql5/fleet/wire.py', '?? tests/unit/test_tip074_wire_unicode.py'}
assert not subprocess.run(['git', 'status', '--short'], cwd=PARENT, capture_output=True, text=True, check=True).stdout
for name in ['unicode-controls.command.json', 'parent-unicode-controls.command.json', 'actual-source-equivalence.command.json', 'actual-owned-cost.command.json', 'compatibility.command.json', 'candidate-owned-intents.command.json']:
    assert json.loads((OUT / name).read_text())['exit_code'] == 0
scope = json.loads((OUT / 'scope-ast.json').read_text())
assert scope['production_ast_diff_exactly_one_condition'] and scope['all_existing_test_files_byte_identical']
eq = json.loads((OUT / 'actual-source-equivalence.json').read_text())
comparison = json.loads((OUT / 'owned-profile-comparison.json').read_text())
owned = json.loads((OUT / 'candidate-owned-intents.json').read_text())
report = f'''# TIP-074B Builder Completion Report

Status: BUILDER_COMPLETE_READY_FOR_CONTRACTOR_VERIFICATION. Exact parent ef31be719b090c14effa96e69c08d405ac0ceceb. Isolated worktree: {FIXED}. Evidence: {OUT}. No commit, merge, publication, CI rerun, VPS or main action occurred. TIP074A edits were not incorporated.

## Change and causal mechanism

Only the string surrogate-rejection condition in wire._tree changed. For exact plainstr ASCII, `isascii()` proves absence of surrogates and omits the redundant Python character loop. Non-ASCII strings and every str subclass retain the exact original generator, including custom iteration, original RuntimeError identity, accepted custom ordinary iteration and error ordering. No import/helper/regex/dependency/cache/authority result change was added.

YAGNI-3: remove the measured redundant scalar loop during every fresh intent hash; reuse built-in plainstr.isascii and original fallback; implement one condition with bounded semantic controls. All original queries, JSON parsing, digests, signatures, resource/freshness checks, durable commits, TTL 1000, clocks, budgets, holds, authority and UNKNOWN behavior remain.

## Source and scope proof

Canonical 217 parent snapshot is unchanged. Fixed 218 snapshot adds only tests/unit/test_tip074_wire_unicode.py and changes only app/vibemql5/fleet/wire.py among existing files. AST comparison restores that single condition and proves complete module AST equality. All 216 other existing canonical files and every existing test/assertion remain byte-identical.

Fixed wire: 9891 bytes, SHA256 7ae01084cb19e922c7d2fb81da222b797bda4b32a91ed1217921e0d1782b557c. New test: 4178 bytes, SHA256 38dbc98571dd4639d02ad0dc3084bb81618fa379d0db6484c94d6f2038a25604. Parent wire: 9842 bytes, SHA256 48b3d18123e93735107360e899af893abd0bc606a179793dc085b973ae1f398e. Exact source copies, diff and AST receipt are retained.

## Semantic and finite cost evidence

The 7 new bounded unit tests pass on both actual parent and fixed source. They verify exact canonical Unicode/ASCII bytes and digests, decode boundaries, nested surrogate keys/values at beginning/middle/end, finite numbers and limits, invalid JSON, and custom str iteration/exception identity. No wall-time assertion was added.

Actual-source comparison uses the real modules, not a cloned function. All 30 scalar/error controls and 7 decode controls produce identical parent/fixed canonical bytes, digests and error identities. Every one of 247 freshly read original owned intents preserves exact canonical bytes and stored hashes. Six alternating 988-hash batches show median {eq['median_ratio']:.6f}x computation-cost improvement with actual fixed source. Red evidence is original measured redundant computation cost; no artificial semantic failure or speed threshold was introduced.

The same actual TLS long [10-1000] case passes with unchanged source fixture/assertions and a 30-second external process limit. Parent command wall was {comparison['parent_command_wall_seconds']:.6f}s; fixed wall was {comparison['fixed_command_wall_seconds']:.6f}s. Total wall did not improve in this single finite run, and no CI gate resolution or total-suite speed claim is made.

The unchanged pump completed 148 heartbeat and 148 poll calls versus 116 each at parent. Node validations remained exactly 2/request (296 per route); Gateway remained 3/heartbeat and 4/poll (444/592); both Gateway signature checks and Node signature checks per request remained. Five native-start requests retained 20 Gateway validations, 10 Node validations, 10 Gateway signed-request checks, 5 Node signed-request checks, 5 signatures and 5 native verifications. Full original and fixed counts are in owned-profile-comparison.json. Inclusive nested timings overlap and cannot be summed as exclusive cost.

Node full validation inclusive heartbeat/poll totals were 0.859357/0.882311 s versus 1.404162/1.387751 s despite more completed requests/history. Node POST totals were 2.055943/2.326370 s versus 2.192403/2.460375 s. The capture RPC observation was 36.020 ms versus 82.813 ms. Per-call/event timing differences are single-run observations with differing history and scheduling; they do not establish a matched-history Windows end-to-end cause.

Natural scheduling also yielded 10 result requests versus 9 at parent. All 312 fixed-owned persisted intents were freshly checked against actual parent/fixed bytes and stored hashes; all match, all ACKED, no pending row. The unchanged transport policy remains max_records 1000, max_payload_bytes 262144, wait_ms 1000; 312 rows stay within original capacity. No count was forced or pump/policy/capacity changed.

## Compatibility and original truth

Six existing modules 058a GatewayControl, 058b Transport, 060 Authorization, 060 Journal, 060c NodeTransport and 064 Integration: 308 PASS, 3 SKIP, 0 FAIL/ERROR, exit 0, 38.512198 s command wall with 120-second external limit. The three unchanged skips require real Windows retained-handle ACL/ownership/staging-directory behavior. Full JUnit, raw bounded logs and exact command/environment receipts are frozen. Native expiry, composition, nonce replay, cleanup-error/worker-UNKNOWN and original assertion identities remain intact.

Historical physical Windows expiry/setup/gate cause is UNKNOWN. Physical Windows qualification NOT_RUN. The proven correction is local fresh-hashing computation cost. Paired physical Gateway/Node commit/return and clock/channel evidence remain necessary to attribute the original failure. No grant retry, clock/TTL policy adjustment or stale result caching is proposed.

## Freeze and handoff

Parent/fixed full manifests, SCAN receipt, source bytes, diff/AST, both original and fixed actual TLS receipts, variant history receipt, exact commands/logs/JUnit, additional read-only candidate intent check and this report are frozen by payload-manifest.json. Ephemeral TLS certificates/private keys and basetemp runtime directories are excluded. Source must not change after this freeze without notice. Contractor independently verifies accepted combined candidate before any separately authorized publication/deployment.
'''
(OUT / 'Completion-Report.md').write_text(report)
(OUT / 'final-source-verification.json').write_text(json.dumps({'parent217_exact': True, 'fixed218_exact': True, 'parent_clean': True, 'fixed_head': 'ef31be719b090c14effa96e69c08d405ac0ceceb', 'fixed_status': status, 'scope_and_all_commands_passed': True}, indent=2) + '\n')
files = {path.name: {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(OUT.iterdir()) if path.is_file() and path.name != 'payload-manifest.json'}
manifest = {'schema': 'tip074b-builder-freeze/1', 'parent': 'ef31be719b090c14effa96e69c08d405ac0ceceb', 'worktree': str(FIXED), 'parent_source_files': 217, 'fixed_source_files': 218, 'files': files, 'total_bytes': sum(row['bytes'] for row in files.values()), 'excluded': ['actual-owned-cost-tmp ephemeral TLS/runtime journals', 'compatibility-tmp ephemeral TLS/runtime journals']}
path = OUT / 'payload-manifest.json'
path.write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'payload_files': len(files), 'total_bytes': manifest['total_bytes']}))
