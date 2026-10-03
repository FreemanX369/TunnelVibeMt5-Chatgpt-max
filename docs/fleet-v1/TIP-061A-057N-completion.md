# TIP-061A / 057N completion

Status: SOURCE_COMPLETE / PREPARED_NATIVE_ADAPTER / PHYSICAL_QUALIFICATION_DEFERRED. Continuous source authorization applies. No actual MT5/SDK/VM execution, operator trust installation, remote publication, production merge or deployment occurred in this Builder's work. The real dedicated native path exists behind the installed physical qualification factory; default calls remain denied.

## YAGNI-3

1. Managed native work needs exact placement, immutable candidate attribution and STRICT environment comparison before reservation or copies.
2. Reuse core immutable sessions/checkpoints/CAS, tester normalization, JobStore, ownership/leases, baseline metrics, compiler/tester drivers and M3 signed authorization/journal.
3. Add finite fleet placement/native contracts and trusted installed producer seams. Node-owned history, scoped exclusion and qualified handles remain the authorities for their respective boundaries.

## Acceptance result

| TIP acceptance | Implemented behavior and source evidence |
| --- | --- |
| 061A node-owned project | Placement overlays reference actual immutable core session/checkpoint/source identity; same-node source/executor and exact owner/device required. Legacy records remain unbound references. |
| 061A frozen iteration | Freeze exact target/generations/roots/source/session/writer reference before reservation. Default changes affect only subsequent freezes. Exact CAS and bounded durable operation replay preserve historical placement. Public stale resume reports explicit conflict. |
| 061A source advancement | `advance_session` CAS updates the placement overlay only after the new actual session/checkpoint/source commit. Old frozen placements and immutable revisions stay unchanged; M5 reuses the same source mutation resource. |
| 061A STRICT | Complete typed target/binding/build/model/logical config/effective calendar period/set/include/input/broker/history matrix. Missing or malformed fields yield UNVERIFIED; differences yield INCOMPATIBLE with bounded field reasons. Candidate source difference remains evidence; comparison never auto-promotes. |
| 057N separate request | `fleet.native/1` canonical request/hash/operation mapping binds placement, logical normalized request, explicit input hashes/bytes and STRICT build policy. Legacy hashing/replay functions are untouched and covered by regression tests. |
| 057N admission | Exact source/session/target/root, installed operator approval and fresh sealed gateway phase/effect proof precede producer work. Inventory-only route projection grants no native authority. Actual route authorization remains the M3 signed gateway boundary. |
| 057N real adapter | Qualified synchronous compiler/tester composition reuses approved driver seams. Exact bytes/snapshot feed deployment, immutable EX5 identity is checked before every tester boundary, and final result promotion has an explicit durable completed event. Persistent live handoffs remain unsupported. |
| 057N exact process ownership | Actual Win32 source creates suspended worker, binds exact independently observed identity and held no-breakaway Job Object before resume. Actual retained worker exit and zero active Job descendants are required for CLOSED. Unknown create/resume/publish/cleanup retains ACTIVE and handles; expiry never force-clears or kills a worker by itself. |
| 057N finite step expiry | Every concrete copy/preparation/create/resume/capture/terminate/result event has intent, fresh exact sealed proof and returned-action completion. A consumed action can complete after TTL; the next distinct action needs a fresh grant and predecessor receipt. Lost/expired-unconsumed/UNKNOWN effects cannot advance or retry. Cancellation binds the gateway-acknowledged exact process digest; cancelled compiler cannot start a tester. |
| 056 integration | Fixed installed marker blocks unsupported legacy native admission. Verified ScopedLease drives actual prepared qualified producer composition. Two independent project/terminal callbacks overlap while the global mutation guard only spans source snapshot capture. Signed common runtime plus deterministic per-target approvals prepare the actual two-target path. |
| Immutable concurrent source | Running scoped candidate uses an internally sealed atomic snapshot and original immutable history after M5 updates current source/session. Result stays attributed to the old candidate; public resume of that old placement remains explicitly stale. |
| Historical closure | `terminal_closure(job,request)` reads a finite request/job/target-bound receipt of actual phase CLOSED records plus normal outer lease return. It is published only after context exit and rejects pending/active/corrupt rows. It does not grant current execution or acquire/release ownership. M3 captures it for terminal recovery witnesses. |
| Installed trust | Fixed trust/approval/runtime files use retained-fd owner/mode/ACL protection, bounded reads, no symlink/reparse/hardlink aliases and stable metadata. Windows file-owner verification is supplied by the shared node_keys helper owned by the integration Builder; exact final integration checks remain required. |

