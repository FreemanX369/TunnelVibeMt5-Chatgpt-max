# Whole-context observation on measured runner temp volume

Input parent d73833cffe72d2d3d3eae2d88613a30181d347b3,
tree27b1f990e83e839321459a26a7ea30a4e48910c6. Parent Linux full is PASS;
Windows full is FAIL1623PASS/2FAIL/12SKIP,1637cases674.329s/no timeout.
Keep all those artifacts. APP89, original tests and product budgets stay frozen.

## Evidence for an environment comparison

Separate PR68 at77f3b531e68427729563fddbdd6431b669b4fbd8 ran one declared
C1/D/C2 crossover on a fresh Windows VM. Run38701330816 attempt1 completed;
artifact11955928891/45333bytes/SHA256
1fc6b2640fa45364c8a2984fc8cd409e306b8378f3fb0faf619c6acccdf5c904.
All12 original case executions passed, source235/research inputs unchanged.

| Arm | SQLite DELETE/FULL median commit ms,8samples | Four-case elapsed s |
| --- | --- | --- |
| C1 |17.7895 |19.296 |
| D |1.113 |11.625 |
| C2 |22.653 |18.547 |

Observed st_dev values differ across C and D. These are filesystem volumes,
not proof of distinct physical disks. This small probe measures a path-dependent
latency difference; it does not prove the cause of the historical TLS/pump
failures. Those failures were NOT_REPRODUCED in the selected crossover.
The first crossover revision a0e861a remains HARNESS_ERROR with all original
cases NOT_DISPATCHED; its tagged-record parser correction has framing evidence.

## Scope and acceptance

YAGNI: the measured environment factor deserves one whole-context test before
any further fixture or product contract change. Reuse the existing full-context
workflow and focused14 runner; change only Windows child temp placement.

- Create a fresh temp directory under RUNNER_TEMP, require a different observed
  st_dev from the original default temp, and reject root/task reparse points.
- Record both drives/volume observations and inherited-ACL policy in the setup
  receipt. Set TMP/TEMP/TMPDIR through GITHUB_ENV before child dispatch.
- Do not change Windows ACLs, add antivirus/security exclusions, override
  basetemp or relax original file/owner/ACL guards. All original Windows guard
  cases must run as part of full suite; no deployment trust is inferred.
- Keep focused14/cap120 then full1637/cap900, job25, retries0. Source234/APP89;
  test IDs/order/assertions/skips, HTTP1/5, TTL1000/max2000, finite pump/worker
  budgets, durable operations, dependencies and Linux temp policy unchanged.
- Preserve previous outcomes and all new failures/receipts/source-before-after
  JUnits. Direct-child EXITED is not descendant closure. No physical MT5/SDK.

Freeze/save both changed files and expected manifest before expected-parent CAS
to the research branch. This is an environment-factor revision, not a rerun of
old attempts. Both platform jobs use exact new head; the unchanged Linux source
inventory remains independently attributable to that head. This does not start
the eight source-release workflows or promote PR65/main/runtime.

Even a passing full D run does not identify why C produced historical long
intervals. Source acceptance still requires independent review and all original
eight exact-head workflows/artifacts, including the final recorded environment.
