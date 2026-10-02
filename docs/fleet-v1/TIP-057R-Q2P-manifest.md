# TIP-057R-Q2-P — Exact environment manifest preparation

Date: 2026-10-02, Asia/Saigon. Status: **PREPARATION COMPLETE / EXECUTION BLOCKED**. User approved the isolated SDK-worker compatibility-first direction following G03-B0. This document prepares the exact Q2 manifest; it does not select an unknown physical host or authorize SDK, provisioning, terminal or trace effects. Authority: PR #62 `0ebbd88b5ba7758c884d521000c2c0e1dee02ee3`, [G03-B](TIP-057R-G03B.md), [Q2 readiness](TIP-057R-Q2-readiness.md).

## YAGNI-3 and smallest candidate

1. This manifest is needed because the qualified C fixture cannot establish actual Python/MetaTrader5 IPC compatibility or no-start.
2. Reuse Q1 restriction/OS identity and G03-A durable authority, qualified Windows receipts and source hashes. Neither is SDK-qualified. Runtime must not import proof modules.
3. Prepare documentation now. After exact environment approval, implement only a bounded research SDK worker for load/attach controls; no unused general launcher or broad producer integration.

**Proposed physical scope, not yet selected:** one fresh disposable Windows x64 VM, one dedicated interactive console session, two fresh terminal installations/data roots, disconnected and without saved accounts. A local interactive VM is preferable to assuming hosted CI supplies an appropriate desktop or SDK distribution. OS build, Python and SDK versions remain unselected. Historical Q1 Windows Server 2025/Python 3.12.10 observations are prior fixture evidence, not the manifest. No current VPS, MT5-2 or production clone is a candidate.

## Manifest slots and required evidence

`BLOCKED` means the required actual value is unavailable, not a permitted wildcard. An operator returns the filled table and evidence attachments without credentials. Each dependency file uses byte length and SHA256; identities are observed, not copied from expected journal fields. Canonical roots include volume/file identity and reparse-point resolution. All fields must be filled and reviewed before effects.

| Slot | Current value | Required actual value / attachment |
|---|---|---|
| M01 owner and host | BLOCKED | Disposable owner; VM/host UUID; creation image identifier/digest; proof of isolation from production; cleanup owner |
| M02 OS and session | BLOCKED | Windows edition/build/x64; user SID; session ID; desktop/window station; console mode; elevation/integrity/token; ambient JobObject membership and restrictions |
| M03 Python | BLOCKED | Exact version/x64; executable and runtime DLL paths, lengths/hashes; installation provenance; dependency search path inventory |
| M04 SDK | BLOCKED | Exact MetaTrader5 version; wheel filename/length/SHA256 and provenance; native extension and all loaded non-system DLL paths/hashes; no minimum-version substitution |
| M05 terminal binding A | BLOCKED | Terminal executable/build/length/hash/provenance; canonical install and data roots; fresh generation; initial process identity or stopped state; no saved account/credentials |
| M06 terminal binding B | BLOCKED | Same facts as A; distinct install/data identities; no copied production profile; observed binding disambiguation |
| M07 distribution/network | BLOCKED | Exact provisioning source URLs/artifacts and allowed network destinations/time window; egress policy during tests; installers' allowed process/file effects |
| M08 restriction/resources | BLOCKED | Effective pre-import AppContainer SID/capability count 0; child restriction policy; inherited handle exclusions; exact Python/SDK/terminal fixture ACL and mandatory labels; any required IPC resource name/access; no privilege expansion |
| M09 trace | BLOCKED | Chosen collector/version/config/hash; actual start/stop/self-check; birth/exit events with timestamps, PID+creation identity, image/parent/session and roots; broker/uncontained path coverage; zero-loss evidence |
| M10 ownership/storage | BLOCKED | Actual disposable authority root/epoch/generation; controller/worker identities; exclusive participants; durable storage/atomic readback evidence; exact termination owner/handles |
| M11 lifecycle | BLOCKED | Provision/start/stop/remove allowlist for A/B and research processes; per-stage deadlines; exact teardown/reconciliation checklist; uncertain cleanup retained ACTIVE |
| M12 approval | BLOCKED | Filled manifest digest; reviewed research-worker source digest; approved physical effect scope and responsible executor; no reusable authorization for other hosts |

Observed local preparation facts: Linux x86_64, Python 3.12.14. These exclude this shell as a real Windows Q2 host. Repository declares `MetaTrader5>=5.0.6147` only; Q1 workflow requests `python-version: "3.12"`, which is not an exact SDK/Python lock. No SDK import or initialization was performed to gather these facts.

## Source reuse anchors

The following observed local byte hashes must be compared against the selected reviewed remote head before execution. They are not signatures of a Q2 SDK harness.

