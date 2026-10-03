# TIP-064 bounded positive admission and startup fixture refinement

STATUS: DONE for fixture refinement. Builder: `windows_fixture_final`, Vibecode Kit v6. Exact next-candidate full Linux/Windows CI is required before final source handover. Product runtime source is unchanged.

## YAGNI-3

1. Deep Update on canonical source `3e402db86b9e6f9cc53489a6b0b88f97cdb516e5` has two remaining fixture failures while the integrated Windows matrix and Bootstrap pass. Preserve their evidence and address the observed finite fixture budgets.
2. Reuse `dataclasses.replace`, the existing ready/failure queues, the monotonic clock and Python's thread frame inspection. No new production mechanism is needed.
3. Give only positive writer admission a finite 5000 ms HTTP policy, and observe actual gateway readiness/failure for at most 10 seconds. Keep original assertions and every product/negative deadline; add no retries.

## Evidence and resulting behavior

The worktree-config rejection test fails before it reaches the Git rejection. Its retained writer admission diagnostic says `TimeoutError`, 1016 ms elapsed, a 1000 ms HTTP budget, a live server thread and zero server failures. The shared writer fixture now configures a 5000 ms positive HTTP budget on both its actual gateway and client. The separate base transport fixture keeps 1000 ms, including slow-header/family-fallback deadline denials. Explicit absolute authorization deadlines, phase TTLs, replay and UNKNOWN behavior are unchanged.

The protected gateway startup test observes an empty readiness queue after five seconds. Its existing finally block then stops and joins the server within its three-second join budget without a server exception. The exact slow stage is unproven. Source inspection shows two synchronous stages before the ready callback: HTTPServer binding calls `socket.getfqdn`, then the real factory initializes its ledgers. These are candidate stages, not an asserted diagnosis of this Windows failure.

`wait_gateway_started` polls the existing ready/failure queues with one finite ten-second observation deadline. A startup failure raises the original exception promptly. A true timeout includes only thread liveness, failure queue size and up to twelve frame file/function/line records; it prints no locals, headers, credentials or payloads. Protected operator startup still uses the real factory, protected files, TLS context, verified client, owner inventory and duplicate initialization denial. The shared writer fixture uses the same observer and stops/joins on failed startup observation.

Three added tests exercise an actual verified TLS gateway with a deterministic delay in HTTPServer's name lookup, the original startup exception path and a bounded blocked-stage diagnostic. The injected name-lookup delay demonstrates that the synchronous stage is reachable; it does not prove the original Windows cause. The blocked-stage test requires the thread to remain alive until explicit fixture cleanup, so timeout is never treated as closure.

## Verification

The full affected local Linux matrix passed **191 tests, 3 explicit Windows-only skips, zero failures/errors, 29.10 seconds**. It includes protected operator startup, principal/writer/worktree/recovery/capacity HTTPS fixtures, the transport deadline negatives and the existing source-runner timeout/source-drift checks. The three skips require actual retained Windows ACL/ownership/staging handles.

[Receipt](evidence/tip064/startup-ci-refinement-v1/receipt.json), [JUnit](evidence/tip064/startup-ci-refinement-v1/focused.junit.xml), [log](evidence/tip064/startup-ci-refinement-v1/focused.log) and [before](evidence/tip064/startup-ci-refinement-v1/source-before.json)/[after](evidence/tip064/startup-ci-refinement-v1/source-after.json) maps retain 44 unchanged source hashes during this focused run. All 88 production Python files also match the prior canonical snapshot byte-for-byte. This is a local cached-dependency diagnostic, not exact Windows acceptance or physical qualification.

| Frozen fixture source | SHA-256 |
| --- | --- |
| `tests/unit/fleet_writer_fixture.py` | `b92647d64b17cacd54fec921e8ecb0a089c7a3878c1775da5a9824ac983eec56` |
| `tests/unit/test_tip064_integration.py` | `b47059c73a8ffb19c34278c2353a43c33da17e274471bb1662280871fbf69ba8` |
| `tests/unit/test_fleet_gateway_fixture.py` | `526ec67b5fa6de8cbf9ea617c6968b9da376ebb93f07783d15d8cfc51b590198` |

The canonical compact sorted JSON map of these three source hashes has SHA-256 `36194bc141f457316918ccdf1d54ddd0b243248121d0b3727e36fef26610923f`. Current A shared-fixture and M5 manifests point to this focused receipt; each preceding manifest is preserved under its distinct `before-final-startup-refinement` name. Historical receipts and the earlier async refinement retain their original bytes and meanings.

SOURCE_FREEZE: these three fixture/test files are frozen after the focused run. This refinement changes no product source, authority TTL, explicit absolute deadline, deliberate negative budget, runtime architecture, physical qualification or deployment state. Private VM, MT5, actual SDK qualification, merge and deployment remain deferred under the approved plan.
