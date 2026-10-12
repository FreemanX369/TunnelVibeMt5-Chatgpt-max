# TIP084 — Negative fixture observation by phase

Parent: `4760e95f0f8ec869bb15a3184b824cdd26430337` (TIP083).

## Problem and approved scope

The original ten-second aggregate success observer also surrounded three
intentional pre-callback failures. A slow but finite prerequisite could reach
`RETURN_WAIT` late in that aggregate window, allowing aggregate cleanup to
release the worker before its original three-second return wait expired.
This masked the exact worker-return failure that the negative control tested.

Only these three regular cases opt into the new negative contract:

| Caller | Exact prerequisite identity |
| --- | --- |
| TIP080 controlled verifier failure | Injected original fault and original cause |
| TIP080 real signed start expiry | Original verifier's captured expired-grant exception |
| TIP079 controlled pre-callback failure | Original recovery error retaining the exact injected fault in `__context__`, with its original cause |

The helper takes an optional `expected_handled_error` matcher. It separately
observes prerequisite completion for ten seconds and terminal completion for
ten seconds after the original `RETURN_WAIT` anchor. **This is a new negative
contract permitting up to twenty seconds of observation; it does not preserve
the former overall ten-second aggregate bound for these three cases.**

The original worker still performs `return_barrier.wait(timeout=3)`. Before
terminal observation, the helper binds the native observer's original handled
error index to the same in-memory exception, requires the original native
result to be `UNKNOWN`, and requires that no fixture callback was entered.
An unexpected handled error propagates as the same original object. An
unexpected worker failure before `RETURN_WAIT` propagates immediately instead
of becoming a generic prerequisite timeout. The anchor is checked first so
that a worker which has already completed its original return wait still
undergoes exact prerequisite identity validation.

Terminal publication records the original return-wait exception before
signalling completion. This avoids a race between terminal notification and
the preserving delegate's exception list. No new control HTTP polling is
issued during terminal observation. Cleanup retains its original three-second
owner drain and all existing exception grouping and restoration behavior.

## Preserved contracts

The positive aggregate five/ten-second path, ACK-before-worker-return ordering,
actual signed proof checks, deliberate 1.2-second expiry and fresh successor
proof assertions remain unchanged. The original local helper functions for
callback, delayed return, success/drain, step observation and exception
preservation are byte-identical to the parent.

Signed TTL 1000, the approved maximum TTL 2000, HTTP 5000, startup10/stop3,
worker-return3, cleanup 3, full-suite cap 600 and retries 0 remain unchanged.
No application, workflow, dependency, authority clock, signer, proof issuance,
durability, production admission or runtime operation changes.

The three callers keep their original bodies and assertions apart from the
explicit matcher opt-in. All 1585 regular case identities and order are
preserved; no cases are added, removed, renamed or skipped by this change.

## Causal evidence and remaining limitation

Thirteen external controls passed on the exact published parent: process
82.471682 seconds, cap 180, retries 0, source 229 unchanged. An independent
Contractor execution also passed 13/13 in 82.877555 seconds.

The paired prerequisite delay occurs before original `NodeJobJournal.execute`
delegation and before any authorization issuance. Parent observation released
the original return wait after 2386/1359/2379ms; the candidate allowed the
original wait to fail after 3001/3001/3000ms, then performed cleanup. Both exact
unexpected-error identity and genuine signed 1000 expiry remained tested.

An additional unexpected pre-delegate failure retains the same original
primary exception and the original cleanup failure. The durable job remains
`DELIVERED`; original cleanup can re-admit that retained work. Research
disposal of idle temporary resources is explicitly external and does not
certify successful helper closure or erase durable uncertainty.

Group A's positive signed 1000 feasibility remains open: prior CI observed a
genuine grant age 2403ms before verification. This change grants no expiry
waiver, renewal, retry or TTL increase. Source acceptance still requires all
eight original exact-head CI gates and verified official artifacts.

Full physical Fleet installation, private-VM/SDK validation and pilot execution
remain deferred, open and not run.