| Existing component | SHA256 |
|---|---|
| `tests/proofs/tip057rq/windows_boundary.py` | `36cc06ea8a80e2f7c6f24cb973c9aede62df4183d8d2c4b56d4d31cb0f542c84` |
| `tests/proofs/tip057rq/authority.py` | `604aeae2fb3da5e9985c3ea28f2f92e1c69d765a5ddda7df15ee43ac251299ff` |
| `tests/proofs/tip057rq/run_proof.py` | `562225eee54566b1a843ed3b32ef4e8b6bb1023e7ec04abeaf0ffca82e7880db` |
| `tests/proofs/tip057rq/fixture_worker.c` | `8c56e060a9f3010f74e4acde73631975486d64ab0c4e74119623253489f0974a` |
| `tests/proofs/tip057rg03a/run_windows.py` | `70c293168a5db2f88f617a62063801688710bf58aac333c7b80eaa399e4e0cd3` |

Existing `Boundary.spawn()` accepts a C fixture argument protocol, not arbitrary Python SDK worker commands. Its flat fixture ACL does not establish access to a full Python runtime or IPC. Therefore existing `run_proof.py --require-windows` can repeat Q1 only; no existing command is an execution-ready Q2 command. After M01–M11 and effect scope are concrete, the smallest bounded research-source TIP must explicitly adapt the command/resource boundary without changing its preventive restriction. Bind actual suspended-worker identity before resume and before SDK import. Keep root-only low label; console mode stays selected and measured. Q1's unresolved no-console startup error is not a supported Q2 default.

## Finite proposed execution sequence

The budgets below are proposed manifest defaults, not measured guarantees: each ordinary case 30 seconds, exact worker cleanup 5 seconds, stage 5 minutes, overall research run 20 minutes. One attempt per matrix case; no automatic retry or privilege widening. Timeout creates a truthful blocked/uncertain receipt. Process termination and ownership reconciliation may remain unresolved after the observation deadline; never label them complete to meet a budget. Evidence output cap proposed at 256 KiB per summary, with raw trace retained separately and loss/truncation causing no-start qualification OPEN. Final selected caps and storage retention belong in M09/M11.

| Stage | Allowed candidate effects after exact approval | Required receipt / stop gate |
|---|---|---|
| P0 environment/prevention control | Enumerate approved host; run unchanged harmless Q1/G03-A fixtures in selected session; validate trace with a short-lived owned marker process | Exact source/dependencies/token/ACL and birth+exit trace; missed transient process or ambient control denial stops qualification |
| L load | Matched unrestricted and restricted Python SDK import only | Both actual native extension/DLL maps and exit identities; restricted failure stops compatibility before any initialize |
| I attach | Deliberately start only fresh A/B using approved provisioning path; one exact-path initialize and bounded null/disconnected observation per binding per control; shutdown then worker exit | OS roots and process binding match; null financial fields accepted; no login/trades; worker/descendant closure exact |
| S stopped | Stop only exact owned disposable target; one unrestricted SDK initialize demonstrating launch, then reset clean stopped state; one restricted initialize | Working matched launch control and complete transient birth trace; restricted zero births plus explicit failure; failed control is BLOCKED |
| R race | Deterministic test handshake removes only exact owned target after discovery and before initialize | Handshake/order and exact exit evidence; matching unrestricted launch control; restricted zero terminal births; no timing-only polling proof |
| E escape | Enumerate real SDK observed launch/IPC paths and exercise relevant approved broker/breakaway controls | Unsupported/unobserved external paths remain OPEN; no broad administrator or service control inferred |
| O ownership | Finite fault matrix: false/raised initialize, observation error, hung call, parent crash and successor contention against same disposable authority | ACTIVE retained until exact observed worker/descendants closed; stale/reused/unknown identity negatives; fresh-dead reopen remains fail-closed |
| T teardown | Stop only bound disposable workers/terminals and remove owned fixture/profile resources after proven safe reconciliation | Actual remaining-process/root trace, exact cleanup receipt and host disposal; unresolved effects retain blocker and owner handoff |

Stages L/I are compatibility-first. A failure ends later effect stages without retries. L/I PASS does not qualify S/R/E/O or a production descendant verifier. Passing only selected Q2 cases yields a partial matrix, not full Q2 PASS. Real broker/account and financial fields remain outside the disconnected scope. G03-B producer transfer/migration, G04 and M1 remain OPEN.

## External input bundle and next handoff

The smallest actionable operator handoff is: (1) selected disposable VM/session facts M01–M02 and owner; (2) exact Python/wheel/native DLL and terminal distribution receipts M03–M07 plus two clean canonical bindings; (3) proposed trace collector and zero-loss self-test plan M09; (4) ownership/effect/teardown allowlists M08/M10/M11. Contractor then validates a filled manifest and dispatches the bounded research worker source TIP, reviews its exact bytes, and presents the final physical manifest for the affected execution decision. No current VPS call or secrets are needed for preparation. Do not create a new launcher to compensate for absent operator facts.
