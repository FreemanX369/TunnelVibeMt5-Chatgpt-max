# TIP-074B — avoid redundant scalar iteration for immutable ASCII strings

Contractor authorizes Builder implementation under the continuous Fleet V1 plan. Exact parent ef31be719b090c14effa96e69c08d405ac0ceceb. Use an isolated worktree; do not modify tip073-candidate or TIP074A worktree. No publication, CI rerun, VPS or main action.

Evidence: owned actual TLS long fixture [10-1000] passed at exact parent, with 116 heartbeat/116 poll calls; repeated fresh NodeTransportJournal validations dominate measured work. The external plainstr ASCII variant of wire._tree produces identical hashes on 247 freshly read owned persisted transport intents and identical outcomes on 29 Unicode/scalar/depth/type/subclass controls. Six alternating 988-hash batches show median4.976x scalar-tree/hash microbenchmark improvement. This is a local causal computation-cost proof, not a physical Windows cause or total-suite speed claim. Original regex variant is retained as diagnostic history; shortest ASCII variant is selected.

YAGNI-3: (1) remove proved avoidable per-character Python iteration in fresh ledger hashing; (2) reuse built-in immutable plainstr.isascii() and the original non-ASCII/subclass scan; (3) one conditional guard, no new dependency, helper, regex, process, authority result cache or service. ASCII has no UTF-16 surrogate codepoints, so checking that exact type is plainstr and isascii() is sufficient. Every fresh ledger parse/query/digest/signature/resource/freshness/policy check remains.

Allowed production scope: app/vibemql5/fleet/wire.py, only the surrogate-rejection condition inside _tree's string branch. For immutable plainstr ASCII only, omit original generator. All non-ASCII strings and all str subclasses execute the original generator with identical iteration/error behavior. Preserve all other branches/functions/constants/imports exactly, including depth/list/numeric/type/size checks, canonical bytes, hashes and WireError behavior.

Allowed test scope: new focused tests/unit/test_tip074_wire_unicode.py only; no existing test/assertion/identity edits. Meaningful controls cover actual encode/decode/logical_digest Unicode boundaries, nested keys/values, invalid surrogate in beginning/middle/end, limits/types/depth/NaN and str subclasses whose iterator changes observations or raises. Keep controls bounded and avoid a huge parametrized corpus in CI. Do not add flaky wall-time assertions to unit tests.

Acceptance:
- Every freshly read owned intent hash and original/prototype semantic control remains identical with the actual fixed source (not only a cloned function). Include exact parent/fixed canonical bytes and error identities.
- Independently rerun the same actual TLS long [10-1000] profile with candidate source and unchanged policies/budgets/TTL/clocks/holds/assertions. Record wall cost, original request/validation counts and phase observations. Do not remove original mandatory validations or mask fail/UNKNOWN. If end-to-end cost evidence does not support a useful correction, report it rather than claiming gate resolution.
- Existing wire/transport/node-journal/grant-expiry/native-composition controls pass; all old test identities/assertions remain intact. No admission-clock changes, automatic grant retry or stale authority caching.
- Freeze exact parent/full source manifests, one-condition AST/diff scope, file SHA/bytes, original and fixed receipts, raw logs, JUnit, finite external limits and Completion Report. State physicalWindows and historical expiry/setup/gate cause UNKNOWN.

Evidence directory deepfix-20261007-1903/tip074b-builder. Return frozen files and isolated worktree for independent Contractor verification. TIP074A owns disjoint transport lifecycle and fixture paths; do not incorporate its edits.
