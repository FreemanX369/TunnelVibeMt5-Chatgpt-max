# TIP-065 — Bounded CI fixture refinement

Contractor contract, 2026-10-05. The approved continuous source/deployment work
continues; no new per-TIP approval or Blueprint restart is required.

## Retained failed candidate and YAGNI-3

Candidate `ec9180e15e840a7d4a3af18f78ce9bee1f4db582`, tree
`66022a510d6d59285c9250d75aa83e038cad24b0`, completed seven of eight workflows on
attempt 1. [The failed receipt](evidence/tip065/ci-ec9180e/metadata/verification-receipt.json)
retains every run, all five original verified ZIPs and the full decoded Bootstrap log.
Bootstrap run 37279566868/job 111664200582 recorded 1178 passed/two failed/12 skips.
Deep and integrated Windows passed 1180/12; integrated Linux passed 1176/16.
Both actual Windows TIP-065 file-observation controls passed. All 210 source hashes
and integrated JUnit/proofs matched exact Git head/tree. Those passes do not replace
the failed eighth gate. No TIP-065 live file write, restart or deployment occurred.

1. Needed now: correct two demonstrated fixture assumptions and retain unmasked
   failure evidence before the new candidate's complete source gate.
2. Reuse: actual native queue/ownership/resource methods, NodeRuntime lifecycle
   methods and the existing primary/cleanup failure preservation helper.
3. Smallest implementation: two existing fixture files plus meaningful controlled
   interleavings/faults. Preserve the frozen observer, overlay and all product bytes.

## Observed boundaries

The resource FIFO fixture enqueues two real processes but assumes the second will
not probe while the first has armed ACTIVE ownership. The product intentionally
rechecks CLOSED on every guarded admission probe, even for a nonwinning ticket.
The reported second-worker ACTIVE_RECOVERY_REQUIRED denial is protective behavior,
not permission to relax the guard or clear state. The fixture emits first success
before actual closure/resource release/lease exit, so that signal cannot authorize
the second producer.

The composed native fixture manually constructs NodeRuntime but omits its normal
`_coordinator=None` and `_capacity_registered=False` sentinels. Its unprotected
cleanup raises AttributeError, masking a primary result-delivery TimeoutError.
The primary diagnostic shows `/fleet/v1/results`, 438 ms post elapsed, HTTP cap
1000 ms, and the server in the job journal transaction while committing a node result.
Result delivery also shares the control round deadline; the HTTP cap is not a promise
of a fresh full 1000 ms. The underlying commit-latency mechanism remains OPEN.

## Builder implementation boundary

For the positive resource fixture, use explicit child scheduling events after real
ticket publication and outside authority guards. Resume the second probe only after
the first proves actual zero-attempt CLOSED, resource RELEASED and native lease exit.
Retain real queue/ticket ordering. This selects a CLOSED composition interleaving;
it does not prove every possible FIFO interleaving. A separate deterministic overlap
must resume a real second probe while the first remains ACTIVE and prove denial,
no second reservation, no implicit closure and eventual first-owner exact cleanup.
Existing pure FIFO serialization checks remain independently required.

For the composed fixture, initialize the normal sentinel fields while retaining the
actual lifecycle methods. Use the existing failure-preservation helper so primary
and cleanup failures survive together. Unexpected WireError remains unchanged.
Controlled primary/cleanup failures must prove no implicit registration, CLOSED,
authority recovery or replay. Any added deadline notes expose only finite sanitized
facts; no request/body/header/token/identity dump is allowed.

No product, HTTP/control/authorization/SQLite/stop budget, durable semantics,
authority or UNKNOWN changes; no automatic HTTP retry, skip, rerun or fixture
initializer on the live host. A later green candidate must not be described as a
functional fix or retrospective root cause for the primary TimeoutError or original
masked owner-grant incident. New exact-head 8/8 checks and complete independent
artifact verification remain mandatory before the approved observation overlay.
