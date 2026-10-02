# TIP-057R-Q2 — Disposable SDK compatibility readiness

Date: 2026-10-02. Status: **PLANNED / ENVIRONMENT NOT SELECTED / NO EFFECTS AUTHORIZED**. Q1's 16/16 Windows fixture PASS and G03-A source proposal do not qualify Python/MetaTrader5 IPC or authorize creating/stopping terminals on the current VPS.

## Smallest useful qualification

First test whether the exact Python/SDK can load and use the necessary IPC inside the preventive boundary. Matched unrestricted controls must use the same exact dependencies, roots, session and observation path. A module import PASS is not an attach/no-start PASS. Restricted access may make the SDK unusable; retain that failure as a valid research result rather than changing privileges to force compatibility.

Proposed disposable scope uses two clean installation/data-root bindings with no saved account/credential and no production state. It can test disconnected/null output and exact roots plus process launch behavior. It cannot certify connected financial fields, real broker behavior, the actual current VPS or the later two-binding/client pilot.

## Required concrete environment manifest

Every row is currently **UNKNOWN / NOT QUALIFIED**; no hostname, example path, prior MT5-2 build or dependency minimum is substituted for actual evidence.

| Required item | Evidence before execution |
|---|---|
| Disposable Windows host | Selected owner, host/VM identity, creation source, isolation from current VPS, persistence/teardown responsibility |
| OS and process context | Exact build, architecture, actual user/session/desktop, privilege/token/console mode, existing ambient JobObject restrictions |
| Python and SDK | Exact Python runtime/architecture, SDK version, wheel hash, native extension/DLL hashes and provenance; fixed rather than minimum dependency range |
| Two clean bindings | Actual terminal executable/build/hash and canonical install/data roots, unique generation/identity, no saved credentials/accounts and no production clone |
| Preventive mechanism | Restriction effective before SDK import/initialize, actual token/child policy, privileged-handle exclusions and exact permitted IPC resources |
| Positive controls | Existing attach works unrestricted; stopped/race unrestricted SDK control actually demonstrates the relevant launch path; broken launcher is not denial proof |
| Process observations | Birth/exit trace records transient processes, exact identity/parent/roots and broker/uncontained paths; before/after snapshots alone cannot prove zero starts |
| Lifecycle and rollback | Exact worker/terminal ownership, bounded termination/wait, retained uncertain authority, allowed provisioning/start/stop/teardown list and verifiable cleanup |
| Effect policy | Only selected disposable terminals; no login/password/server, order/trade, account copying or AutoTrading changes; reviewed network/provisioning scope |
| Acceptance scope | Supported exact version/topology and known unsupported paths; strict no-start remains required |

The current repository only declares `MetaTrader5>=5.0.6147`. Neither installed SDK hashes nor a selected disposable environment can be inferred from that lower bound. G03-A cannot authorize this physical manifest by source CI alone.

## Proposed execution stages after a separate environment decision

| Stage | Result required | Honest failure / limit |
|---|---|---|
| Q2-L load | Restricted Python+exact SDK import works, with actual token/process/evidence and matching control | Load failure means compatibility OPEN; do not grant broad access to current terminal/config |
| Q2-I attach | Both clean running bindings attach with exact observed roots/processes; disconnected values remain null | No account fixture can qualify real financial/session fields |
| Q2-S stopped target | Matched unrestricted SDK launch works; restricted attempt produces zero terminal births and explicit failure | No working control or trace coverage means OPEN, not PASS |
| Q2-R discovery race | Deterministic target exit after discovery but before initialize; preventive restriction remains in place; zero births in the restricted path | Repeating snapshots or detecting wrong binding after an effect is insufficient |
| Q2-E escape coverage | Relevant broker/out-of-process/inherited/breakaway paths are examined with qualified controls | Ambient job-denied breakaway or unknown SDK launch path remains OPEN |
| Q2-O ownership | Fault/hang/parent crash retain exact durable authority until qualified closure; evidence/cleanup agree | Already-dead fresh identity uncertainty remains fail-closed; no broad kill/TTL clear |

Use the selected real console/session mode. Q1's no-console `0xc0000142` remains unresolved and must not be promoted to a runtime default. No SDK load, terminal setup, process tracing installation or VM provisioning is performed by this document.

The actual SDK can fail because the sandbox blocks access required for IPC; this is a mechanism compatibility question, not a reason to relax no-start. If the preventive boundary and required IPC cannot coexist, keep targeted IPC disabled and return to a reviewed product/vendor boundary decision. A disposable Q2 PASS would still require G03 product producer/migration proof, actual client schema and guarded two-binding acceptance before TIP-057R/M1 is qualified.
