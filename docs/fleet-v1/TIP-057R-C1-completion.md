# TIP-057R-C1 — Explicit local read validation source report

Date: 2026-10-03, Asia/Saigon. **DONE / C1 SOURCE PASS.** Parent is Draft PR #63 head `5583204f698dcbf664ad20ddae8106d96019c8d2`; qualified C1 source is [Draft PR #64](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/64), head `9ec22fec63c64bcaf2aae0df85f1d10d70dfd1e0`. Builder implements [C1's dispatched scope](TIP-057R-C1-build.md): additive input, fresh inventory attribution and static denial of targeted observation. Final documentation-head CI is settled separately by the Contractor. C1 does not complete the original fourteen-AC live-read feature, G03-B integration, G04/Q2, physical connector/two-binding pilot or M1.

## YAGNI-3 and result

1. An explicit registered terminal reference needs a strict product request and sanitized failure receipt before real SDK qualification.
2. Reuse fresh `TerminalInventory`, unchanged M0 `validate_local_target(..., capability="inventory")`, registry attribution and existing `ConcurrencyManager.native_execution`. Inventory resolution supplies identity only; it grants no `live_read` capability.
3. Add one small `fleet/reads.py` helper and optional `target=None` on two facade/MCP reads. There is no SDK/proof import, target-process discovery, helper launch, success branch, activation flag, new transport or durable schema.

No target/null preserves the exact legacy `_observe_live` path, output authority and historical interactive-runtime errors. MCP null/omitted input still invokes the facade without an argument. An explicit object validates exact schema/fields, full-match persisted IDs and positive integer generations without coercion. Malformed input is not echoed. Non-null positive route generation is projected then rejected with `ROUTED_NATIVE_NOT_ENABLED`; invalid route types fail before projection.

Local resolution occurs under the existing shared native admission with a maximum requested wait of two seconds and the remaining ten-second soft budget. Fresh raw inventory rows preserve disabled/duplicate aliases; a narrow precheck rejects non-boolean enabled values and reports case-insensitive duplicate aliases as `RESOURCE_CONFLICT`, without changing M0 or legacy validators. Fresh current registry/configuration is the authority, never cached `facade.inv`. Unknown, stale, disabled, conflicting, unqualified, corrupt or drifted bindings fail without fallback.

A resolved target returns inventory identity source/revision/alias and canonical `identity.binding={executable,data_root}`. It always fails `LIVE_ATTACH_ONLY_UNPROVEN`; source, observed timestamp/binding, terminal and account remain null. Native attachment cleanup is `NOT_ATTEMPTED`, and unexecuted process/initialize/observe/revalidate/cleanup timings remain null.

The helper preserves common lease acquisition, FIFO, ownership checks and audit behavior. Missing/invalid/ACTIVE ownership and generic admission faults return `LIVE_RECOVERY_REQUIRED`; wait `TimeoutError` returns `LIVE_LEASE_UNAVAILABLE`. No native authority is armed, created, closed or mutated. `ownership=RELEASED` is reported only after normal common-context exit; for this zero-effect request it means the request no longer owns the native lease, not SDK/descendant qualification or authority closure. Lease release uncertainty wins with `LIVE_CLEANUP_UNPROVEN`, retains the first earlier failure, reports `RECOVERY_REQUIRED`, and keeps native cleanup `NOT_ATTEMPTED`. Actual monotonic final elapsed time includes release overruns; the first failure stays authoritative while expiry is disclosed separately. No hard-response deadline is claimed.

## Changed files and frozen source

| File | Change | SHA256 |
|---|---|---|
| `app/vibemql5/fleet/reads.py` | New strict denial/receipt helper | `5cfa9e08ccdce9a274aa298dfb237b5e316b0e1da2f90bc25c966a6d442c07c5` |
| `app/vibemql5/core/facade.py` | Only two optional-target read signatures/branches | `692dd3d33b7ed7bbbe09eeb3729b43c0235662adffe4e0d0c9068e92bc69e12b` |
| `app/vibemql5/adapters/mcp.py` | Only two optional object/null input schemas and descriptions | `de83c6fb5e11c107812e1f8b82e64f6fa5708bc7bf0cd7b81b72a159ac213e3c` |
| `tests/unit/test_tip057rc1.py` | 62 focused cases; actual generated MCP schema and common-gate tests | `63205fae09f1cd862e28102fdf4cffd54c8523e2ca5f976ccefebf96b52f8257` |

This Builder report is the fifth new/changed file; the Contractor owns C1 TIP/index/publication/verification documents. No existing proof, evidence, M0 identity/target validator, concurrency/ownership implementation, native job/request-hash, catalog or dependency file changes. The exact generated schemas of all 83 unselected MCP tools match parent baseline SHA256 `16ceef873678e7d7598874c6e612393e23de35c934f18ab6a31b09ad15bd7541`; catalog order/count/hash stay unchanged at 85 tools.

## Verification and acceptance

