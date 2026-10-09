# TIP-074B Builder Completion Report

Status: BUILDER_COMPLETE_READY_FOR_CONTRACTOR_VERIFICATION. Exact parent ef31be719b090c14effa96e69c08d405ac0ceceb. Isolated worktree: /workspace/scratch/b4674f0ac496/tip074b-builder. Evidence: /workspace/scratch/b4674f0ac496/deepfix-20261007-1903/tip074b-builder. No commit, merge, publication, CI rerun, VPS or main action occurred. TIP074A edits were not incorporated.

## Change and causal mechanism

Only the string surrogate-rejection condition in wire._tree changed. For exact plainstr ASCII, `isascii()` proves absence of surrogates and omits the redundant Python character loop. Non-ASCII strings and every str subclass retain the exact original generator, including custom iteration, original RuntimeError identity, accepted custom ordinary iteration and error ordering. No import/helper/regex/dependency/cache/authority result change was added.

YAGNI-3: remove the measured redundant scalar loop during every fresh intent hash; reuse built-in plainstr.isascii and original fallback; implement one condition with bounded semantic controls. All original queries, JSON parsing, digests, signatures, resource/freshness checks, durable commits, TTL 1000, clocks, budgets, holds, authority and UNKNOWN behavior remain.

## Source and scope proof

Canonical 217 parent snapshot is unchanged. Fixed 218 snapshot adds only tests/unit/test_tip074_wire_unicode.py and changes only app/vibemql5/fleet/wire.py among existing files. AST comparison restores that single condition and proves complete module AST equality. All 216 other existing canonical files and every existing test/assertion remain byte-identical.

Fixed wire: 9891 bytes, SHA256 7ae01084cb19e922c7d2fb81da222b797bda4b32a91ed1217921e0d1782b557c. New test: 4178 bytes, SHA256 38dbc98571dd4639d02ad0dc3084bb81618fa379d0db6484c94d6f2038a25604. Parent wire: 9842 bytes, SHA256 48b3d18123e93735107360e899af893abd0bc606a179793dc085b973ae1f398e. Exact source copies, diff and AST receipt are retained.

## Semantic and finite cost evidence

The 7 new bounded unit tests pass on both actual parent and fixed source. They verify exact canonical Unicode/ASCII bytes and digests, decode boundaries, nested surrogate keys/values at beginning/middle/end, finite numbers and limits, invalid JSON, and custom str iteration/exception identity. No wall-time assertion was added.

Actual-source comparison uses the real modules, not a cloned function. All 30 scalar/error controls and 7 decode controls produce identical parent/fixed canonical bytes, digests and error identities. Every one of 247 freshly read original owned intents preserves exact canonical bytes and stored hashes. Six alternating 988-hash batches show median 4.996347x computation-cost improvement with actual fixed source. Red evidence is original measured redundant computation cost; no artificial semantic failure or speed threshold was introduced.

The same actual TLS long [10-1000] case passes with unchanged source fixture/assertions and a 30-second external process limit. Parent command wall was 6.892319s; fixed wall was 7.187073s. Total wall did not improve in this single finite run, and no CI gate resolution or total-suite speed claim is made.

The unchanged pump completed 148 heartbeat and 148 poll calls versus 116 each at parent. Node validations remained exactly 2/request (296 per route); Gateway remained 3/heartbeat and 4/poll (444/592); both Gateway signature checks and Node signature checks per request remained. Five native-start requests retained 20 Gateway validations, 10 Node validations, 10 Gateway signed-request checks, 5 Node signed-request checks, 5 signatures and 5 native verifications. Full original and fixed counts are in owned-profile-comparison.json. Inclusive nested timings overlap and cannot be summed as exclusive cost.

Node full validation inclusive heartbeat/poll totals were 0.859357/0.882311 s versus 1.404162/1.387751 s despite more completed requests/history. Node POST totals were 2.055943/2.326370 s versus 2.192403/2.460375 s. The capture RPC observation was 36.020 ms versus 82.813 ms. Per-call/event timing differences are single-run observations with differing history and scheduling; they do not establish a matched-history Windows end-to-end cause.

Natural scheduling also yielded 10 result requests versus 9 at parent. All 312 fixed-owned persisted intents were freshly checked against actual parent/fixed bytes and stored hashes; all match, all ACKED, no pending row. The unchanged transport policy remains max_records 1000, max_payload_bytes 262144, wait_ms 1000; 312 rows stay within original capacity. No count was forced or pump/policy/capacity changed.

## Compatibility and original truth

Six existing modules 058a GatewayControl, 058b Transport, 060 Authorization, 060 Journal, 060c NodeTransport and 064 Integration: 308 PASS, 3 SKIP, 0 FAIL/ERROR, exit 0, 38.512198 s command wall with 120-second external limit. The three unchanged skips require real Windows retained-handle ACL/ownership/staging-directory behavior. Full JUnit, raw bounded logs and exact command/environment receipts are frozen. Native expiry, composition, nonce replay, cleanup-error/worker-UNKNOWN and original assertion identities remain intact.

Historical physical Windows expiry/setup/gate cause is UNKNOWN. Physical Windows qualification NOT_RUN. The proven correction is local fresh-hashing computation cost. Paired physical Gateway/Node commit/return and clock/channel evidence remain necessary to attribute the original failure. No grant retry, clock/TTL policy adjustment or stale result caching is proposed.

## Freeze and handoff

Parent/fixed full manifests, SCAN receipt, source bytes, diff/AST, both original and fixed actual TLS receipts, variant history receipt, exact commands/logs/JUnit, additional read-only candidate intent check and this report are frozen by payload-manifest.json. Ephemeral TLS certificates/private keys and basetemp runtime directories are excluded. Source must not change after this freeze without notice. Contractor independently verifies accepted combined candidate before any separately authorized publication/deployment.
