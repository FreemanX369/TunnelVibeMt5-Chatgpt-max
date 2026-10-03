# TIP-058A — Builder completion report

Date: 2026-10-03, Asia/Saigon. Parent: Draft #64 `e74bdee81db3db3d5ae774a99a9146d74742ea8a`. Contract: [TIP-058A](TIP-058A-build.md), with the concrete atomic pairing boundary required by [TIP-058B](TIP-058B-059-062A-build.md). Continuous owner authorization permits the next source TIPs without individual approval stops.

Status: PARTIAL verification. Implementation and Linux verification are complete; exact-head Windows CI verification and Contractor acceptance are pending. No VM, MT5 SDK, deployment endpoint or actual node key was accessed.

## YAGNI-3

1. Durable routing, enrollment grants and replay proof need persistent control state before transport can safely expose them.
2. Reuse stdlib SQLite WAL/backup, SHA-256/secrets and the existing OS `_exclusive_file_lock`. No additional dependency is needed by this slice.
3. One concrete `GatewayControlStore` implements the state transitions and finite policies. It has no network server, native effect, generic transaction callback or authentication boolean.

## Files and behavior

* `app/vibemql5/fleet/gateway_control.py`: explicit initialize/open/close/snapshot, one canonical lifetime OS lock and owning thread, versioned SQLite state, expiring single-use hashed grants, key/route CAS, durable administrative request identity, replay nonces, consistent bounded backup and always-fenced supported restore.
* `tests/unit/test_tip058a_gateway_control.py`: independent QA owns this file, including actual cooperative child processes, crash boundaries, malformed state, logical replay, capacities and atomic verified-pair coupling.
* This report is the Builder's documentation. Contractor owns the dispatched contracts and aggregate verification documents.

Every receipt says `CONTROL_STATE_ONLY`, `NOT_VERIFIED` and `dispatch_enabled=false`. Public keys are shape-checked references. Grant secrets are returned only on first issuance; persistent data, snapshots, diagnostics and idempotent recovery contain no plaintext secret. Reopening never creates missing state or changes policy. Exact SQLite objects, typed records, operation-specific receipts and cross-record history are validated before admission.

Mechanism ceilings are explicit validation bounds, not defaults or a production security profile: waits at most 60,000 ms; grant TTL and nonce retention at most 604,800,000 ms; clock skew at most 300,000 ms; grant secrets 32–64 bytes; at most 4,096 devices and 65,536 grants/nonces/operation receipts; nonce at most 4,096 UTF-8 bytes and operation identity at most 1,024 bytes. Every actual policy value remains required. Retention must cover twice the allowed skew. Records are not silently evicted; full capacity fails closed. SQLite backup has a progress deadline using the explicit SQLite wait budget.

Administrative idempotency is distinct from transport replay. The committed logical request includes the original CAS inputs and excludes retry time. Replay lookup precedes current-CAS checks and never reconstructs a lost secret. New admissions retain the highest observed server wall time even on a semantic denial; backward wall time cannot resurrect expired evidence. A metadata-only wall observation can survive a denied/rolled-back mutation without changing route, revision, grant, nonce or operation state.

## Concrete 058B pairing boundary

`consume_verified_grant` is a narrow trusted internal API invoked by the sole wire controller after real Ed25519 verification. It rechecks grant/device/key/secret and original signed route, then commits nonce, grant consumption, resulting route and logical operation receipt in one transaction against the original pre-envelope revision. It accepts no arbitrary SQL callback or asserted authentication flag.

The initial signed wire route `0` denotes the grant's absent route only at this pairing boundary. Its nonce is retained as historical `purpose=PAIR` evidence under the original signed route; enrolled route starts at `1`. Normal `reserve_nonce` still requires a positive, active, exact current route, and the transport adapter must supply `expected_public_key`. A fresh-nonce retry of the exact logical pairing returns its historical receipt without pairing again. A later revoke, rotation or re-pair causes conservative denial of an old pairing retry; it cannot repaint current authority. The reserved `nodepair:` namespace is rejected by administrative operations.

## Acceptance and evidence

