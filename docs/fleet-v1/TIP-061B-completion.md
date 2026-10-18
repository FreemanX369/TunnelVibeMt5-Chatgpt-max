# TIP-061B Completion Report

STATUS: DONE for verified principal and node writer source behavior. TIP-063 worktree implementation is owned and reported separately; physical qualification and platform CI remain separate gates.

`GatewayPrincipalAuthority` issues finite Ed25519 certificates bound to a client public key, installation/session, scopes and expiry. Requests prove possession of that client private key over exact method/path/body bytes, audience, certificate, timestamp and nonce. Durable admitted commands bind the original payload, project/target and principal/assignment/writer epochs. A signed node cannot invent an unadmitted writer operation. Private client keys and principal HTTP headers are absent from ordinary receipts and authority state.

`NodePrincipalRuntime` verifies the actual gateway command and signed assignment, retains one authoritative writer fence per project, and requests a fresh signed gateway proof for each source/session phase. Every phase intent precedes its effect and cannot be issued twice after a lost acknowledgment. Source and session commits reuse the existing atomic source write, checkpoint and immutable session CAS under the same `fleet_source_guard` mutation resource used by routed native execution. Placement advances through the existing exact CAS; old freezes become explicitly stale and new freezes observe the committed source.

Revoke, owner release and voluntary release by the currently assigned verified principal block new admissions immediately and remain DRAINING until the replacement fence and outstanding phases are acknowledged. A signed installed fence with pending intents is accepted as DRAINING so its installation command has a durable outcome; it cannot publish release. Expiry/heartbeat do not reassign a writer. A crash reconciles only original bytes, operation and epochs. Finite owner-approved drain recovery can complete an original session phase that was never issued, or recover the exact session commit already completed. It cannot write new source, adopt a successor or reissue an uncertain prior session phase. Changed/unknown source stays DRAINING. Same-journal typed resolution links preserve an original UNKNOWN record and prove its exact completed original drain outcome. Configured worktree recovery binds the actual complete quiescent worktree head and closed Git process steps; absent worktree authority is explicit null.

FILES CHANGED:

- `app/vibemql5/fleet/principals.py`: gateway certificate/client possession verification, assignments, admitted commands, durable phase authority/ACKs, DRAINING and signed exact-intent reconciliation, configured recovery heads and typed resolution evidence.
- `app/vibemql5/fleet/writers.py`: immutable sealed node commands/phase fences, source/session commit boundaries, crash reconciliation, native exclusion and placement advance, voluntary release and old-intent drain completion.
- `tests/unit/fleet_writer_fixture.py`: ephemeral client/node/gateway Ed25519 keys and actual verified local HTTPS fixture.
- `tests/unit/test_tip061b_principals.py`: lifetime/thread fences, policy bounds, corruption, durable clock high-water, authenticated replay and unadmitted operation denial.
- `tests/unit/test_tip061b_writers.py`: actual source/session bytes, replay/CAS, labels/tampering, native exclusion, crash/reopen, revoke/drain, unknown bytes, voluntary release and new source denial.
- `tests/unit/test_tip064_writer_resolution_https.py`: actual signed source UNKNOWN, installed pending fence, exact owner drain, gateway/node resolution heads, stored receipt tampering and immutable original failure.
- `tests/unit/test_tip061b_absence.py`: pure read-only absence without authority initialization, unknown/data/owner/temp markers, actual closed writer, non-null worktree checkpoint and historical replaced gateway assignment denial.

TEST RESULTS: 17 principal tests, 13 writer tests, 12 absence tests and 1 genuine HTTPS domain resolution test PASS (43 total, zero Linux skips). Genuine TLS all-journal recovery additionally verifies persisted principal/writer phase history and read-only absence. Logs and JUnit are retained under `evidence/tip061b`.

ISSUES / LIMITS:

- Disconnected revocation is not instantaneous; installed fences plus the fresh gateway proof and DRAINING protocol define the supported boundary.
- EMPTY_ABSENCE is a signed evidence kind for a device that has no local authority data/markers and no gateway writer history. It grants no writer authority. Existing or inactive stores remain required evidence even if configuration disables them; no helper opens, initializes or deletes them.
- Unknown prior phase/source/session effects block successors. No TTL reclamation, automatic adoption, worker-death inference, force-clear or raw-source diagnostics are used.
- An issued/UNKNOWN session phase with no confirmed session commit remains blocked even when the current revision is unchanged. No force-clear or phase reissue API is provided for this case, and supported restore cannot resolve it. A future recovery protocol would need concrete prior worker/effect closure plus durable phase history; unchanged revision alone is insufficient.
- VM, installed SDK, actual native processes and external deployment remain deferred. Temporary local TLS fixtures establish source protocol behavior only.

DEVIATIONS: none. Concrete optional drain authorization and typed UNKNOWN resolution were approved by the Contractor within M5. Actual Git worktree effects remain TIP-063's disjoint Builder responsibility, using these same sealed command/phase APIs.

Current shared fixture hashes are retained in [the current source manifest](evidence/tip061b/source-manifest.json). The [asynchronous CI refinement](TIP-064-async-CI-refinement.md) adds sanitized writer-admission failure context while preserving its 1000 ms timeout; it also verifies normal native worker-return/drain ordering. The previous shared-fixture manifest is retained separately as `source-manifest-before-async-ci-refinement.json`; original M5 test counts retain their historical meaning.
