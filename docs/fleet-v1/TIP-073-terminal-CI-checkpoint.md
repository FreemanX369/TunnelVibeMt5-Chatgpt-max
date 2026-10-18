# TIP-073 terminal CI checkpoint carried into TIP-074

Exact previous candidate: ef31be719b090c14effa96e69c08d405ac0ceceb, tree917f04cf1cc50deb26af92c9c26c63f2e7a89a0f, parentab8ce9891ae8fbb871d5de231a33d05dbb585f90. Draft PR65; main70e2112da9fe8eaa6262f2ba896b55bf3e078260 remains unmerged.

All8 required original CI runs completed on attempt1:6SUCCESS,2FAILURE. TIP073 is NOT_ACCEPTED. No failed run was rerun.

| Workflow | Run | Result |
|---|---|---|
| G03A | 37613312356 | SUCCESS |
| B1 | 37613312466 | SUCCESS |
| Q1 | 37613312567 | SUCCESS |
| TIP027 | 37613312578 | SUCCESS |
| TIP028 | 37613312411 | SUCCESS |
| Deep | 37613312386 | SUCCESS |
| Bootstrap | 37613312607 | FAILURE |
| Fleet integrated | 37613312450 | FAILURE |

Deep original default merge4a446b7dab2e1bccf3a190df32aeabb386ad7b2e has exact candidate tree and ordered main/candidate parents. It reports1435PASS12skip0FAIL,429.83s. Bootstrap reports1433PASS12skip1FAIL1ERROR,354.13s: capacity fixture startup5s deadline observes DomainJournal checkpoint in progress; server later stops without a further cleanup group. Long10-second case denies NATIVE_AUTHORIZATION_EXPIRED correctly: TTL1000; internal verifier age953ms, producerrequire age1016ms. The BEGIN clock sample precedes the consumed-intent commit and is not a return timestamp. No causal grant-clock or SQLite checkpoint correction was established from those logs.

Integrated Linux:1447cases1429PASS18skip0FAIL,125.961s. Integrated Windows: original600.016s full-unit aggregate limit,exit124,noJUnit;1205FINISH rows1195PASS10skip0FAIL;ordinal1206 START at596235ms is test_actual_tls_inventory_discovery_read_project_and_production_native_denial. Advancing progress does not prove deadlock; later required controls are NOT_REACHED. No immediate test-failure metadata appeared.

Contractor verified five official artifact ZIP digest/size/CRC and exact 217-entry source before/after manifests; nine harmless proofs remain distinct from physicalFleet/realSDK qualification. Required259 controls retain original outcome/platform skip. Seven known malformed-ID negative cases conservatively omit labels under unchanged progress validation; three are new TIP073B controls, four historical. Corrected Contractor allowlist is preserved in the original checkpoint; no source/test assertion relaxed.

Full original receipts remain in fix-20261007-1748/ci-tip073. This checkpoint records prior terminal evidence; TIP074 changes and a new original CI attempt must be evaluated separately. Neither a new source head nor a local PASS erases TIP073 failures or establishes live readiness.
