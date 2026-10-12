# TIP081 — Preserve the capacity entry boundary through bounded cleanup

Parent: `a7b883bb0cb241c496a03869af5407c198b97f77` (TIP080), tree `017974d761ef40c4080ba3e56aab891a1af2afbd`.

## Observed failure and limits

TIP080 original attempt 1 finished with seven successful workflows and one failed Bootstrap workflow (`38156458682`, job `114520338964`). The failure was the existing TIP077 original three-second capacity entry negative case. It raised an unchanged `HTTPS_UNAVAILABLE` transport error during cleanup; the recorded HTTP elapsed time was 766 ms against the fixture's original 5000 ms policy. No capacity scope transaction failure was observed. The historical physical latency owner remains UNKNOWN.

An independent external control reproduced a causal deadline class: two workers released into the same cleanup control round share its absolute RPC budget. A controlled slow first authorization response left approximately 0.78 seconds for the second start POST. The original transport denied that request, and the fixture correctly refused to count it as the intended entry-boundary failure.

The qualifying control delays the gateway handler before its original clock sample. Grants retain the original 2000 ms TTL, signing and freshness checks, and their issued timestamp equals the returned original clock sample. This avoids a misleading control in which a grant is already expired before response release. Successful controls require four original verification returns (two reserve and two start), no verification errors, unchanged constructor clock identity, exact original exception identities, notes, causes and pump traceback, and closed resources. The root independently ran all eight controls on exact TIP080 source: 8 PASS, JUnit 48.672 s, process 49.042455 s, cap 120 s, zero retries. All 229 published source blobs matched before and after.

## Minimal fixture correction

Only `tests/unit/test_tip077_capacity_entry_watchdog.py` changes executable source. Existing test names, identities and order remain intact.

The original entry gate still opens only after the original predicate returns False. Both positive workers retain their original concurrent cohort. For the original three-second negative case only, the second worker waits before its original native body until the first worker has exited and a new original `OutboundNode.step` begins. Both conditions share one additional five-second pre-request wait bound. A cohort lock assigns the two worker indices. The wrapped worker and step each delegate to the original implementation exactly once.

The selected heartbeat and poll component each run the original HTTP POST once before padding their total controlled component duration to a minimum of 1.6 seconds. A real `perf_counter` measurement controls only this scheduling pad. Each component must remain strictly below five seconds, and aggregate entry must exceed three seconds. Original transport errors propagate unchanged. This removes additive transport latency from the controlled pad without replacing any production clock.

A finite verification witness delegates once to the original verifier, records successful phases only after the original return, and checks its clock identity before and after. The fixture requires exactly two reserve and two start successes after cleanup. A first-worker authorization expiry therefore cannot hide behind the expected three-member error union.

## Invariants and qualification gate

The original entry pump default remains three seconds, positive observation ten seconds, initial pre-request gate five seconds, HTTP policy five seconds, cleanup pump ten seconds, and capacity hold twenty seconds. Grant TTL, production RPC deadlines, original stop/watchdog clocks, signatures, certificate validation and wire freshness remain unchanged. Unexpected denials are never accepted as entry-negative success.

The negative preserves the original primary `pytest.fail`, callback error, and `SCOPE_RELEASE` error union, original causes/notes/context and original pump traceback. The positive preserves its original callback/release pair and the original UNKNOWN and retained ARMED/ACQUIRED assertions. Workers must be joined and dispatchers/resources closed.

The source manifest remains 229 entries; all 89 application files, eight workflows, dependency declarations and runtime overlays remain byte-identical to TIP080. No new regular unit cases are added. All 1585 parent case identities and order must be preserved locally and in both integrated CI artifacts. Root controls cap remains 120 seconds; full source verification cap remains 600 seconds. Each newly published head must complete all eight original-attempt workflows, all five official archives, both source manifests/JUnit suites and nine harmless proof summaries. No reruns or cap increases qualify a head.

This is source and harmless fixture qualification. It does not qualify real Fleet installation, private VM execution, native SDK/compiler/backtest, pilot accounts, AutoTrading or activation. Those physical phases remain OPEN in the approved plan. The existing legacy runtime needs no fixture-only patch or restart.
