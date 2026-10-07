# TIP-074 Contractor verification — proven lifecycle and scalar computation corrections

Contractor accepted frozen Builder output for a new draft source candidate under the existing continuous update plan. Parent ef31be719b090c14effa96e69c08d405ac0ceceb; main70e2112da9fe8eaa6262f2ba896b55bf3e078260 stays unmerged. Prior TIP073 terminal gate remains NOT_ACCEPTED6/8; no old CI attempt rerun.

## Concrete behavior

TIP074A: serve_gateway now owns a completed controller during post-factory initialization and started callback, then attempts domain/native and control cleanup. Only errors raised by this lifecycle body enter the primary/cleanup group. Actual cleanup failures remain visible; a before-domain close failure leaves its owners visibly UNKNOWN/open, never falsely closed. Four test fixture factories immediately register each acquired resource with ExitStack and transfer ownership only after successful controller construction. Production fleet_cli.gateway_factory already handles partial construction and is unchanged.

Two original actual TLS/SQLite controls prove retained traceback owner leakage: a real test factory DomainJournal construction error retains earlier control/jobs, and a raising started callback retains three completed controller stores. Owned corrected controls release exact leases while preserving exception evidence. Final unchanged V3 controls at parent10FAIL2PASS versus candidate12PASS; selected compatibility15PASS0skip. Builder V1 observer overcounting and the candidate's initially incorrect sys.exception()/docstring placement are preserved and corrected, not attributed to historical runtime faults.

TIP074B: one condition in wire._tree skips the redundant Python character scan only for exact immutable ASCII str. Unicode and custom str subclasses use the original generator and error behavior. Every fresh ledger query, JSON parse, hash, signature, resource/freshness/authority check, commit, TTL, clock and budget remains. Actual parent/fixed semantic controls30scalar+7decode,247original and312fixed fresh intents preserve bytes/hashes/errors. Actual-source microbenchmark median4.996x; one TLS command wall increased6.892→7.187s, so no total-suite or historical Windows speed claim. Native-start request/signature/validation multiplicities stay exact; heartbeat/poll totals vary naturally with the original pump.

## Independent Contractor checks

- Verified8MCP-SCAN+17lifecycle-SCAN+16cost-SCAN frozen payloads; hashes match their manifests. Live ordinary reads, hash bypass, corrected evidence read, supervisor/tunnel status all return raw MCP-32603. No installed/loaded identity or guard state was inferred; no live writes.
- Verified all46TIP074A and50TIP074B Builder payload byte/hash receipts. Frozen source matches integration copies. Private generated TLS files and basetemp stores are excluded.
- Combined219-entry source snapshot changes exactly6existing files and adds2test modules;211existing source files are byte-identical. Production AST outside serve_gateway is exact and its docstring preserved; wire module AST differs only by the proved ASCII condition. All existing test bodies/assertions remain byte-identical; four fixture modules' AST outside the factory and ExitStack import is exact.
- Independent full owned local Linux unit suite:1466cases1425PASS41skip0FAIL/ERROR,exit0,118.974s,original600s external aggregate bound. 23skips require locally absent PowerShell;18existing platform/live gates remain skipped. All19new controls PASS.219before/after source hashes match.
-2932ordered paired progress rows; no immediate failure metadata. Seven existing malformed-ID negative controls retain conservative unlabeled rows under unchanged progress validation. Complete JUnit and case identities preserved; no tests/assertions/progress rejection rules relaxed.

## Scope and deployment state

These corrections are proved local lifecycle safety and fresh-hashing computation improvements. Historical physical Windows capacity checkpoint latency, expired capture authorization and the prior integrated600s timeout cause remain UNKNOWN. The source CI candidate must complete all8 original required workflows and exact artifact/manifest/control checks; local PASS is not Windows or live qualification.

Fleet V1 M1-M5 source and31optional tool definitions remain source-built. This does not prove runtime registration. The currently exposed legacy connector's loaded source/catalog and prior receiptless test descendants remain UNKNOWN because every current read route errors. Backend tools share MCP startup/transport; no independent VPS ingress was established. No blind restart, new live test, account/credential/AutoTrading change or full-source replacement of the historical derived legacy variant was performed. PrivateVM/two-node/realSDK/physicalFleet qualification remains deferred/OPEN.

A later permitted deployment needs fresh target/guard observation, compatible exact source bytes, checkpoint/CAS, readback hashes and loaded runtime/tool verification. This report supplies source evidence and a qualified draft candidate path, not a claim that a VPS deployment occurred.
