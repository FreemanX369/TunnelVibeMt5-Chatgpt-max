# TIP-060C Completion Report

STATUS: DONE for the conservative source recovery contract; platform CI and physical VM/SDK qualification remain separate gates.

Supported control restore explicitly stages schema `fleet.gateway.control/2` and preserves the complete original control ledger anchor before fencing. No automatic migration occurs on ordinary open. `RestoreCoordinator` requires an independently retained canonical checkpoint and Ed25519 operator approval for one fresh challenge, exact control anchor, registry/key/route/session scope, job mapping, and every configured domain/principal head. It admits only sealed signed node recovery requests and complete transport/job/domain/writer witnesses. Configured worktrees bind their actual durable, quiescent journal head and complete CLOSED Git steps into both operator checkpoint and signed writer witness; disabled worktrees use explicit null. A node configured without writer authority may supply signed EMPTY_ABSENCE evidence only when actual local writer/worktree data and markers are absent, expected worktree head is null, and gateway assignment/phase/command history for that device is empty. An inactive or unknown writer store cannot become absence by disabling configuration. A missing/newer transport head, pending intent, unmapped job, scope drift or missing journal evidence remains fenced. This supports the approved no-ledger-delta recovery profile; it does not reconstruct missing grants, nonce history or unknown rotations from an old database.

Control reconciliation commits while fenced, job and configured domain/principal journals finalize under exact proofs, and control READY is published last. All nested journal witness fields are validated by the concrete read-only journal verifier before any envelope or nonce is persisted. Durable coordinator phases resume after before/after publication faults. Expired approval on an unfinished phase requires a fresh signature from the same trusted operator for the same challenge, checkpoint and coordination scope. Earlier approval envelopes and digests remain bounded history. Reapproval changes no witness, nonce or ledger scope. Completed recovery opens against its completed timestamp and permits later legitimate admissions.

FILES CHANGED:

- `app/vibemql5/fleet/gateway_control.py`: explicit supported restore metadata, stable control head, conservative full-ledger comparison and concrete coordinated commit/READY hooks.
- `app/vibemql5/fleet/restore_coordination.py`: finite signed checkpoint/witness coordinator, durable nonces, phase receipts, same-scope reapproval and configured journal binding.
- `tests/unit/test_tip060c_restore.py`: signed checkpoint negatives, replay/corruption, phase faults and approval expiry/resumption.
- `tests/unit/test_tip060c_https_restore.py`: genuine local HTTPS empty/source/worktree/read-only full-service restore with real node transport intent/ACK history, actual principal source/session phases and temporary Git worktree CLOSED receipts. CLI `NodeRuntime.reconcile` builds actual worktree and read-only evidence; a closed inactive writer blocks that helper before transport intent. A genuinely signed false absence request cannot erase gateway writer history or persist a recovery nonce/body.

TEST RESULTS:

- 120 retained TIP-058A source tests PASS.
- 20 TIP-060C coordinator tests PASS, including denial of an unknown nested job field before persistence.
- 5 genuine HTTPS all-journal restore tests PASS: empty persisted journals, completed source/session operation, configured temporary Git worktree with complete closed process receipts, read-only absence success, and inactive-writer denial.
- Combined retained A plus recovery: 145 PASS, zero skips on Linux. Logs and JUnit are retained under `evidence/tip060c`.

ISSUES / LIMITS:

- Physical MT5, VM, client lifecycle and installed SDK qualification remain deferred by user instruction. Local TLS fixtures do not certify those environments.
- Operator checkpoint retention and trusted key configuration are prerequisites; database possession alone proves no latestness.
- Unknown source/native effects and unresolved key/route changes remain fenced. No force-clear, caller authentication boolean or arbitrary SQL callback exists.

DEVIATIONS: none from the approved conservative checkpoint contract. Domain/principal head and witness binding completes the explicitly approved full-service scope. The prior TIP-058A report and v4 evidence remain historical frozen evidence; this higher TIP changes the current control source and has its own manifest.
