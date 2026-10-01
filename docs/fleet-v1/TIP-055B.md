# TIP-055B — Windows lease release liveness

Status: DISPATCHED under owner continuation “Duyệt tiếp tục theo plan”, 2026-10-02T02:12:19+07:00. Priority: high bounded corrective maintenance. Dependency: verified main `db9a12895c1b908fb6b0e61f89f9d76db1b04415`, tree `ac094ada3c0817515aec49062556843d5c0ba076`. This is not a new fleet architecture or native capability.

## Context and evidence

[Issue #56](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/issues/56) retains real Windows CI WinError32 at owner-lock unlink and an isolated fault proof. The current release marks itself released before deletion; denied deletion leaves a live-owner lock and makes later release no-op. The initial failing run remains evidence; same-head rerun PASS is not a fix.

Main concurrency source SHA-256: `74700aa7db7ee5279dd1166bbcb5465ce939b1da06858cbbd6123fb1eaa365f4`, 19,649 bytes. VPS source: `bf7603ce7b2566eb13b3596944253dcee7005b22442b77dc3a2f9edc55c32c2e`, 19,896 bytes. Full AST is equal; three extra VPS comment lines must be preserved in the reviewed payload. Raw hash-verified drift snapshot: `/workspace/scratch/250985b4823e/runtime-drift-055b-concurrency.py`.

The isolated worktree has all 160 main blobs verified before copy. Its local synthetic snapshot commit is not a GitHub commit or remote parent. Existing venv: `/workspace/scratch/250985b4823e/audit/tunnel-venv/bin/python`; use this worktree's app on PYTHONPATH.

## YAGNI-3 and task

1. Necessary: an observed Windows release failure can strand serialized native/mutation work while owner process remains alive.
2. Reuse: existing queued file lease, ownership token, PID/FIFO/lock paths; inspect available read/retry helpers before adding one.
3. Smallest sufficient output: bounded release hardening and meaningful isolated/Windows regression. No broker, journal, shell executor, new MCP tool/suite or lock topology.

Builder repairs release liveness while preserving lease ownership and FIFO. Retry only diagnosed Windows sharing/lock errors for a fixed bounded interval; persistent/general permission, read corruption and other failures remain explicit. Check current ownership on retries; do not delete a token known to belong to a successor. Mark release complete only after confirmed deletion/absence or confirmed non-ownership; unresolved release must stay retryable. Preserve cleanup and existing Path-compatible APIs.

Decide minor retry constants/helper reuse within this contract and report reasoning. If safety requires changes to acquisition/fencing/schema/native routing or a wider redesign, report the concrete finding before changing architecture.

## Acceptance criteria

| AC | Required observable result |
|---|---|
| B01 | Given own lease and a transient Windows sharing/lock delete error, when release retries within its bound, then own file is removed and release completes exactly once |
| B02 | Given persistent sharing denial, when the bound expires, then failure is explicit, own file stays, release remains retryable; a later successful release removes it |
| B03 | Given a non-retryable error or unreadable/corrupt ownership, then no blind delete, no false released flag and explicit failure |
| B04 | Given another owner token appears before a retry, or two callers release the same lease object concurrently, then only the owning delete completes and a successor token is retained |
| B05 | Absent file, normal release and repeated completed release remain compatible; existing FIFO/live/dead-owner/native/mutation tests pass |
| B06 | Windows CI opens a real deny-delete handle on an isolated lease file, proves real sharing-denial occurs, releases the handle and proves bounded recovery; unavailable Windows mechanism is a gate, not silently labelled PASS |
| B07 | Existing catalog order/count/hash remains 85; fixed native MT5-2, global lease paths, native/mutation capacity and lock order remain intact |
| B08 | Deployed payload retains exact observed comments. Fixed compile and supported runtime-forensics can select the new isolated regression module without broad unit/live-chart execution or suite/API expansion |
| B09 | Existing failed CI evidence is retained; report distinguishes injected POSIX fault, actual CI Windows handle and later deployed fixture evidence |
| B10 | No deployed identity bootstrap, native job, live chart, account/credentials/AutoTrading or generic PowerShell MCP; no direct commit main |

Tests must use temporary roots and intercepted operations, except the actual Windows handle case, which still uses a temporary lease file. A source-only assertion or a longer FIFO test timeout is insufficient. Use a filename compatible with the existing runtime_forensics selector; do not duplicate tests or invoke real deployed state in fixtures.

## Completion and deployment

Builder reports DONE/PARTIAL/BLOCKED, changed files, each AC result, runtime/comment manifest, residual risks/deviations and exact local results. Contractor reviews behavior and exact delta, publishes a PR from main, verifies all four exact-head CI workflows and records actual Windows handle results before any deployed-fix claim.

Owner continuation covers this bounded corrective PR and supported guarded rollout of the verified fix. Runtime qualification uses fresh idle/healthy A/B/C guards; hash-verified drift-preserving payload; checkpoint and exact live CAS; compile/isolated forensics; B/C then detached A refresh; postchecks of catalog, inventory, queue/locks and current source hashes. Existing integration backup/new-file recovery limitations remain explicit. No native operation is needed.

Real M0 enrollment/backup/physical bindings remains OPEN and independent: fresh inventory still has five UNENROLLED/UNQUALIFIED rows. TIP-057R spec may be refined, but its build retains the actual enrolled-target dependency. This fix does not supply enrollment receipts.
