# External diagnostic revision R02/R03 — 20261014

New research input, NOT a rerun/reconstruction of UNKNOWN original TIP088-44. Canonical source bdeec841/tree4873 remains untouched. Opt-in `--tip088-diag-output` enables temporary test-call observers; omitted option has no application import, patch or sideband file write. All timers, TTL, clock functions, durable calls, SQL/HTTP reads and original predicates remain original. Observer can affect scheduling and diagnostic timing; this proof alone does not qualify product release.

## Files and import layout

Publish observer.py and controls.py under `docs/fleet-v1/research/release-resume-20261014/`. Set PYTHONPATH to that directory, app, and tests/unit. Existing runner can dispatch commands; no mutable R01 imports required. `controls.py` is explicitly passed to pytest, so does not add cases to canonical tests/unit or original1611 IDs.

## Commands (after Root durable freeze ONLY)

Controls once;static estimate10 cases from9 functions (one parameterized2); collection NOT_RUN:

`python -m pytest -p observer docs/fleet-v1/research/release-resume-20261014/controls.py -q --tb=short --junitxml=<unique-output>/controls.junit.xml`

Selected original4 once; exact IDs and order:

`python -m pytest -p observer -p fleet_source_progress 'tests/unit/test_tip064_capacity_https.py::test_capacity_positive_profile_delayed_durable_registration_has_no_retry[5000]' 'tests/unit/test_tip077_capacity_entry_watchdog.py::test_original_three_second_capacity_entry_observation_remains_bounded_negative' 'tests/unit/test_tip063_worktrees.py::test_exact_crash_reopen_recovers_without_duplicate_git_effect[commit:after_effect]' 'tests/unit/test_tip064_integration.py::test_actual_tls_blocked_native_keeps_heartbeat_status_cancel_and_lost_ack_durable' --tip088-diag-output=<unique-output>/observations.jsonl --basetemp=<unique-output>/tmp -v --tb=short --junitxml=<unique-output>/selected.junit.xml -o faulthandler_timeout=60`

Each dispatch requires outer cap<=300 seconds; controls cap60 and selected cap240 recommended, max300 combined per platform. Original4 expected from historical Windows timings significantly below240 seconds but this is not a guarantee; selected diagnostic failure/timeout remains failure/UNKNOWN, never a manufactured reproduction or proof of fix. Do not run controls alongside selected original timings. This selection is10 estimated external control cases+4 original cases, not original44. The original cases already include positive profile, negative original3, controlled crash/reopen and cancellation/lostACK assertions; no additional slow fixture schedules introduced.

Each output root must be new and nonexistent, isolated by PID/attempt identity. Set output permissions privately and dispatch no live MT5/Tunnel requests. Original fixtures choose temporary directories and dynamic loopback TLS. Root runner owns receipt/start/hash/PID/cap/heartbeat/terminal/childclosed and preflight APP89 hash guards.

## Evidence produced

Finite ring192 events percase, first16 errors, stage/outcome counters; no payload, IDs, secrets, exception text/notes or arbitrary code strings. Error code only finite whitelist; unknown becomes OTHER. Grant issue/expiry times come from existing method inputs/returns, gateway current time only from original `now_ms` argument. Native callback phases, handled journal outcomes, dispatcher closed/pending counters and worker alive counts are observed without SQL/HTTP requery. Predicate wrapper invokes original once. No extra clock reads from product clock functions; observer uses its own monotonic elapsed only.

Buffered evidence is appended after casecall and immediately emitted via pytest reporter. If write fails, test outcome remains unchanged but observation file is missing and diagnostics are NOT_ATTESTABLE. Wrapper restores with ExitStack after casecall. No cleanup intervention, worker join, authority renewal or timeout modification.

Next proof: Root independent qualification of privacy/default-noeffect/exceptionidentity/once-predicate/cap/diagnosticfailure contracts, then selected4 Linux and Windows, evidence interpretation restricted to those NEW attempts. Observe exact original code/stages before any product or fixture repair proposal.

Timestamp coverage: native grant input to verifier and NodeClient authorization return are plain existing body dictionaries; gateway authorize_node now_ms is an already-read argument. No node verifier clock is wrapped/read. WRITER_RECHECK's sealed fence contains no plain dictionary projection, so this stage emits timing/count/error only; exact node grant age at require/recheck remains NOT_OBSERVED unless original caller returns timestamps. Do not infer expiry from total case elapsed. Exact gateway error code is whitelisted; an unknown code becomes OTHER, not exact-code evidence.

Only the four exact selected nodeids activate observers, correlated using fixed case_ordinal1–4 and fixed case_id labels, never raw input parameters. Binding infrastructure failure explicitly returns TIP088_DIAGNOSTIC_BINDING_BLOCKED before original selected casecall; it is diagnostic qualification blockage, not reproduction of original CI failure.

## Fixed runner and Windows workflow

Mapped runner path derives repository ROOT via __file__.parents[4]. It reuses R01 run_case/checkpoint/source_manifest from exact checkout tests/proofs/fleet_v1/run_source.py, keeps full-unit900 untouched and adds no generic command CLI. Fixed controls cap60 (10 static-estimated cases) followed by original4cap240 only after controls terminalPASS/directchildEXITED; sum dispatchcap300 plus bounded directchildcleanup5 per subprocess. JUnit exact10+4 after collection verifies the static estimate, finite four case-correlated observations and source/research byte guards are required for diagnosticPASS. Descendant closure explicitly UNKNOWN, not certified by directchildEXITED.

Command: `python docs/fleet-v1/research/release-resume-20261014/run_diagnostic.py --output <new-nonexistent-output>`; Windows adds `--require-windows`. FLEET_V1_EXPECTED_SHA is required; optional FLEET_V1_EXPECTED_TREE is checked. Output reuse is refused even when empty. No tests are launched by merely importing the runner.

Proposed workflow maps to .github/workflows/verify-release-resume-diagnostic.yml; pull_request only targets feat/fleet-v1-continuous-source-20261003, exact PRhead checkout, Windows/Python3.12, unchanged locked dependencies,15min job and uploadalways. Original8 main-target workflows do not dispatch from this research PR. This diagnostic workflow cannot qualify release or repair missing original44.
