# TIP-056 — Qualified scoped capacity completion evidence

Builder: `fleet_transport_build`. Date: 2026-10-03. Status: scoped concurrency source implemented and combined source matrix passed. Default production is one common native slot. Physical Windows independence/load/SDK tests and signed profile activation remain deferred.

## Scope and YAGNI-3

Independent terminal workloads need one atomic authority for both the complete physical resource set and device capacity. The source reuses SQLite WAL/FULL, the existing OS writer lock and exact process ownership semantics. It adds one finite scoped coordinator and one required signed installation profile, with no generic scheduler, remote capacity flag or free-RAM admission rule.

`resources.py` supplies the serialized foundation under the actual existing common native lease. `scoped_resources.py` supplies the qualified capacity path. M2's actual routed native driver and M1's SDK controller consume the sealed scoped lease and its authority; this is an execution path, not an unused reservation table.

## Implemented contract

| Acceptance | Source/evidence |
| --- | --- |
| Required signed qualification profile | Ed25519 `fleet.capacity-profile/1` binds owner key, device/install epoch, full current product candidate, runtime, terminal generations, exact executable/data/include/agent paths and observed physical identities, capacity, conflict matrix and explicit measured load/closure receipts. No qualified numeric defaults are invented. |
| Full source bundle, bounded parsing | Local admission pins the entire current product manifest. Gateway verifies the same complete product file/hash set across configured OS roots. Missing, extra, duplicate alias or two-file substitute manifests deny even with a valid signature. Marker/source/receipt reads have per-file, cumulative and stable-identity bounds. |
| Windows stable file reads | The bounded reader uses retained Win32 file ID, size and basic metadata, then reopens the pathname through the same read-only API before releasing the original handle. It rejects reparse/nonregular files and grants no write/delete sharing. It does not compare incompatible descriptor/path stat metadata. Native and SDK hash readers reuse the same finite helper. |
| Atomic capacity and physical resources | Durable FIFO WAITING → ACQUIRED admission reserves every resource and one device slot in one transaction. Inode aliases, canonical/ancestor overlaps and per-node SDK IPC serialization conflict. Expired/abandoned/unknown reservations are retained rather than reclaimed. |
| Exact producer lifecycle | Sealed lease carries root/token/profile/reservation and the actual authority. ARMED → CREATE_ATTEMPT → BOUND precedes resume. Release needs actual exact retained process exit and proven descendant closure, or exact zero-attempt ARMED closure. An uncertain phase remains UNKNOWN/occupied after restart. |
| Shared legacy/routed admission | No marker preserves existing global behavior and capacity one. Presence of a valid or malformed marker blocks unsupported legacy/global effects before mutation. Qualified native and SDK paths select their scope internally from the verified installation; HTTP callers cannot select a namespace. |
| Read-only SDK worker proof | Restricted worker reads bounded stable files and a checkpointed SQLite snapshot copied into memory. It cannot open a writable coordinator, guard, WAL or shared-memory file. Profile/owner/candidate/runtime, parent and exact BOUND worker identity must match. Synthetic persisted record provenance is denied in production views. |
| Remote higher-capacity delivery | A verified installed roster binds current admitted node/route. Gateway journal retains the operator-approved slots and exact physical sets; heartbeat/free RAM cannot grant capacity. Node executor is bounded by the sealed verified roster; owner control/heartbeat/cancel stays live while native effects execute. The finite installed-profile registration helper supplies only verified marker and bounded receipt bytes. |
| Persisted approval trust | Gateway stores bounded original signed profile and load/closure bytes, then re-verifies signatures, exact full source bundle and receipt bindings on reopen and before higher-capacity observation or poll. The currently configured owner key supplies trust; the stored proof cannot choose its own signer. Missing or changed current trust fails closed. |
| Meaningful concurrency fixtures | Two actual OS producers acquire distinct scopes concurrently; shared roots, aliases, per-node IPC, FIFO/capacity, schema tampering, faults and unknown restart deny unsafe successors. Gateway/node two-thread fixture holds the actual scoped authority. Synthetic profiles do not activate physical qualification. |

## Required owner-run qualification after source handoff

