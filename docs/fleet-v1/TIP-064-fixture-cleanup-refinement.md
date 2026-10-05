# TIP-064 — Preserve fixture failure and proven closure

Status: **BOUNDED FIXTURE REFINEMENT**. Starting candidate `375e6af790e695aa4f1293268d80cd9a1f111487`, tree `d8072b5217de7855e9925811d9bf6487cb673dcc`, completed six of eight workflows. The [retained checkpoint](evidence/tip064/ci-375e6af/metadata/verification-receipt.json) contains failed Deep/Bootstrap logs, all workflow identities and five original artifact ZIPs. All ZIP digests were checked. Both integrated artifacts match 206 exact Git source hashes and unchanged manifests: Linux 1127 passed/14 skips; Windows 1131 passed/10 skips, zero failures/errors. Those successes do not replace the two failed gates.

Deep run `37263050590`, job `111614077926`, failed the normal capacity fixture at its unconditional final `pump` heartbeat: 1130 passed, one failed, ten skipped. No original primary failure or cause/timing note survived that traceback. Bootstrap run `37263050670`, job `111614078244`, passed 1131 tests/10 skips but had one teardown error: the composed server thread was alive after its three-second join. Its actual live stage was not recorded. Neither log establishes a product transport cause or a specific blocked shutdown stage.

## YAGNI-3

1. The fixture cleanup unconditionally emits another control request after drain and may overwrite an earlier exception. Those source defects are reproducible independently of an inferred Windows incident cause. Teardown needs truthful bounded live-stage observations.
2. Reuse the existing diagnostic HTTP subclass, retained pending/close fences, Python 3.12 `BaseExceptionGroup`, existing events and thread/failure queues.
3. Add one small test-only helper and five controlled cases, apply it to the two implicated capacity/composed fixtures and their relevant cleanup paths. Production modules, HTTP 1000 ms, normal stop observation three seconds, authority deadlines, UNKNOWN semantics and shared writer fixture stay unchanged.

## Corrected boundaries

`close_dispatcher_fixture` checks the retained pending set before pumping. A proven empty set needs no extra authenticated heartbeat. Pending work still requires the existing bounded drain and `dispatcher.close()` remains the final product fence. Failed drain neither closes nor claims idle.

`preserve_fixture_failure` retains the original exception object and its existing notes together with a cleanup failure in a `BaseExceptionGroup`. Cleanup-only failures remain failures. This preserves primary capacity state and transport diagnostic notes rather than substituting a later error.

`stop_gateway_fixture` keeps the normal three-second join and asserts actual thread exit. If still alive, it records at most twelve source basename/function/line frames and failure count. It never prints frame locals, secrets or exception messages, and never calls a live thread CLOSED. A controlled actual `GatewayDomain.close` barrier first establishes event entry, then measures a shortened 0.1-second observation. Only explicit release and the normal three-second join prove later closure; the private barrier watchdog remains finite.

## Evidence and limitations

Builder and independent Contractor focused logs/JUnit, source patches and unchanged before/after hashes are retained in [v2 evidence](evidence/tip064/transport-diagnostics-v2/). Preliminary and final control runs have separate names. These controls prove the cleanup/evidence defects and their correction; they do not reconstruct a missing cause in either the original `8019a52` incident or the later Windows failures.

The next candidate requires its own eight successful workflows and complete exact-head integrated artifacts. No workflow rerun changes any failed receipt's meaning. Original incident cause and unobserved Windows shutdown stage remain OPEN until direct evidence identifies them. Physical VM/MT5/SDK/no-start/two-node/load/client/migration/rollback and production merge/deployment remain OPEN and unperformed.