## Verification

Owned M2 suites: **78 placement/native tests and 24 qualifier tests passed**. Four actual harmless Windows Job Object cases are platform-skipped on Linux. Prior related source/regression checkpoint: **340 passed, 7 platform skips**, in 19.22 seconds. After the retained-handle STOP refinement, current owned suites are **102 passed, 4 Windows skips** in 5.20 seconds. M3/064 recovery-projection integration is separately verified by its owners; an intermediate related run exposed three integration failures during those edits, which were reported for correction. Python compileall for owned source/tests and `git diff --check` passed.

The verification covers defaults/freeze/reopen/CAS/drift, actual immutable histories, typed STRICT fields/calendar/hash validation, bounded malformed state and duplicate JSON, native input/copy windows/EX5 drift, no effects on unqualified target, interrupted reserved publication, common/scoped ownership, two prepared concurrent producers, source advancement while running, signed process mismatch, consumed completion after TTL, lost grant after launch retaining ACTIVE/handles, explicit final promotion and historical closure corruption. Positive driver/signature/scoped source fixtures are explicitly synthetic seam evidence; they do not certify physical MT5 or install qualification.

Exact command and source hashes are in [TIP-061A-057N-verification.md](TIP-061A-057N-verification.md). The integrated Linux/Windows exact-checkout workflow must verify the final whole-build candidate after other Builders finish; these owned hashes are a source checkpoint rather than a production approval.

## API handoff

- `FleetProjectStore(root)`: `enroll`, `get`, `set_default`, `freeze`, `load_frozen`, `validate_frozen`, `resume`, `advance_session`. Calls require exact revision/hash/operation identities described in source signatures. Frozen writer labels remain UNVERIFIED_REFERENCE; M5 supplies authenticated principal/writer/source actions separately.
- `strict_compare(candidate,baseline,...)`: complete STRICT fingerprint and optional existing result metrics; typed comparison with `auto_promote: false`.
- `native_request(placement,logical_config,input_manifest,build_policy="STRICT")`, `native_request_hash(request)`, `request_from_preset(...)` prepare the separate native namespace.
- `RoutedNativeAdapter(root,authorization_provider=None)`: `reserve(request,node_operation_id,exact_fence=None)`, `start_reserved(local_job_id,request,exact_fence)`, `effect(local_job_id,phase,request,exact_fence)`, `terminal_closure(local_job_id,request)`, `has_retained_work()`.
- M3 owns trusted `authorization_provider`, `begin_effect`, `complete_effect`, `publish_process`. These are internal callbacks carrying actual sealed signed proofs and finite journal truth, never wire caller booleans. Preallocated local job ID and all job/session/request/target identities remain exact.
- `load_installation(root,request)` is the sole real activation factory; fixed trusted operator signing inputs and actual Windows runtime checks apply at each new effect. `SyntheticNativeAdapter` and private test factories cannot install it.
- Additive core `owned_launch`, `before_effect`, `after_effect`, `frozen_inputs`/`frozen_set_bytes` default to None; legacy launch and result behavior remain the existing path. Owned launcher rechecks its current sealed proof immediately after durable create-attempt I/O before CreateProcess.

## Stop and recovery review amendment

