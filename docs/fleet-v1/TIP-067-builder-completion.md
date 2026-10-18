# TIP-067 — Builder fixture diagnostic completion

Status: **DONE, focused source verification** under the
[Contractor contract](TIP-067-fixture-diagnostics.md). Parent candidate
`7ebff6b6d3dcfa47a0696b0f571826276bbbda88`, tree
`31bda92fa74f91598cb54234fba4f30cfe800b4d`, remains rejected at 5/8 original
attempt1 workflows. Accepted ancestor remains `fe6ef1b`. Contractor independent
review and the new exact candidate's eight-workflow/artifact gate are separate.

## YAGNI-3 before implementation

1. Necessary: the Windows capacity failure loses its callback exception before
   journal translation to UNKNOWN; the long fixture lacks authorization timing.
2. Reuse: original callbacks, existing verifier clock and real signed proof,
   bounded owner drain and identity-deduplicated post-cleanup failure union.
3. Smallest scope: two existing test files, fixture-local observations and
   controlled regressions. Production, dependencies and policy remain unchanged.

## Implementation and exact bytes

| Test file | Bytes | SHA256 |
|---|---:|---|
| test_tip064_capacity_https.py | 25365 | 11315d03a5fe3992e2861a4fac808b53d650d5f88f1f66b91e3064945fa0cb65 |
| test_tip064_integration.py | 88908 | 291cea3c4e3a6d9879bc0e178494381745a49d574e2b708a5be125fc7ee57434 |

Capacity captures reserve/start exceptions, including inside the ARMED body
before the scope context manager attempts durable release. Completion predicates
check original callback failures before and after normal observation. Original
observation, callback, release and cleanup errors are collected after bounded
cleanup and deduplicated by object identity. A sole original is raised unchanged;
distinct originals form a group. Journal UNKNOWN, uncertain scope records,
callback counts and every existing successful-outcome assertion remain required.

The long fixture records at most 32 rows for existing BEGIN/REQUIRE calls. Rows
contain finite stage/phase/event, elapsed milliseconds, outcome and valid integer
issued/expires/current timestamps. A local verifier wrapper observes only the
already-returned clock value, with the original call count. Grant/body/key/ID/path
and arbitrary diagnostic text are not emitted. Instrumentation is confined to the
fixture verifier and restored after cleanup. Restoration failures join the original
failure union. A retained proof's clock wrapper still delegates the original clock
after restoration and stops observations; no global clock/require patch exists.

All signed TTLs, HTTP/control/SQLite/hold/producer/return/cleanup budgets, authority,
nonce, source checks, FULL/WAL and UNKNOWN semantics remain unchanged. The added
negative scheduling control holds an already-signed snapshot response for 1.05s;
its original 1000-ms TTL expires and is denied. This is a controlled fixture fault,
not a changed positive budget or attribution of historical CI latency.

## Verification and evidence

Diagnostic v1: **13 PASS / zero skips/errors/failures, 4.35s**. Two further
controls were then added. Final focused v2: **164 PASS / 3 explicit Windows
skips / zero failures/errors, 167 JUnit cases, 60.55s**. Counts overlap and are
not summed. All 15 new cases pass on final bytes.

Final command selects both changed suites, test_tip058b_transport,
test_tip060_authorization and test_fleet_gateway_fixture with the constrained
Python3.12.14 environment and current worktree on PYTHONPATH. The three skips need
actual Windows retained-handle ACL/owner/staging observations. Linux PASS does not
satisfy those Windows boundaries. Existing TLS positives, long ACK-before-return,
proof expiry/fresh-phase assertions, signed replay denial, capacity callback counts,
held-worker control and original deadline negatives remain covered.

New controls prove original callback/cause/notes, durable UNKNOWN with retained
ARMED/UNKNOWN scope, original callback plus independent release failure with
ARMED/ACQUIRED still retained, primary/late-callback/cleanup union, actual signed
expiry at verify/require with exact clock calls, retained proof behavior after
restore, concurrent fixture clock isolation, cap32, malformed/sensitive omission,
broken annotation delegation and restoration failure preservation. An actual TLS
first-snapshot expiry control verifies the note emitted by the shared long callback.

The 212-entry manifest is identical before/after final focused verification.
Exactly two source entries differ from parent; every production app entry and all
other 210 source entries remain unchanged. Whitespace verification passes.

Commands, dependency environment, both original log/JUnit receipts, final source
manifests, diff and summary are retained at
`/workspace/scratch/b4674f0ac496/resume-20261006/tip067-builder/`; selected evidence
is [evidence/tip067/builder](evidence/tip067/builder/) with member size/SHA256.

## Limitations and remaining gates

This repairs fixture evidence preservation only. Capacity's historical callback
cause, historical owner-grant/COMMIT/storage/scheduling and native-expiry latency
remain UNKNOWN. No performance, runtime availability or stability repair is claimed.
No full source suite, commit/push, VPS test, restart, deploy, initialization, package,
service, native demo, account/credentials/AutoTrading change or evidence reset was
performed by Builder. The two old demo jobs remain failed. Runtime guards and old
synchronous unit outcome remain UNKNOWN; physical qualification and production
merge remain OPEN/NOT_RUN. The next candidate needs independent review, exact-head
tests, eight original workflow successes and complete artifact verification.
