# TIP-071 checkpoint — 2026-10-07

Source cleanup fix implemented and independently verified; full source gate **NOT_ACCEPTED_6_OF_8_ORIGINAL_ATTEMPT1**. Runtime update/demo **BLOCKED/NOT_RUN**.

- Draft PR: https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/65
- Candidate: `e9f668a049288eb899c580a6b8147e5caedae585`
- Tree: `29426b4fa2fdf0aefbcc4e0273b1f465d5b554c3`
- Parent: `ce621625324a3872faee5302ec27c35b684d5217` (retained rejected TIP-070 v2,7/8)
- Main: `70e2112da9fe8eaa6262f2ba896b55bf3e078260` (unchanged; no production merge)

`ScopedResourceCoordinator._db` leaked its open SQLite connection if either setup PRAGMA raised before the caller obtained it. An actual owned SQLite read/exclusive transaction produced SQLITE_BUSY5; retaining the traceback kept that connection usable before the fix. The fix closes once on setup failure, retains the same primary setup error and chains a secondary close error. A direct builtin SQLite post-fix control confirms the retained connection is closed and normal reopen/data remain usable.

Only production `app/vibemql5/fleet/scoped_resources.py` and new `tests/unit/test_tip071_scoped_db_setup_cleanup.py` changed outside evidence/docs. Signature/connect arguments/setup SQL/successful return and production AST outside `_db` are identical. Other214 source entries match the parent; source216 before/after match the committed head. No budget, TTL, original assertion, workflow, dependency, configuration, schema or authority changed.

Builder focused16PASS; compatibility236PASS/1skip. Independent Contractor46PASS/0skip with92 matched progress rows. These suites overlap; their counts are not added as distinct coverage. Original baseline13FAIL/3PASS and four v1 test-authoring assertion failures remain intact; v2 checks actual Python cause identity/traceback/notes and production was unchanged between v1/v2.

| Original attempt1 workflow | Run | Result |
| --- | --- | --- |
| G03-A |37591357720|PASS|
| TIP027 |37591357681|PASS|
| TIP028 |37591357686|PASS|
| Q1 |37591357702|PASS|
| B1 |37591357719|PASS|
| Bootstrap |37591357624|PASS|
| Integrated |37591357620|FAIL: native FIFO|
| Deep Update |37591357617|FAIL: capacity normal fixture|

Five official ZIPs independently pass size/digest/CRC checks, exact source identity and manifests. All nine harmless proofs pass in their declared limited scopes. Both integrated platform JUnits contain1401 unique cases, preserving all1385 parent identities plus16 new controls. Each platform log has2802 matching START/FINISH progress rows; four existing malformed-ID controls intentionally omit labels.

| Suite | PASS | FAIL | Skip | Full-unit elapsed |
| --- | ---: | ---: | ---: | ---: |
| Integrated Linux |1383|0|18|123.807s|
| Integrated Windows |1388|1|12|467.625s|
| Bootstrap Windows |1389|0|12|465.33s|
| Deep Windows |1388|1|12|515.42s|

All16 TIP071 controls pass on both integrated platforms. All213 required Windows controls pass. Linux has209 required PASS and four existing platform skips. Integrated full unit did not exceed the original600-second budget. Artifact success does not override either failed workflow.

Integrated failure: `test_tip024_native_fifo_order_for_multiple_waiters`. B's native admission thread raised actual `PermissionError errno13` at `os.open(.active.lock,O_CREAT|O_EXCL|O_WRONLY)`; B's ticket was removed during exception cleanup and assertion saw `['C']` instead of `['B','C']`. Raw errno13 establishes the abort, not the OS reason or owner state at that instant. A bounded causal qualification review is separate from TIP071.

Deep failure: `test_actual_tls_verified_two_slot_delivery_keeps_control_live_and_conflicting_third_queued[normal]`. Original three-second pump did not observe `entered.qsize()==2`. Captured scope failure_count0/last_failurenull, bounded timeline32/60 with28 dropped. Root cause remains UNKNOWN; no timeout/assertion was relaxed. This is distinct from the parent's delayed-release guard timeout. The old failing capacity case passed in this head's integrated Windows run; this does not prove its original root cause was fixed.

Bootstrap and Deep use synthetic PR merge `2fd0a4f4fedbdc894e1b4121d9807396ee141e15`; API confirms ordered parents(main70,candidatee9) and exact tree equality with the candidate. This was CI checkout evidence, not a production merge. No failed CI attempt was rerun.

At the fresh post-publication observation, all five typed VPS reads returned raw MCP-32603. Current installed hashes, loaded instance, READY/PIDs/queue/locks, the receiptless older synchronous unit run and MT5 connection/session/data-root/feed/IPC remain UNKNOWN. No VPS write, restart, test or native demo occurred. Older tester jobs `BT-20261006-155004-81B15C` and `BT-20261006-155036-45FC65` retain FAILED/MT5_IPC_INITIALIZE_FAILED with executionNOT_RUN; no reset or rerun.

The mixed legacy TIP053/0.2.42 plus TIP065 read-only overlays is not the full source candidate. TIP071 scoped resources cannot be copied there. Only the previously scoped backend_admin/core.py overlay may be considered after8/8 exact-head artifacts and fresh runtime guards/checkpoint/CAS/readback/reload/loaded checks. Its candidate SHA1700bb519292cdfed4dc64452ad62c3e7a362b5407c29271bae456332bb32e18 and78852B are unchanged; fresh installed SHA remainsUNKNOWN. Full privateVM/two-node/realSDK/physicalFleet qualification and production main merge remainOPEN/NOT_RUN.

Previous DeepFix and Continuation evidence archives retain their original SHA256 and pass CRC checks. New evidence includes raw starting/runtime observations, causal SQLite controls, Builder/Contractor manifests/JUnit/logs, publication identity, five official CI artifacts, raw job logs and terminal workflow receipts. No caches, test databases, private TLS keys or compiled fixture programs are selected as standalone payloads.
