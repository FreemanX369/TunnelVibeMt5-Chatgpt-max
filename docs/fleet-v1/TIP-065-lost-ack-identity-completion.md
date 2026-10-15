# TIP-065 — Lost-ACK identity independent review

Status: fixture exception-identity repair PASS; delivered source gate PENDING 8/8.
Historical storage/scheduling causes OPEN/UNKNOWN. No overlay deployment/restart;
physical qualification NOT_RUN. [Contract](TIP-065-lost-ack-identity.md), 2026-10-05.

Exactly one test file changes from rejected d9adc579. Final
tests/unit/test_tip064_integration.py SHA256 is
`0ffeee330c445e6c69b9124ca150c18e4cb30a94c8ce0dfb36b0ed98d399b883`.
The [Builder report](evidence/tip065/lost-ack-identity-v1/builder-completion-report.md)
and [manifest](evidence/tip065/lost-ack-identity-v1/frozen-source-manifest.json) bind
its before/final bytes and all 210 source entries. All 89 app files, other 209 source
entries and exact five-file overlay payload remain unchanged. Source payload SHA256
is `0efadd3d855b602e6bd8d58cd7033f092395026b633bceb28629e75fe4003182`.

Contractor reviewed the shared single-call handler at the original loop position.
Normal response identity is preserved. Unexpected WireError is bare re-raised with
its original identity/notes. Deliberate FIXTURE_LOST_ACK still requires exactly the
same close STOP_PENDING assertion. Controls prove one run_once/no close on normal
or unexpected failure, one close for the intentional fault, and failure on a wrong
close status. All original actual TLS cancellation, lost==[True], withheld QUEUED,
DRAINED and retained intent assertions stay required. The cancellation loop remains
three seconds, harmless hold five, cleanup two, HTTP and shared round 1000 ms;
all TLS/durability/SQLite/control/server budgets remain unchanged. No new request,
lookup, retry, cache, reset or product/authority change.

Builder's one-file run: **48 PASS / zero skips/errors/failures**. Independent
Contractor ran integration, existing TLS/security/COMMIT diagnostics, gateway
cleanup controls and frozen preflight: **156 PASS / 5 platform skips**, no errors
or failures. All 210 hashes were unchanged during each run and final source matches
the frozen Builder manifest exactly. Complete commands/environment, logs, JUnit and
hashes are in [Builder receipt](evidence/tip065/lost-ack-identity-v1/focused-v1-receipt.json)
and [Contractor receipt](evidence/tip065/lost-ack-identity-v1/contractor-receipt.json).
Counts overlap and do not replace the exact-head full-source and eight-workflow gate.

The [original d9adc579 receipt](evidence/tip065/ci-d9adc57/metadata/verification-receipt.json)
retains its 7/8 failure, all five original verified ZIPs, 210 manifests, JUnit/nine
harmless proofs and complete 43043-byte Deep log. Its actual /results response-read
timeouts sampled reserve_nonce COMMIT. Observed 766/906 ms are consistent with the
remaining absolute 1000-ms round cap; exact duration attribution and OS cause remain
UNKNOWN. The identity repair does not fix COMMIT latency or prove historical incidents
resolved. No workflow rerun occurred. A green new candidate would qualify only its
exact source and the separately reviewed legacy diagnostic slice.

Full Fleet migration, protected configuration/process/connector registration and
private VM/MT5/SDK acceptance remain OPEN/NOT_RUN. Eight successful workflows and
independent original ZIP/head/tree/manifests/JUnit/proofs precede the authorized
five-file read-only legacy overlay deployment. No main merge, credentials/AutoTrading
action, authority/UNKNOWN reset or generic PowerShell.
