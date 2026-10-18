# Final source CI environment and bounded Deep unit evidence

Parent757f63d6708fcf396ab0753703ec926fe4b77cd8,
tree4935844f7a17b0dd6de7f28875593af61bc02da2. Exact-head research full run
38702169608 attempt1 is verified: Linux1619PASS/18SKIP,227.754s;
Windows1625PASS/12SKIP,284.922s;0FAIL/ERROR,1637cases each. Focused14 passed
on both platforms; source234/APP89 unchanged and original1611 IDs/order and
skip sets preserved. Windows temp was a fresh directory on observed volume D,
with original inherited ACLs and every original Windows guard test unchanged.
This is source research evidence, not independent review or source acceptance.

## Why this revision exists

The final Integrated, Bootstrap and Deep workflows each run the complete unit
suite. They must use the recorded Windows temp environment rather than leave
the accepted environment change only in the research workflow. Deep still ran
pytest directly without dedicated900 child bound, exact-head runner receipts
or retained JUnit; that leaves an evidence/stall gap despite older PASS status.

Reuse the existing source runner, exact-head checkout and small Python temp
preflight. No application/test/runner/dependency changes or new service/helper.
The three temp preflight blocks are identical, so their constraints can be
compared directly during review. A Windows preflight records distinct original
and runner-temp volumes, rejects root/task reparse points, preserves inherited
ACLs, and writes GITHUB_ENV before source-test dispatch. A failure blocks tests;
always-steps retain its receipt inside the existing artifact directory.

Deep now uses the same unit-only runner cap900/job25 and exact head pin already
used by Bootstrap. Original compile/install/config/dry-run/boundary steps remain.
Existing dependency commands, product clocks/TTLs, durability and original
assertions/skips/order are unchanged. No ACL/security exclusions or basetemp
override. Passing JUnit output and opt-in authorization observations use the
already-qualified noninterference controls. Process interrupts still propagate.

## Acceptance and artifact inventory

- Source234/APP89, full1637=1611original+26controls; no new unit cases.
- All three original Windows full-suite entry points have temp preflight,
  source_before/after, direct-child identity/exit, cap900 and retained JUnit.
- Integrated retains its unchanged portable/Windows harmless proofs and120
  proof cap. Bootstrap downstream config/dry-run/manifest/boundary must PASS.
- There are now seven expected ZIPs: the original five proof/source artifacts,
  plus Bootstrap unit evidence and Deep unit evidence. The original nine
  harmless proof inventories are unchanged. Four complete unit JUnits are
  expected: Integrated Linux/Windows, Bootstrap Windows and Deep Windows.
- Original artifact paths are preserved; temp-setup.json is copied into each
  existing source artifact directory only after runner completion/failure, so
  its output-reuse guard remains intact. No fixture temp/private keys uploaded.
- Independent review, exact-head eight CI and official artifact attestation
  remain required before SOURCE_ACCEPTED. This revision does not publish to
  PR65/main, deploy a runtime, or qualify any physical Fleet/SDK/MT5 operation.

Retain d738 and9c7 Windows failures, a0 harness error, original44/e7 UNKNOWN and
descendantUNKNOWN records. C/D latency measurements do not establish an internal
cause of every historical timing failure. Passing source CI is scoped to its
recorded environment, never a claim of production topology or capacity.