`has_retained_work()` checks current held process/thread/Job Object/ObservedProcess handles under the adapter guard, without polling or closing them. QA combines this with current futures and pending ACK maps: after a callback fails and maps clear, actual retained unclosed handles keep STOP_PENDING and the owner loop alive. A previous persisted UNKNOWN or empty launch object alone can drain the owner process while durable execution exclusion remains. The actual harmless Windows pre-resume fault case checks this distinction.

Historical recovery carries only the finite recovery outcome evidence projection and original receipt SHA, plus exact CLOSED phase proof; rich normal core/native records remain unchanged. Independent M2 review required real retained process/descendant evidence, finite global/scoped CLOSED records and exact process attribution. Pending/unknown/cancelled intent histories cannot grant new authority. M3 owns projection validation and actual TLS recovery tests.

## Explicit mechanism bounds and deferred work

Native inputs: up to 1024 files, 32 MiB each and 64 MiB cumulative, validated before reads; JSON records at most 256 KiB; project operation histories at most 256 entries. Product source manifest uses the complete bounded SDK/capacity algorithm; qualification file hashes stream at most 512 MiB and control receipts at most 256 KiB. Shared runtime roster has two to sixteen exact targets. Native event graph limits include 1024 include copies, bounded report/set targets and 100000 capture/total producer callbacks. Operational wait/timeout/capacity values are explicit signed policy fields.

Later physical work is described in [TIP-061A-057N-qualification.md](TIP-061A-057N-qualification.md): actual MT5 compile/pass/fail/full-period/root/stale/descendant/crash/cleanup/broker/session controls, interactive Windows and source/runtime builds, owner protected files, fixed operator signature, current gateway trust, exact resource/parallel load profile and source/payload pins. A signature authenticates operator approval, while retained physical evidence must support its claims. No real qualification or automatic baseline promotion is asserted here.

## Owned checkpoint

Canonical relative-path-to-SHA256-map bundle: `cd2dee85cb1aeeb9a7608ee8ed79ee2fb2914bc2cc1ceaf6ef973c8ad118353f`.

| File | SHA256 |
| --- | --- |
| `app/vibemql5/fleet/project_targets.py` | `1c60f34fa4fcd4c2d865532b4d18c8277512c849ae264089b9f2d68ef05e0d86` |
| `app/vibemql5/fleet/strict_baseline.py` | `db196ab0be627fb743e0e8d6365e034ee8ed062348794d6d52c0551ca1228802` |
| `app/vibemql5/fleet/native.py` | `48deaddd80324e67b14d1b63c0809a1bf6b449c66a4014c538a60d4862b2db6b` |
| `app/vibemql5/fleet/native_qualification.py` | `6f5f6f628d03727991c3e0b150f58e4cc4d93ab9e5c1b46bc1c4183441d16ab2` |
| `app/vibemql5/fleet/native_process.py` | `d61eb43c3fd9a143a53c9b8e813fcde20bb834f0a5c5da197d07a862662d8122` |
| `app/vibemql5/core/compiler.py` | `df3a3019dbd79a6081cf3df2bf2e1f3d7211a12bc53c5557033bb59e642d4589` |
| `app/vibemql5/core/tester.py` | `e8548bdd4aafd51589708676823164a78fcc1e265e2a1f73432990a757f7fa5a` |
| `app/vibemql5/core/native_ownership.py` | `857bef23426df32fbc41ae58e456a869c6533d3ab59b3dc2f6eba034cad20e87` |
| `tests/unit/test_tip061a_057n.py` | `9c64338cb23e17bb77924a68d5b86e73a8f344ac44b06fcbb4b703a062cafdbd` |
| `tests/unit/test_tip057n_qualification.py` | `7df0106f9f62ef4b9ac43dc5c6fb06259425a2dcc7cf0db863b5bd9a77a54c28` |
| `tests/unit/test_tip057n_windows_owned_process.py` | `4d34604cc59ffb0b113490c6f2a8247abb9aa94f6ea3fa42b21599b2b0be2b74` |
| `docs/fleet-v1/TIP-061A-057N-qualification.md` | `f33ba5d22873ef438d00fb11a2caa45f2d99faae9876bc510251922ad7c290d8` |
