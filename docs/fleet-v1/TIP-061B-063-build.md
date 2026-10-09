# TIP-061B / 063 — Verified node writer and Git worktree isolation

Status: prepared for BUILD after 060 interface/source acceptance, under continuous source authorization. Reuse existing source locks/checkpoints/CAS/Continuity and node-owned project writer. This completes approved M5, not a generic remote shell or Repo Worker.

YAGNI-3: remote mutation and multiple agents require a writer fence and isolated source; reuse existing guarded mutation/revision history and Git worktree; implement narrow authenticated assignment and commit boundaries, no second Continuity system.

## 061B acceptance

* Gateway-issued cryptographically verifiable principal credential, finite scope, installation/session/assignment epoch and expiry. Explicit owner provisioning/revoke only; arbitrary `agent_id`/MCP metadata/labels do not authenticate. Private bearer material never returned in ordinary receipts/logs or packed in clone/repository. Authenticate client at transport before selecting node mutation; node verifies gateway principal evidence and assignment owner.
* One writer per project on owner node. Freeze exact project/revision/checkpoint/source SHA/bytes, target/route, principal/session/epoch and logical operation before dispatch. Pre-source and pre-session commit recheck authoritative writer fence under existing lock; stale/lost/revoked principal cannot commit. Same operation replay returns original committed/recovered receipt; changed request conflicts.
* Reuse atomic source write, checkpoint and immutable session revisions. Crash after source write/before session commit must reconcile exact original bytes/operation/principal; never apply mutation again or finish under a new writer epoch. Unknown effect blocks new writer/source action. Gateway stores references, not a second writable project history. Agent lease loss does not terminate native workloads.
* No shell/admin/secret capability routes. Finite guarded source mutation only, same-node source/executor. Tests include source CAS, double dispatch, epoch loss before both commits, crash/reopen/reconcile old owner, changed operation and no raw source/secret diagnostics.

## 063 acceptance

* Real Git worktree on project owner node with verified principal assignment epoch, frozen repository/base commit and bounded task/worktree reference. Create/remove only registered paths inside configured owner roots, no arbitrary repository/path/shell inputs. Reuse Git through structured argv and existing file locks; no shell command interpolation.
* At most one writer for one assigned worktree/project; validate canonical path/repository and base/HEAD at commit. Clean worktree prerequisite and changed-HEAD drift explicit. Commit source/result references with same fence/operation identity. Timeout/lease expiry is not proof a worker died or proof worktree safe to reclaim.
* Recovery retains unknown in-flight native/source outcome and old assignment provenance. New owner cannot adopt another writer's partially committed work without exact reconciliation. Continuity remains the semantic task history.
* Tests use temporary real Git repos/worktrees for isolation, clean/dirty/base drift, stale owner/epoch, path traversal, competing assignment, commit interruption/replay and no unintended main checkout modification. No external repo deploy/merge action.

Each report maps actual source and tests to its TIP. Source-qualified authentication/worktree behavior is distinct from later physical client/process qualification.

## Contractor implementation decision — 2026-10-03 continuation

A static signed credential cannot establish current revocation across a disconnected node. Use the finite signed node route `/fleet/v1/writers/authorize` for fresh proofs bound to the exact principal, assignment, writer epoch, operation, intent hash and phase. The node verifies both its locally installed signed writer fence and the gateway proof before the source commit and again before the session commit. Persist issued phases and their exact acknowledgments; lost acknowledgment never permits another source effect.

Revoke/release blocks new admissions immediately, then remains `DRAINING` until the node acknowledges the signed replacement fence and every issued pending phase is reconciled. Only then publish `REVOKED`/`RELEASED` and allow a successor. TTL, heartbeat or a caller label cannot reclaim ownership. A crash between commits may reconcile only the original bytes, operation and owner epoch; ambiguous outcome blocks successors. This makes the distributed revocation boundary explicit without changing the approved singleton gateway or node-owned source architecture. Include principal/assignment/phase heads in the joint recovery checkpoint.
