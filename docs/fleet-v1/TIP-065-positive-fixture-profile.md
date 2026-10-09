# TIP-065 — Positive fixture policy and complete failure preservation

Contractor decision, 2026-10-06, under continuous source authorization. Parent
`99ac11991b8858990bf8f5d7ed8f9bcd785b7858`, tree
`34c788a21dcb5f48102987b58828d6085e583b7a`, is rejected at 5/8, attempt 1.
Its original logs, five official ZIPs, matching 211-entry manifests, complete
JUnit including the Windows failure and nine harmless proofs are preserved in
[the failed receipt](evidence/tip065/ci-99ac119/metadata/verification-receipt.json).

## YAGNI-3 and causal evidence

1. Necessary: actual Windows CI identifies positive registration timeout while
   reading the complete current source manifest; three valid control rounds take
   2766 ms rather than the fixture's arbitrary 1500 ms; phase/result response
   timeouts sample durable COMMIT. A new negative control masks an unexpected
   transport failure with its exception-identity assertion. Scratch controls
   additionally demonstrate a worker failure arriving during cleanup after the
   current helper has already collected errors.
2. Reuse: existing positive writer fixture already selects a 5000-ms HTTP policy;
   reuse explicit policy replacement, actual TLS fixtures, immutable signed TTLs,
   original worker barriers, owner drain and original exception objects. Four
   independent profile controls show a delayed durable registration times out
   under 1000 ms but completes under 5000 ms, exactly one install per fresh
   instance with no retry. Expired 1000-ms proofs and nonce/session/owner denials
   remain enforced under the positive profile. Two separate controls demonstrate
   late-worker loss and valid held-worker progress beyond 1500 ms.
3. Smallest scope: only `tests/unit/test_tip064_integration.py` and
   `tests/unit/test_tip064_capacity_https.py`. No production or dependency edits.

These controls establish fixture defects and profile coupling. They do not prove
the root cause of historical storage/COMMIT scheduling latency, or a production
performance improvement. The original 8019a52 and 30bcc584 incident causes remain
UNKNOWN. Preserve the scratch assertion-selection failure and its corrected
single-control result as distinct evidence.

## Explicit replacement of prior fixture assumptions

Prior contracts froze fixture budgets while investigating particular defects.
This contract supersedes only the following positive fixture assumptions, on
the controlled evidence above. The approved Blueprint specifies owner-selected
measured physical resource/latency thresholds, not a universal 1500-ms gate.

* Only the long-phase fixture family selects HTTP 5000 ms and control-round
  5000 ms explicitly, while retaining signed authorization TTL 1000 ms and
  original test names/parameter IDs. Other composed fixtures keep their default
  profile. The constructed outbound owner uses the selected HTTP policy.
* The positive capacity fixture selects HTTP/control-round 5000 ms, preserving
  signed TTL 2000 ms. Replace its three-step 1500-ms speed assertion with a
  finite aggregate observation bound of six configured request budgets (30 s),
  and direct assertions after every step that the two actual workers remain
  pending and unreleased. Keep original ARMED scopes, third job QUEUED, first two
  STARTING, exact callback count, final successful results and no install marker.
* Retain the stricter independent 20-second harmless worker hold. The 30-second
  aggregate cap does not promise acceptance of every worst-case request schedule.
  It is a source harness bound, not a production latency qualification.

Keep the 1.2-second producer, three-second return barrier, three-second long
cleanup, ten-second capacity cleanup, all SQLite limits, FULL/WAL, observed-wall
and nonce commits, real proof expiry/replay checks and product policy unchanged.
The transport suite's original 1000-ms and explicit negative deadlines remain.
Do not cache source/authority, skip either source verification pass, clear
UNKNOWN, retry requests, discard unexpected errors or reset evidence.

## Failure and verification criteria

Build the identity-deduplicated union of original observation, worker and cleanup
exceptions after bounded cleanup completes. Reraise a sole original object;
group distinct errors without masking notes. Expected-negative controls must
propagate unexpected errors intact. Exercise primary-before-late-worker and
late-worker-plus-cleanup ordering through the actual shared helper.

Add/reuse meaningful controls for the two independent delayed registration
profiles and exactly one durable operation each, expiry and replay denial under
the positive policy, and three control steps returning with native workers held
despite scheduling beyond the old aggregate assumption. Preserve all original
positive assertions; record the new per-request control against its actual
configured policy, without claiming the old 1000-ms performance target passed.

Builder provides exact diff, command/environment/log/JUnit, before/after manifests
and completion report. Contractor independently reviews and verifies frozen
bytes. One reviewed candidate then requires its own 8/8 workflows, ZIP digests,
Git head/tree/manifests, complete JUnit and proofs before the unchanged five-file
legacy observation overlay can deploy. Full Fleet activation, measured physical
performance and private VM/MT5/SDK qualification remain OPEN/NOT_RUN.
