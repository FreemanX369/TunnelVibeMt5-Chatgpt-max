# Builder completion — TIP-058B / 059 / 062A and node transport witness

Status: **DONE for the owned source modules and portable fixture criteria**. Final composed client/runtime Windows CI and physical VM/SDK/MT5 qualification belong to Contractor verification and the deferred owner test. This report does not certify a live endpoint, machine clone prevention or real account observations.

Methodology: Vibecode Kit v6 Builder. YAGNI-3 established the need for authenticated outbound routing/bounded observations, reused stdlib HTTPS/SQLite/file locks and locked Ed25519 support, and chose finite transport/controller/broker APIs. The owner authorized continuous source completion without separate TIP approval stops. Parent source checkpoint is Draft #64; source hashes below are local candidate hashes, not a Git commit claim.

## Files owned

Created `fleet/wire.py`, `fleet/node_keys.py`, `fleet/transport.py`, `fleet/read_broker.py`, `fleet/node_transport_journal.py`; created the 058B transport, 059 broker and 060C node transport tests. Declared direct `cryptography>=50,<51` dependency in `pyproject.toml`; the bootstrap lock already pins 50.0.1. Added [protocol](transport-protocol.md), [portable evidence](evidence/tip058b/portable-unit.log), [JUnit](evidence/tip058b/portable-unit.xml), [composed source log](evidence/tip058b/composed-source.log) and [JUnit](evidence/tip058b/composed-source.xml), [source hashes/runtime](evidence/tip058b/source-hashes.json).

Gateway control/restore/principal stores, SDK controller/qualification, durable native/resource modules, domain composition, CLI/MCP and deployment handbook remain their named Builders' ownership. Their APIs are composed through finite reviewed paths; no source overlap or remote mutation was performed by this Builder.

## TIP-058B source acceptance

| Acceptance | Result and evidence |
|---|---|
| Exact canonical body/method/path/device/key/route/time/nonce/audience Ed25519 | PASS: real ephemeral Ed25519 sign/tamper/exact-byte/audience tests; immutable sealed body projections and replay-verifiable signed recovery envelope |
| Strict finite JSON/header/path/size grammar | PASS: duplicate headers/keys, malformed UTF-8/surrogate, boolean numeric fields, NaN/overflow, unknown fields and capacities deny |
| Atomic grant/nonce/logical receipt coupling | PASS composed with 058A `consume_verified_grant`: fresh signed pair retry recovers original logical receipt, route zero stays historical evidence; old route/key and replay deny |
| Verified HTTPS singleton event owner/outbound client | PASS: temporary CA real HTTPS, hostname/CA failures, no insecure context, separate clients never open/start gateway; owner thread assertion and sanitized errors. Trusted server-context fixture serves after original key/certificate paths are deleted, proving no reopen |
| Total HTTP boundedness | PASS: slow fragmented headers cannot renew the accepted TLS/header/body deadline; response parser and snapshot calls borrow one absolute deadline |
| Session collision/reconnect and physical distinction | PASS source: concurrent active sessions conflict, same route retained; heartbeat labels transport presence without SDK/account evidence |
| Explicit per-install key bootstrap | PASS portable: exclusive create, restrictive POSIX load, public-only receipt and no overwrite. Windows creation sets current owner and protected DACL using explicit `WRITE_OWNER`/`WRITE_DAC`; loading checks current/SYSTEM owner plus exact DACL on one retained handle. Actual Windows CI remains required |

## TIP-059 source acceptance

| Acceptance | Result and evidence |
|---|---|
| Frozen exact target/operation/digest/deadline | PASS: command, poll, admission and result bind complete route/device/terminal/generation; no alias or MT5-2 fallback |
| Current command revalidation before SDK | PASS: sealed one-use `NodeReadAdmission` requires actual TLS poll delivery and fresh `/read-authorize`; interrupted/completed/expired/stale session/route deny |
| Result attribution and idempotency | PASS: identical results recover receipt; changed/cross-target/stale route/late result conflicts or denies; restart returns `READ_INTERRUPTED` |
| Callback once across loss windows | PASS: result ACK lost before and after gateway commit reuses the exact cached observation; no second callback/initialize |
| Per-node serialized lifecycle and production qualification gate | PASS source: default adapter fresh-validates local registry and denies SDK; installed `QualifiedReadAdapter` requires sealed operator installation plus node read admission and full routed attribution |
| Strict positive observation projection | PASS: terminal six/account 21 allowlisted fields, masked login, exact observed process/binding, `PROVEN` cleanup/`CLOSED` ownership; raw login/secret/nonfinite/unproven/future result rejected |

## TIP-062A source acceptance