1. Freeze the exact source candidate, signed shared native runtime roster, Python/Windows/session and every target-specific native/SDK qualification. Verify every executable, compiler, data, Include and local-agent binding independently.
2. Measure simultaneous independent compiler/tester/SDK workloads under the proposed capacity. Record explicit duration/completed work and CPU, RAM and phase-latency measurements with owner-selected limits. Verify SDK IPC remains serialized and conflicts with the selected native roots.
3. Exercise suspended launch/create/bind/resume faults, exact Job Object worker/descendant closure, PID reuse, restart, cancellation, source changes, overlapping roots/hardlinks and unsupported legacy admission. Unknown ownership must retain the resource/slot fence.
4. Sign exact load and closure receipts, then sign the capacity profile with its required candidate/runtime/roster/epoch bindings. Install only during the explicit quiet migration after common global ownership is actually CLOSED. Startup never creates or overwrites a profile.
5. Register the same signed profile through authenticated HTTPS under the current route/session. Verify bounded remote fanout, live heartbeats/cancel, full-resource conflicts and exact result attribution before physical activation.

No Windows private-key ACL, MetaTrader/SDK behavior, physical independence or load limit is certified by Linux fixtures. This container cannot qualify an external child process identity; its process-closure fixture explicitly verifies retained CREATE_ATTEMPT denial when that namespace is unqualified. Actual Windows handle/Job Object closure remains an owner-run gate.

## Validation

The Builder's combined source snapshot passed **378 tests with 7 Windows-only skips**; root's final matrix covers subsequent CLI pairing-failure assertions added by the integration owner. `test_tip064_capacity_https.py` adds actual temporary-CA HTTPS signed roster registration and bounded two-worker admission under actual harmless scoped leases. Heartbeats/status remain live, and a conflicting third job waits until closure. Separate fixtures exercise two concurrent OS producers, same-resource denial, uncertainty retention, read-only SDK scope verification and changed/missing current approval trust. JUnit, exact command and owned source hashes are recorded with the TIP-060 handoff.

Tests do not relabel harmless callbacks, signed protocol claims or source branch coverage as a physical pass. Higher capacity remains unavailable unless its exact required profile and installation evidence verify; default global capacity one remains intact.

Windows candidate `3b955d6` exposed the earlier descriptor-versus-path stat comparison failure. The retained-handle correction and portable historical path predicate pass the affected Linux suites: 105 passed, one Windows-only skip. New fixtures exercise actual bounded reads and retained-file replacement/write rejection. The next root CI candidate must validate the actual Windows semantics; this follow-up does not claim a Windows pass.

Final POSIX admission refinement adds `O_NONBLOCK` to the existing retained read open, allowing regular-file metadata validation to reject an actual FIFO without waiting for a writer. A subprocess deadline safely exposed the prior five-second hang; the corrected fixture returns `SCOPED_INPUT_INVALID`. Regular-file bounds, stable identity/path verification and Win32 FileId128 metadata/no-write-or-delete sharing are preserved.

The final focused scope/roster/capacity/SDK/history/native diagnostic is **214 passed, one Windows-only skip** in 4.67 seconds. New log/JUnit files are `evidence/tip060056-final-refinement.txt` and `evidence/tip060056-final-refinement.xml`. `evidence/tip060056-source-hashes.json` now records current owned bytes, the separate focused receipt and exact command; its historical 378/7 matrix and 105/1 follow-up remain unchanged. The root's next exact-candidate Linux/Windows matrix controls acceptance of this refinement.

Candidate `ebbb56c` exposed a fixture-only source-manifest separator assumption: the duplicate-alias case split a Windows path using POSIX separators before reaching its signature/source denial. The fixture now normalizes separators while retaining the same self-consistent signed duplicate and rejection assertion. Together with short M2 oversized-record IDs and valid worktree Git include syntax, the focused three-suite Linux diagnostic passed **141 tests, zero skips**, 14.07 seconds. Separate `evidence/tip060056-windows-fixture-refinement.txt`/`.xml` and current hash JSON record this later snapshot; no earlier counts are repainted and exact Windows confirmation remains pending.
