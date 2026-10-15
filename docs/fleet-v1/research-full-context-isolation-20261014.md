# Independent full unit context research

This workflow is a new research attempt on separate GitHub-hosted Ubuntu and Windows ephemeral VMs. Its pull-request base is `feat/fleet-v1-continuous-source-20261003`; it does not target or modify main. Checkout and `FLEET_V1_EXPECTED_SHA` both bind the exact pull-request head. Freeze the reviewed candidate and durable input contract before creating the research pull request.

The earlier local full-context attempt remains UNKNOWN: owner 95688, direct process observations PID 8 and PID 12, last observed heartbeat 2026-10-14T09:18:37Z at 370.538 seconds. The known FIFO failure and passing TIP077 cases remain partial observations. Passing-case probe JSON was not retained there. The new VM attempt neither replaces that attempt nor proves its child or descendant closure. Do not launch additional recovery probes while its transport is unavailable. Once access is restored, read back the same attempt and its retained receipts before any further local execution. Do not relaunch or reset that attempt.

The workflow invokes the existing `tests/proofs/fleet_v1/run_source.py --unit-only` once per platform. Unit cap remains 900 seconds; job cap remains 25 minutes. Automatic retry is zero. Python remains 3.12; dependencies remain pytest 9.1.1, mcp 2.1.1 and cryptography 50.0.1 under the existing bootstrap lock. No application file, original test ID, assertion, order, skip, product clock, authorization TTL or wait is changed.

The opt-in `TIP077_AUTHORIZATION_SCOPE_PROBE=1` records successful original verification calls. JUnit uses `junit_logging=system-out` and `junit_log_passing_tests=True` so passing TIP077 records survive normal pytest capture. These output options do not change selection, capture mode or deadlines. No inherited `--basetemp` is supplied. Plugin autoload is disabled; the existing runner explicitly loads its progress observer.

Linux creates a fresh private directory under /tmp, verifies 0700 ownership, no symlink ancestors, and requires sticky semantics for writable ancestors. Its TMPDIR/TMP/TEMP are set through GITHUB_ENV. Windows retains the hosted runner defaults and original ACL checks. Setup receipts are preserved even if preflight or dependency installation fails.

The artifact always retains isolation receipts plus the runner's exact source-before/source-after manifests, summary, direct-child receipt, semantic checkpoints, raw unit log and JUnit if produced. A missing terminal summary or artifact remains UNKNOWN rather than PASS. Direct-child EXITED does not imply descendant closure.

There is no live VPS, MT5 terminal, SDK installation, account, credential, live journal or external trading mutation in this workflow. APP89 must remain hash-identical to the frozen candidate. Source manifest count includes the new workflow; verification must bind its actual Git bytes.

For attribution, entry 3 plus worker-binding match alone is insufficient. Distinct queued-third proof requires successful reserve/start rows for entry 3 with `cohort_binding=OUTSIDE`, worker binding true, and zero dropped rows/observation errors. Entry 3 with FIRST or SECOND is re-entry and must not be filtered. UNKNOWN bindings or no third reproduction do not authorize a scope filter. Original exact-four assertion remains unchanged.

A PASS here is source-unit research evidence. It is not the eight-workflow release gate, Fleet activation, Windows physical qualification, MT5 acceptance or permission to merge/deploy. Retain failures and all prior UNKNOWN attempts.
