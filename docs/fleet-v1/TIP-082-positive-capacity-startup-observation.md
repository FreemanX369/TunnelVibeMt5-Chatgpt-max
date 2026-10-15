# TIP082 — A bounded positive capacity startup observation

Parent: `284a7220e5889f69da5a1233d72e8f69407d66da` (TIP081), tree `212bfdef5b096dafb8a877a90c916b058166c2ac`.

## Failure and evidence

TIP081 original attempt 1 finished with seven successful workflows and one failed Integrated workflow. Its Windows full suite recorded 1572 PASS / 12 original SKIP / one setup ERROR / 1585 cases, JUnit 446.098 s, process 448.359 s under the unchanged 600 s cap. No process timeout occurred. All TIP081-specific and original TIP077/078/079/080 cases passed; Bootstrap and Deep also passed their complete Windows unit suites.

The sole error was the existing `test_scope_broken_diagnostic_and_restore_keep_original_unknown_and_armed[record]` setup. `capacity_service` explicitly waited five seconds for gateway startup. The original `GATEWAY_STARTUP_FIXTURE_TIMEOUT` reported a live server thread and zero server failures, with its stack in `GatewayJobJournal.__init__` at `PRAGMA journal_mode=WAL`. A stack location does not identify the physical latency owner; that owner remains UNKNOWN.

All five official archives and nine harmless proof summaries were independently checked. Both integrated source manifests contained the same 229 published entries before/after, and both digest-verified JUnit archives retained all 1585 parent case identities/order. TIP081 remains rejected 7/8. Its immutable archive SHA256 is `b68a60a1938a124a33670295ea2fda849ce22facce7f09f963d3f47695e96c07`.

Three frozen external controls on exact TIP081 compare actual original construction and failure semantics, without altering source or production clocks. Root independently recorded 3 PASS, JUnit 12.433 s / process 13.116861 s, cap 120 s, retries 0, with all 229 published source blobs matching before/after:

1. Zero schedule with original startup five runs the existing record case's complete assertions.
2. A real original gateway journal constructor, delegated exactly once and padded after return to total component 5.400153 s using `perf_counter`, produces the original default-five startup timeout. Wait/start/outer error identities and original notes remain equal, no fixture/body is yielded, all three gateway owners close, and the actual three-second join takes 0.405941 s.
3. The same actual constructor at component 5.400104 s under a counterfactual positive-ten observation runs the existing record case's complete error/cause/notes, UNKNOWN, retained ARMED and attribute-restoration assertions. Three gateway and three node owners close; the actual three-second join takes 0.006629 s.

The original record case has no explicit install-marker absence assertion; this contract does not invent one. These controls establish the readiness-budget distinction, not a Windows I/O cause or physical-performance fix.

## Explicit narrow contract revision

TIP074A froze `capacity_service` at explicit startup five / stop three; TIP078 superseded only `composed_service` positive startup to ten. Capacity positive-ten was therefore not inherited authorization or an unchanged budget. This TIP explicitly supersedes that one positive fixture caller's startup observation from five to ten, after the fresh independent evidence above and Contractor review.

Both capacity HTTP profiles (1000 ms and 5000 ms) perform positive gateway initialization before any authenticated job or grant. Their later HTTP-negative and transport deadline phases remain independent and unchanged. Only `capacity_service`'s explicit `startup_timeout=10` changes, with a short explanatory comment. Its `stop_timeout=3` remains intact.

The generic `start_gateway_fixture` default startup five remains unchanged. The named original-five composed negative controls still invoke that actual default and require the original timeout and owned cleanup. All other callers retain their existing startup/stop values. Constructor work, durable WAL/FULL setup, ownership through close, signatures, certificate validation, grant clocks/TTL, production RPC deadlines and callback error semantics remain unchanged. There is no constructor bypass, journal retry, I/O weakening, fake clock, timeout waiver or production/runtime change.

This positive observation remains bounded at ten; an initialization that exceeds that bound still fails with the original startup error and bounded owned cleanup. No evidence supports reducing actual initialization latency or making a greater-than-five component fit the original-five observation without omitting work. The contract changes the positive fixture observation explicitly instead of making that unsupported claim.

## Acceptance and scope

Executable source changes only `tests/unit/test_tip064_capacity_https.py`. Together with two TIP082 documents the frozen payload is exactly three paths. No regular case is added, removed or renamed: all 1585 parent identities/order remain mandatory. Source manifest count stays 229, with 228 parent entries, 89 application files, eight workflows and dependencies byte-identical. No heavyweight regular case is added; the existing default-five negative cases and frozen external real-TLS boundary controls supply the meaningful regression evidence.

Builder focused/full and root independent controls/full must pass once. Root controls include the existing 22 controls plus three actual-candidate startup controls, cap 120 s; full cap remains 600 s, with no retries or tolerance changes. After one expected-parent non-force publication, all eight original-attempt workflows, five official archives, both source manifests/JUnit case sets and exactly nine expected harmless proofs must pass. A failed workflow rejects the head.

This remains source and harmless fixture qualification. Full Fleet installation/authority/private VM/real SDK/pilot phases remain deferred OPEN and physical NOT_RUN. This test/document-only change needs no legacy runtime patch/restart and does not authorize main merge or account/AutoTrading changes.