| AC | Linux source evidence |
|---|---|
| A01 | Missing/unknown/corrupt state, canonical spelling, duplicate actual cooperative writers, owner crash and cross-thread denial. |
| A02 | WAL/versioned transactions, strict records, exact schema objects and generation/history consistency. No terminal generation storage or mutation. |
| A03 | Required primitive policy, practical mechanism ceilings, mismatch/corruption and finite capacities. |
| A04 | First-return-only secret; wrong key/device/secret/expiry/route and reused grant deny without partial mutation. |
| A05 | Original-CAS logical retry after reopen; changed request conflicts; no eviction; admin/node namespaces distinct. |
| A06 | Pair/re-pair/revoke/rotation increments, exact key/route CAS and stable reopen. |
| A07 | Durable nonce replay, key/route/state fence, timestamp window, clock rollback and fail-closed capacity. |
| A08 | Before/after-commit faults and actual child crash leave original or complete state; bounded public errors. Atomic verified pair includes nonce/control/receipt. |
| A09 | SQLite backup consistency; supported restore remains `RECONCILIATION_REQUIRED` across reopen and blocks every admission/replay. No force-clear or unconditional mark-ready. |
| A10 | Focused Linux and retained M0/C1/G03A regressions; all 85 actual MCP schemas retained. Exact-head Windows CI pending Contractor publication. |

Frozen Builder verification: `test_tip058a_gateway_control.py` **120 passed, zero skipped**, 2.79 seconds on Linux. Independent final combined QA: **306 passed, three existing platform skips**, 8.83 seconds, with source hashes unchanged before/after the run. Retained M0 identity/release, G03A ownership and C1 reads alone: **186 passed, three existing platform skips**, 6.43 seconds. The focused suite includes direct verified-pair initial route-zero/fresh-nonce/reopen/fault/capacity and revoked/rotated authority cases, owner-thread and namespace separation, as well as relational corruption negatives. All 85 actual MCP tool schemas match the C1 baseline hash `64337437115a20a8555cc1214706a503b985195dbdbd219de2adfa35e2c8134d`.

Machine-readable evidence: [source manifest](evidence/tip058a/linux-source-v4/source-manifest.json), [JUnit](evidence/tip058a/linux-source-v4/focused.junit.xml), [raw log](evidence/tip058a/linux-source-v4/focused.log). Earlier evidence iterations are retained.

| Frozen file | SHA-256 | Git blob |
|---|---|---|
| `app/vibemql5/fleet/gateway_control.py` | `21d0dd452fbce40cf6eee8e30aedd6f77e17b96bd1b062c47e1e075566789939` | `08d4e5cd088b94ea892e2690ef81fb843a7a6881` |
| `tests/unit/test_tip058a_gateway_control.py` | `42fb7cdd29a94e29ef79e0b2a03773cb541a37d30f29bd5ac94c0b2352e303f4` | `a8ef9c43963a1bf762e3e780ed85e2289a03580c` |

Commands: `python -m pytest -q tests/unit/test_tip058a_gateway_control.py` and `python -m pytest -q tests/unit/test_tip055a_runtime_forensics_identity.py tests/unit/test_tip055b_runtime_forensics_release.py tests/unit/test_tip057rg03a_native_ownership.py tests/unit/test_tip057rc1.py`. The cached test environment is `PYTHONPATH=/workspace/scratch/250985b4823e/audit/tunnel-venv/lib/python3.12/site-packages:app:tests/unit`. Exact-head Windows receipts remain pending publication rather than being inferred from the previous checkpoint.

## Remaining qualification and limits

058A does not verify Ed25519 possession, physical clone uniqueness, actual TLS deployment, SDK readiness, native ownership or MT5 account data. Those belong to their own source modules and physical tests. A consistent old database copied outside the supported restore path cannot be identified as old using SQLite alone. Internally inconsistent accidental state is rejected; a coherent hostile rewrite is not authenticated by a database-only checksum. Node-journal reconciliation and independent anti-rollback witnesses are not fabricated here. Supported restore always fences control admission, with no completion bypass.

No change to legacy/native signatures, fixed MT5-2 targeting, M0/C1 evidence, MCP catalog or historical request hashing is part of this slice. No GitHub mutation was performed by the Builder. Contractor publishes and verifies the checkpoint while the remaining approved source work continues.
# Current cumulative source pointer

The frozen TIP-058A rows and counts above retain their historical checkpoint meaning. Later control/restore refinements are documented in [TIP-060C completion](TIP-060C-completion.md) and its [current source manifest](evidence/tip060c/source-manifest.json). The whole-update [Contractor verification](source-update-verification.md) supplies exact-candidate acceptance; earlier hashes are not overwritten to represent current shared source.