Focused C1 Linux suite: **62/62 PASS, zero skips/failures/errors**. Contractor's final full-unit run on the frozen source: **464 PASS / 26 existing Linux platform skips**, zero failures; `audit/c1-unit-final.xml` confirms every C1 case executed without skips. The earlier 402/26 receipt predates C1 test collection and is retained as intermediate only. Retained Q1 portable 8/8 and B1 portable 39/39 PASS. Compileall and whitespace checks PASS.

The Contractor verified **7/7 source-head CI workflows SUCCESS**, exact remote Git blobs/SHA256 for all four product/test files, and retained original logs and downloaded proof artifact ZIP digests in [source verification](../../evidence/tip057rc1/source-9ec22fec/verification.json). Source tree is `3eea6cf2c47abdbacbc2d6dcf80ee8922eae335b`. The Windows unit job checked out merge commit `b91c87a5a956d24e91fd431237c78afcce78bd55`; its tree was verified identical to the candidate source tree, with no changed files. [Windows unit run 37054091718, job 110994378031](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37054091718/job/110994378031) reports **486 PASS / 4 pre-existing skips in 38.05 seconds**, zero failures. Named C1 cases executed in that full suite; it is product request-validation evidence, not physical terminal/account or connector-pilot evidence.

Retained source-head proof workflows verified Q1 Windows **16/16**, G03-A Windows **8/8**, B1 portable **39/39** and B1 Windows harmless fixture **10/10**, with zero mandatory-case failures/errors/skips. Original proof source bytes remain unchanged. These results retain their isolated fixture/ownership scope and do not qualify real SDK descendants, VM compatibility or live attachment.

| AC | Named focused evidence | Disposition |
|---|---|---|
| C01 | `test_legacy_none_and_explicit_null_keep_fixed_calls_output_and_errors`; `test_actual_generated_mcp_schema_adds_only_two_optional_objects` | PASS: both legacy methods/runtime policy, actual optional schemas, all 83 other schemas/catalog/native signatures unchanged |
| C02 | `test_malformed_target_is_not_echoed_or_admitted`; `test_domain_scalar_or_missing_fields_remain_sanitized`; `test_route_generation_is_validated_before_projection_and_denied_before_lease`; actual SDK argument-model scalar rejection | PASS: no coercion, arbitrary caller fields/diagnostics never appear |
| C03 | `test_fresh_config_and_registry_faults_beat_cached_facade`; `test_unknown_remote_or_stale_targets_never_fallback`; `test_fresh_registry_revision_and_generation_are_resolved_without_fixed_fallback`; `test_registry_revision_drift_during_resolution_fails_without_observation`; `test_config_and_registry_resolution_execute_only_under_admission` | PASS: fresh raw rows and registry, duplicate/type guards, no process/SDK/fallback |
| C04 | `test_resolved_target_is_inventory_attribution_only_and_authority_unchanged` | PASS: both operations, exact inventory attribution, observed/account fields null, static denial |
| C05 | `test_real_shared_ownership_denies_without_mutating_authority`; `test_genuine_common_fifo_gate_does_not_acquire_a_target_specific_lock`; `test_preacquisition_faults_are_sanitized_and_do_not_release`; `test_real_corrupt_fifo_sequence_is_recovery_failure_not_wait_timeout`; normal release test | PASS: actual common guard/FIFO, immutable authority, correct sanitized failure taxonomy |
| C06 | `test_release_uncertainty_wins_and_preserves_primary`; `test_normal_release_measured_before_return` | PASS: first failure/release precedence, no receipt before release, no native cleanup claim |
| C07 | `test_release_overrun_records_expiry_without_replacing_first_denial`; `test_acquisition_expiry_skips_inventory_and_releases`; `test_remaining_budget_bounds_acquisition_or_skips_it` | PASS: soft budget, truthful executed durations, expiry/first-failure behavior |
| C08 | Actual generated MCP schema test; all 62 C1 cases; final Linux 464/26 and Windows 486/4 unit receipts; retained proof cases; exact-source 7/7 CI verification | PASS for qualified C1 source; final documentation-head CI tracked separately |

The focused suite records every attempted forbidden SDK, target-process discovery, child launch or proof import and asserts zero attempts at teardown. Authority-byte tests and source review verify the absence of native arm/create/closure effects. Domain clock/admission error adapters are explicitly synthetic; actual common FIFO/ownership/corrupt-sequence and SDK-generated schema tests are separate. The named full-suite diagnostics establish C1 validation/receipt behavior and retained baseline behavior. They do not establish real MT5 observation or a physical connector/two-binding pilot. Existing Linux and Windows skips concern prior fixtures and are not converted into C1 PASS or SDK qualification.

## Issues, deviations and next checks

No known source correctness issue remains after review corrected generic admission faults to recovery-required and preserved duplicate-alias evidence. No architecture/scope deviation was introduced. Real VM/Q2 remains deferred by the owner. C1 adds no SDK install/import or invocation path; no VPS/MT5 action, account/credentials/AutoTrading change, enrollment mutation, merge, deployment or product activation occurred in this slice.

Next: Contractor settles final documentation-head CI separately and retains the raw source receipts. Existing deployed connector acceptance, real terminal/account observations and all original unimplemented live lifecycle/SDK gates remain OPEN. The additive schema is prepared in source; it is not exposed on the existing production connector by this build alone.
