# Runtime cost SCAN at exact TIP073 parent

Parent: ef31be719b090c14effa96e69c08d405ac0ceceb. All 217 canonical source files remain byte-identical. No implementation, CI rerun, VPS, admission-clock or TTL change occurred during this SCAN.

## Proven narrow computation cost

Fresh NodeTransportJournal validation rehashes every persisted intent through wire.logical_digest, encode_body and _tree. For plain immutable ASCII strings, the original per-character Python surrogate scan is redundant: str.isascii() establishes every code point is below 128. All non-ASCII strings and all str subclasses must keep the original generator (including observable custom iteration and error behavior).

Selected shortest correction: add `not (type(value) is str and value.isascii()) and` to the existing surrogate-rejection condition only. No import, helper, regex, dependency, service or cache is needed. Every fresh ledger query, JSON parse, hash/digest, signature, resource/freshness/authority check remains.

YAGNI-3: remove a measured redundant scalar loop; reuse the built-in plainstr ASCII predicate and original fallback; restrict production work to one condition with meaningful bounded controls.

## Finite actual owned TLS profile

Unchanged existing long [10-1000] test: 1 PASS, exit 0, process wall 6.892319 seconds with a 30-second external limit. There were 116 heartbeat and 116 poll calls. Node full validation executed 232 times for each route, inclusive 1.404162 and 1.387751 seconds. Node POST inclusive route totals were 2.192403 and 2.460375 seconds. Gateway full validation counts were 348 heartbeat and 464 poll. These are nested inclusive measurements and must not be summed as exclusive elapsed costs.

Five native start requests retained 20 Gateway validations, 10 Node validations, 10 Gateway signed-request checks, 5 grant signatures and 5 Node native verifications. Worker RPC waits for admission, admission, snapshot, compile and capture were 34.191, 15.145, 33.529, 36.833 and 82.813 milliseconds. No hold, policy, TTL, clock, delay or validation result changed. Full aggregate counts and event timings are in actual-owned-cost.json; exact command/environment are in commands.json.

## External variant equivalence and computation timing

Both observed variants are retained: regex-only-for-plainstr and the selected plainstr.isascii guard. They were compiled as external isolated clones, leaving source unchanged. Each matches 29 bounded scalar, Unicode boundary, surrogate, key/value, depth, count, number, type and custom-str-iteration controls, and every stored hash for 247 freshly read owned transport intents. Six alternating batches each rehashed 988 intents per side.

Regex median ratio: 3.830275x. Preferred ASCII guard: original 34.659–38.297 ms versus guard 6.871–7.726 ms, median ratio 4.975805x. This proves avoidable computation on observed fresh inputs, not a full-suite or physical Windows speed claim. No speed assertion belongs in CI. The prototype script's unused regex setup is diagnostic history only; the proposed production condition needs no regex or new import.

## Ranked brainstorm and boundaries

1. Plainstr ASCII surrogate guard: measured equivalence and cost proof above; concrete TIP074B correction justified, subject to actual fixed-source and owned TLS verification.
2. SQLite and started-callback lifecycle: root's independent lifecycle owner is investigating a real retained-traceback resource leak; disjoint ownership and cleanup correction belongs to that owner.
3. Win32 ABI/DLL binding initialization: reuse the existing immutable ABI/table/owning-DLL cache pattern only if a physical Windows probe measures this as relevant. Every handle/token/SID/ACL/resource observation must stay fresh. No current proof ties this setup to delayed capture BEGIN.
4. Double Gateway signature verification: measured 10 checks for 5 native requests cost about 3 ms inclusive. Owner/error-order proof and fresh checks outweigh the tiny demonstrated saving; no correction proposed.
5. Repeated ledger metadata/row computation within one validation: any future optimization must retain fresh guard and query semantics, use identical freshly observed inputs, and prove equivalence. Cross-request cache or skipping full validation is outside scope.
6. Connection pooling or changed TLS lifetime: architecture/resource-bound change exceeds the current proven mechanism; no current correction proposed.

The original physical Windows expiry/setup/gate cause remains UNKNOWN. Missing paired wall/monotonic, Gateway issuance/commit/return and Node service/CONSUMED-commit timings prevent attribution to clock jumps, storage or scheduling. No claim that this local optimization resolves the historical failed gate is supported. Physical Windows qualification NOT_RUN.

## Evidence freeze

Top-level evidence files only are included in payload-manifest.json. Ephemeral owned TLS certificates/private keys and basetemp directories are intentionally excluded. Source-before.json and source-after.json cover canonical 217 files. All observed variants, exact commands, raw bounded logs, JUnit, profile and receipts are retained.
