# TIP-072 / TIP-072F — Contractor verification

2026-10-07. Local output is accepted for a new exact-head CI publication. Full source CI for this candidate is pending; deployment/demo is BLOCKED/NOT_RUN. Parent is `e9f668a049288eb899c580a6b8147e5caedae585`; main remains `70e2112da9fe8eaa6262f2ba896b55bf3e078260`.

TIP-072 preserves a native FIFO waiter's ticket when publication raises EACCES at the exact expected lock path and an ordinary non-aliased owner record is affirmatively bound to the same live OS process identity. Qualification only supplies a wait barrier. Admission remains the original exclusive publication under CLOSED authority. Missing, malformed, foreign, aliased, dead, unobserved or inaccessible owners retain the exact original error. No owner reclaim/delete, arbitrary denial retry, deadline/TTL increase, mutation namespace generalization, new API or authority relaxation was added.

The real owned-file/live-owner baseline with only the observed errno13 boundary modeled loses B's ticket and permits C to win. Contractor independently replayed that original-source causal probe. This establishes the conditional defect, not the owner or physical Windows mechanism in the original CI failure. Those remain UNKNOWN.

The historical Builder baseline V2 is 3 FAIL / 28 PASS, fixed focused 31 PASS / 0 SKIP. Original V1 authoring evidence is retained. Historical compatibility is 228 PASS / 1 SKIP / 1 FAIL across230 cases, exit1/wall10.864s. It was unreadable during the execution-server outage; it is not relabeled PASS.

The complete pristine parent has216 source entries, all exact Git bytes, and reproduces the same230-case compatibility failure. The isolated old TIP024 catalog/context test fails on both heads because its fake MCP module omits `exceptions.ToolError`. Collecting a separate actual-SDK module masks that omission through cached imports. This is a fixture import-order defect in unchanged code, not evidence against the TIP-072 concurrency change or evidence of physical SDK acceptance.

Separate TIP-072F adds exactly three statements to that existing fake SDK setup to provide its missing exception module/class. Contractor confirms all previous AST nodes/assertions remain and the AST outside the fake setup is identical. The strict production adapter and SDK imports are unchanged; a fresh incomplete-provider negative control still raises the original SDK-required RuntimeError with ModuleNotFoundError as cause.

| Verification | Result | Scope |
| --- | --- | --- |
| Builder TIP-072 controls |31 PASS /0 SKIP|Qualified barrier, FIFO/deadline,24 negative qualifications, bad path, authority and normal success/release|
| Contractor independent TIP-072 |31 PASS /0 SKIP|Frozen implementation,217 source entries unchanged|
| Builder corrected original compatibility |229 PASS /1 existing Win32 skip /0 FAIL|Same original230 cases, original budgets/assertions|
| Builder isolated corrected registration |1 PASS|Fresh process, no unrelated SDK module preloading|
| Contractor combined compatibility+TIP-072 |260 PASS /1 existing Win32 skip /0 FAIL|261 cases, wall9.101s,217 entries unchanged|
| Contractor isolated registration |1 PASS|Fresh process, wall0.428s|

Coverage overlaps; these numbers are not added as distinct coverage. The existing Win32 SDK control remains a Linux platform skip. Fake registration controls remain stub scope and do not qualify the physical SDK/Fleet.

| Source | SHA-256 |
| --- | --- |
| `app/vibemql5/core/concurrency.py` |`0bf1db9cf1a97c36714bcc87f6229922f8d666b38d904ab0534a7c4aff474db4`|
| `tests/unit/test_tip072_native_denied_publication.py` |`8e238ed853dea1d1283c07ac12bde9c2166e339fb14178edd1e74de573494d81`|
| `tests/unit/test_tip024_multiclient_concurrency.py` |`e33edee22aa54f3ca8fe5f91177324f9fdf6bdd147993781ec431160b0a7e7ee`|

Only these three source entries differ from the parent; other214 match exactly. Production AST outside the narrow denial/helper/import additions is identical.217-entry manifests match before/after every independent run. All30 causal-review and26 fixture-Builder payload hashes verify. Source/report diff checks are required before publication; raw logs remain byte-preserved.

Evidence is under `evidence/tip072/`: historical Builder receipts, original modeled causal probe/replay, complete-parent compatibility diagnosis, corrected fixture evidence, independent Contractor logs/JUnit/manifests/AST/scope and fresh Git/runtime observations. The candidate's expected full unit collection is1401 retained parent identities plus31 new controls; original workflows/dependencies/budgets are unchanged.

The parent remains rejected6/8: integrated Windows native FIFO failure and separate Deep capacity-normal three-second pump failure. No prior failed CI was rerun or overwritten. A new candidate must pass all eight original-attempt workflows and exact-head artifact review. A later PASS does not establish the original Windows OS cause or the separate capacity cause.

All five current typed runtime reads return MCP-32603. Current installed/loaded identity, READY/PIDs/queue/locks, old receiptless synchronous unit descendants and MT5 state remain UNKNOWN. No VPS write/restart/test/demo occurred. Full-source concurrency/scoped-resource code must not be copied onto the mixed legacy runtime. Any previously eligible core overlay still requires exact source gates and current checkpoint/CAS/readback/loaded/guard verification. Private VM, two-node and physical Fleet qualification remain deferred/OPEN; production merge is NOT_RUN.
