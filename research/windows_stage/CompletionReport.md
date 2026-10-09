# Windows stage research — Builder checkpoint

## YAGNI3 before new code

1. This research is needed because the retained Windows failures expose a pre-arm timeout and a 4798ms pre-callback gap without identifying the slow stage. No production correction is justified yet.
2. Reuse the fixed canonical source's `source_manifest`, original pytest suite, `fleet_source_progress`, original fixtures, subprocess timeout and faulthandler. Existing observation source and its controls are retained.
3. The shortest useful addition is one external opt-in pytest plugin, one harness importing the original manifest function, and one Windows workflow checking out the fixed source separately. Only four original node IDs produce bounded timing records. No canonical file changes.

Status: READY_FOR_CONTRACTOR_REVIEW_AND_RESEARCH_RUN. Windows run NOT_RUN; qualification RESEARCH_ONLY. No release acceptance claim.

## Implementation and provenance

All seven added files are research-only. Canonical source was verified against both worktree bytes and local Git blobs: 223 entries exact, local HEAD `8246e7ef884c6debfb74cd332b20c8700430f23d`, tree `010e0e6ed046bc632e737a1d72cc5334d3ea3739`, equivalent to published `f5ee95360acd732e3ccb81730e8a288adb94e4e1`. No existing tracked file was modified.

The new workflow triggers only a PR targeting `feat/fleet-v1-continuous-source-20261003` that changes the research paths. It checks out the PR research HEAD and fixed canonical f5ee953 into separate directories, uses the original locked Python 3.12 dependencies, runs research controls and one full original `tests/unit` subprocess with `fleet_source_progress` and the external plugin. The original 600s bound, faulthandler 90s and job 20min envelope are retained. There are no retries. The harness rejects a wrong source SHA, tree, manifest or platform; it records all 223 source hashes before/after and research file hashes/HEAD. Original nonzero unit exit statuses are preserved. A zero original exit with source drift exits 2.

Plugin capture starts at the original test call, after fixture setup, and stops before fixture teardown. Only the four exact node IDs declared in `stage_observer.CASES` opt in. The control thread is an exact Thread object. Up to two workers bind through an exact owned dispatcher `_native_work`, with no thread name or ID attribution. Constructors bind only during the original selected helper's synchronous construction; nested module seams are measured only inside owned original calls. Owned objects retain original arguments, results, exceptions and context manager protocols. Research initialization, partial install, clock, record, binder, restoration and publish faults fail open. Late/in-flight wrappers delegate original behavior after capture stops.

Finite stage/error categories, three actors and saturating counters bound output. Timeline is 64 prefix + 64 tail rows; only stage/actor/count/timing/error category are retained. No arguments, SQL, identifiers, paths, exception messages or traceback/cause references enter observations. Timing is inclusive and overlapping, so totals must not be added across nested stages. CM `.ENTER`, `.BODY`, `.EXIT` describe the original context protocol; `.EXIT` is not an isolated COMMIT/fsync measure. Native/SQL file-lock entry duration includes original acquisition and setup, without measuring physical OS owner. Gateway server/TLS internals and external fixture teardown are unobserved. Some declared wrappers can legitimately have no executed rows (including callbacks on unbound threads); absence is not proof that a stage was fast.

## Verification

- Research controls: **31 PASS**, 0 errors/failures/skips, JUnit 0.095s. Controls cover exact object/thread routing, unchanged argument/result/error identity, context enter/body/exit and suppression, clock/record/binder faults, partial setter unwind, restoration failure, constructor/nested seam gating, bounded schema/no error retention, retained wrappers and in-flight callbacks after stop, hook construction/missing service faults, and harness source/timeout/exit status controls.
- Four unchanged original cases with the real external plugin: **4 PASS**, JUnit 12.959s on local Linux. Observation faults **0 in every case**; worker bindings **2/2/1/1**; event totals **405/405/2694/3005**. Every observation retains at most 128 rows. Capacity cases observe worker, journal transaction, reserve/start, scope DB/lease arm/RPC stages. Long cases observe admission/materialization/authority/job lock/callback stages. Source remained exact after this smoke run.
- No full local original suite was repeated. No VPS, MT5, account, native SDK or physical qualification operation was performed.

Evidence resides separately in `windows-stage-evidence`: controls and selected-original logs/JUnit, four bounded observation JSONs, verification receipt and frozen publication/manifest. The Contractor independently verifies the package and controls before publishing a separate research draft PR. This package does not merge into the canonical candidate and does not fix or attribute the two retained Windows failures yet.