PASS: bounded fan-out/row count/queue and one monotonic aggregate deadline; exact per-target source/time/age/freshness/status/reason; partial requested/succeeded/failed coverage; unavailable/disconnected accounts are null. Snapshots are explicitly non-atomic and contain no totals, FX, account identity inference, automatic charts/rates/ticks or captures. Production gateway rejects `SYNTHETIC_TEST`; the explicit test broker exercises positive routing with this unmistakable source label.

## Source 060C and runtime extensions

The independent configured `NodeTransportJournal` commits exact nonce/audience/device/key/path/route/time/body/request hashes before HTTPS and a matching gateway control head/response digest after validated success. No body, pairing secret or private key is persisted. Lost/rejected/missing replies remain pending across reopen and later successful requests; capacity denies rather than deleting uncertainty. Signed challenge witnesses retain the latest ordinary head; recovery-lane ACKs never pretend to advance a live ledger. The control/restore Builder owns the complete fenced coordinator; missing/newer/pending witnesses cannot silently clear restoration.

The readonly `assert_pair_replay` helper permits only the exact interrupted initial bootstrap: nonempty validated history, every intent on `/pair`, exact body SHA and configured pre-pair route, and unchanged journal identity/key/audience. Changed grant/secret/operation/revision/route or mixed authority history denies. It never clears an old pending request. A genuine TLS test loses the first pair ACK, closes/reopens the journal, recovers the original revision/route receipt with a fresh signed retry, and then proves a heartbeat prevents further bootstrap replay. The helper reuses existing journal validation and bounded wire encoding without introducing another pairing store.

The finite `NodeRpcProxy` passes native effect and writer phase authority and domain results to the control event owner. Native authority retains event and predecessor receipt alongside phase/sequence/challenge and a required nullable process digest. Process-bound authority waits for exact current progress ACK; a lost ACK issues no authority. A bounded async dispatcher can run native/cancel/source/worktree callbacks without stopping heartbeat/poll. Each step sends heartbeat first and services one authority round with a shared heartbeat-interval budget, followed by one bounded result drain. The portable blocked harmless-callback and authority-burst tests prove the control owner continues heartbeat, authority executes on the owner thread, and expired queued RPCs never later issue authority. The composed durable-native/TLS workload test belongs to TIP-064. Default capacity remains one; `/capacity/register` installs the separate verified signed roster with bound load/closure receipts, never a heartbeat claim.

The bool-only trusted stop seam `step(poll_commands=False)` suppresses new workload admission while retaining heartbeat/RPC/drain and finite signed `CANCEL_ONLY` polling of explicit owner cancellation for an already admitted exact job/process. Both controller and client separate workload/read polling from the cancel lane; a non-cancel response cannot execute. Runtime stop policy is owned by TIP-064 and may report `STOP_PENDING` while continuing service; it never turns a timeout into native termination or proven closure. The actual TLS fixture covers stop, withheld inventory, later owner cancellation, lost terminal ACK and eventual drain without repeated effect. Finite `/jobs/recover` and signed `/jobs/recovery-witness` transport carry read-only challenge-bound historical terminal references without changing original UNKNOWN/capacity or executing a native effect.

## Test result and remaining gates

Owned focused suite: **72 PASS, zero failures/errors, two Windows-only skips**. Combined owned suite plus TIP-064, gateway capacity, native authorization and A coordinated restore: **147 PASS, two Windows-only skips**, including actual temporary-CA HTTPS native heartbeat/cancel/lost-ACK, stop/owner cancel, history-only recovery, initial CLI pairing loss windows and principal-only guarded source flows. The additional full-journal HTTPS restore suite passes **three cases**, including the current `NodeRuntime.reconcile` helper with committed nonempty worktree/domain/principal witnesses accepted and reverified by A. Runtime: Python 3.12.14, pytest 9.1.1, local cryptography 50.0.2. The retained-handle wrong-owner fixture honestly requires Windows and normal-token permission to assign a foreign owner; it enables no privilege. The held protected staging-directory rename/key fixture also requires Windows. Portable owner/DACL contract checks do not qualify either Windows API branch. Original first-run escaped-surrogate failure was fixed by strict nested Unicode/numeric validation. Bootstrap-pinned 50.0.1 and Windows branches must be verified on the exact published candidate CI; no local result is substituted for that evidence.

Owned source freeze: no further changes are planned after these refinements; hashes describe the local owned files. Independent read-only review of TIP-064 continues and does not certify its unverified startup or shutdown changes. Contractor publishes and verifies the immutable integrated candidate.

Remaining physical gates: actual HTTPS endpoint/provider/certificate/account settings; protected Windows installation/key/clone behavior; two-node/two-terminal real SDK preventive no-start/process/descendant/closure qualification; broker/clock/restart/load/soak and all scoped native topology evidence. The source contains prepared positive SDK/native authority paths, while actual activation requires their separately verified installation/profile. No live VM, MT5, account, credentials, AutoTrading, deployment or merge action was performed.
