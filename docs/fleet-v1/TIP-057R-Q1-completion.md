# TIP-057R-Q1 Builder Completion Report

**Status: PARTIAL — first isolated proof candidate implemented; actual Windows execution pending.** This report accompanies the first Draft candidate, not a production implementation or no-start certification. Broker/SDK paths and actual MetaTrader5 compatibility remain OPEN even if every harmless fixture test later passes. Builder code/workflow are frozen for the first exact-head Windows CI run; refinements will follow concrete failed receipts rather than replacing them.

Authorization: owner approval at 2026-10-02T13:59:50+07:00, “Duyệt run plan auto tiến hành đúng vai trò theo methodology @vibecode kit v6”. Output contract: [TIP-057R-Q1](TIP-057R-Q1.md), with [read contract](TIP-057R-contract.md) and [boundary proposal](TIP-057R-boundary-proposal.md). Real base main `70e2112da9fe8eaa6262f2ba896b55bf3e078260`, tree `6b32f1bc2d13627eba9e915f6fa3c0011b3539e5`; supplied 184-blob base was verified before this work. Local synthetic snapshot `2c46924e16fe4227fa5e83628888892475f53741` is not a remote parent or candidate CI head. No applicable `AGENTS.md` was found.

## YAGNI-3 and mechanism assessment

1. Required: the approved no-start/recovery guarantees need a falsifiable boundary experiment before product IPC can be built. A running-process precheck plus a helper does not prevent a library starting a replacement process.
2. Reuse: dedicated Windows CI, standard Windows APIs, stdlib Python/ctypes/unittest, and the existing shared native file lease in temporary fixture roots. No SDK dependency, production sandbox package or new scheduler is required.
3. Smallest sufficient experiment: one harmless standalone C fixture, a focused AppContainer launcher, a fixture authority prototype and one runner/workflow. The C fixture avoids packaging a Python runtime inside the sandbox. It emits synthetic process/phase data and never connects to a terminal or account.

Microsoft documents that child-process restriction is effective in a sandbox excluding privileged process handles, and explicitly warns about `PROCESS_CREATE_PROCESS`/`PROCESS_VM_WRITE` bypasses. The selected candidate uses an AppContainer with zero capabilities plus `PROCESS_CREATION_CHILD_PROCESS_RESTRICTED` as creation-time attributes, `bInheritHandles=False`, and an initially suspended worker. Profile/SID and file grants are unique to a temporary fixture root. It is a bounded experimental mechanism, not an administrator helper with a flag and not a JobObject process-count argument.

The parent commits fixture intent before process creation, commits a CREATE_ATTEMPT phase immediately before `CreateProcessW`, then commits PID/creation timestamp/image from the returned exact handle before `ResumeThread`. Windows setup failure before the create callback remains distinguishable from an unknown create outcome. The latter is retained as recovery-required even if no worker reference was persisted.

## Files created by Builder

| File | Purpose |
|---|---|
| `.github/workflows/verify-tip057rq.yml` | Dedicated Windows job, contents-read permission, Python 3.12, exact PR-head checkout, required Windows execution and bounded retained artifacts. |
| `tests/proofs/tip057rq/fixture_worker.c` | Harmless direct/breakaway child-launch controls, token/mitigation and separate privileged-right probes, hang and observable initialize/observation/cleanup fault callbacks. |
| `tests/proofs/tip057rq/windows_boundary.py` | Unique AppContainer/profile/root ACL lifecycle, creation attributes, no inherited handles, suspended creation and exact process-handle identity/termination. |
| `tests/proofs/tip057rq/authority.py` | Fixture-only common acquisition gate, ACTIVE/CLOSED generation record, durable intent, expected-authority reconciliation and shared native-lease reuse. |
| `tests/proofs/tip057rq/run_proof.py` | Eight portable cases, eight real Windows cases including per-mode fault subtests, compiler invocation and JSON/log evidence. |
| `docs/fleet-v1/TIP-057R-Q1-completion.md` | This report. |

No production blob, dependency/packaging file, existing unit test or existing workflow was changed by Builder. No proof module is imported by the runtime. Contractor-owned planning documents were left to Contractor. No GitHub mutation or VPS/native/chart/account/credential/AutoTrading/PowerShell/deployment operation was performed.

## Fixture ownership and failure semantics

Every fixture acquisition checks durable disposition while holding the fixture coordination file lock before acquiring the existing global native lease. An ACTIVE generation with missing intent is `LOST_ACTIVE_INTENT`; malformed/partial records fail closed. A dead parent PID, absent failure marker, unknown create result, live exact worker, wrong creation identity, stale generation or unresolved descendant disposition cannot authorize clear. The ACTIVE record is committed before intent, so a crash between those writes is a blocked unknown state. Successful close writes CLOSED after exact native release and then removes intent; incomplete close retains a blocker.

Reconciliation compares generation, native lease token, parent and worker identity, requires the exact worker handle to be signaled, verifies the fixture descendant disposition, and clears under the same fixture coordination guard. It refuses a successor native token. A restarted parent uses a fresh gate; two independent Python callers test that common fixture acquisition remains blocked. A separate main-thread-checked thread race tests stale reconciliation against the successor generation. This does not exercise unchanged production A/B/C or legacy acquisition paths.

Only a pre-create setup/validation failure can release with `cleanup=NOT_ATTEMPTED`. Initialize false/real injected SEH exception and observation exception execute observable fixture cleanup callbacks. Cleanup has a separate attempted marker, completed result and exception count; unproven cleanup wins while retaining the earlier primary code. Unqualified outcomes return no account values. These are harmless fixture callbacks, not SDK shutdown receipts.

For launch-capable fixture modes, descendant disposition begins UNRESOLVED. C records whether each API actually created a child and whether its exact handle was subsequently signaled. Missing/uncertain outcomes retain uncertainty. A marker alone is not a denial proof: restricted tests require API creation failure and a nonzero error, while an unrestricted direct-launch control must create, exit and write its marker. Breakaway causality is qualified only if its matching unrestricted control works; an ambient CI JobObject denial leaves that path OPEN. All old phase-marker files are cleared after acquiring exact fresh authority, and started PID is matched to the active worker reference.

## Acceptance map at first Draft

All actual Windows rows below are **PENDING**, not PASS from source inspection or Linux models.

| AC | Named cases / observable evidence | First Draft result |
|---|---|---|
| Q01 | `test_q01_restriction_active_before_work_and_setup_failure_no_attempt`: real invalid-attribute setup failure, no worker marker; suspended worker starts only after durable binding, reports AppContainer and child restriction before work. | Windows PENDING |
| Q02 | `test_q02_q03_unrestricted_control_and_restricted_stopped_launch`; `test_q02_exit_between_discovery_and_launch`: real API outcomes and markers, including exact target exit before gated replacement attempt. | Windows PENDING |
| Q03 | Separate `PROCESS_CREATE_PROCESS` and `PROCESS_VM_WRITE` parent probes; real inheritable privileged-handle control and restricted no-inheritance check; direct/breakaway API results. | Windows PENDING for fixture paths; broker/SDK/uncontained launch OPEN. Breakaway may remain OPEN if its control is denied by host policy. |
| Q04 | `test_q04_primary_and_real_fixture_cleanup_faults`: initialize false/raise, observe raise, shutdown raise and combined primary/cleanup fault with separate markers/results. | Windows PENDING; portable precedence PASS |
| Q05 | `test_q05_hang_does_not_release_before_exact_termination`: 250 ms fixture observation budget, retained native ownership until exact termination/wait, measured total and termination time. | Windows PENDING; no hard 10-second claim |
| Q06 | `test_q06_real_parent_crash_before_failure_marker`; portable create-attempt/unbound and lost-active-intent cases. Real parent exits 73 while worker remains, failure marker absent; fresh acquisition remains blocked. | Portable PASS; real crash PENDING |
| Q07 | `test_q07_real_creation_identity_stale_generation_and_descendants`; portable live-worker/identity/stale/descendant cases. Reused-PID condition is simulated by altering the real creation timestamp, not forced PID recycling. | Portable PASS; real identity/termination PENDING |
| Q08 | `test_q08_conflicting_callers_restart_and_recovery_race`: two independent process callers blocked, exact old worker terminated, stale thread clear and new contender checked in main thread, successor token/generation retained. | Portable successor-CAS PASS; Windows process/race PENDING |
| Q09 | Q01 real setup failure plus `test_no_attempt_release`; outcome precedence model. | Portable PASS; real setup failure PENDING |
| Q10 | `--require-windows` refuses non-Windows without skips; dedicated job checks actual git HEAD against reviewed head, records OS/Python/source hashes/exact worker identities/API outcomes/timings. | Local rejection PASS; actual Windows CI PENDING |
| Q11 | `git diff --exit-code` for app, packaging, existing tests and all four existing workflows; only isolated proof/new workflow allowed. | Local PASS; Contractor exact remote-delta review pending |

## Local verification and retained evidence

Runtime: Linux, Python **3.12.14**. The originally supplied audit venv was absent after environment refresh; available system Python 3.12.14 was sufficient because this proof uses stdlib and existing source only. No dependency was installed.

- `python tests/proofs/tip057rq/run_proof.py --portable --output /workspace/scratch/250985b4823e/audit/tip057rq-portable-v1`: **8 tests, 0 failures, 0 errors, 0 skips**, suite 0.018 s; status `PORTABLE_PASS_WINDOWS_UNQUALIFIED`. Summary elapsed 21.9927 ms includes runner work.
- `python -m py_compile` for the three proof Python files: PASS.
- `git diff --check`: PASS.
- `git diff --exit-code -- app pyproject.toml requirements-bootstrap.lock tests/unit` plus each of the four existing workflow paths: PASS, byte-identical to the supplied base.
- Required-Windows negative gate on Linux: **exit 1**, `BLOCKED`, `REAL_WINDOWS_REQUIRED_NO_SKIP`; no skipped gate or Windows PASS was manufactured.

Retained local paths (scratch evidence, not CI receipts):

```text
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v1/summary.json
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v1/proof.log
/workspace/scratch/250985b4823e/audit/tip057rq-require-windows-local/summary.json
```

The Windows runner writes `summary.json` capped at 256 KiB, bounded compiler/proof logs, and no compiled fixture binary in the uploaded artifact. The job uses a 15-minute overall ceiling; OS/API failure, missing compiler, profile/ACL failure, required test skip, wrong head or oversized evidence fails the job. The proof's measured 250 ms hang scenario is a shortened fixture budget; it neither certifies the proposed 10,000 ms production soft budget nor a hard caller deadline.

## Primary mechanism references

- [UpdateProcThreadAttribute](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute): creation-time AppContainer/security capabilities, child restriction and privileged-handle caveat.
- [AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation): restricted resource/process access; does not certify a trading-library broker path.
- [CreateAppContainerProfile](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile) and [SECURITY_CAPABILITIES](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-security_capabilities): unique profile/SID and zero capability list.
- [CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw): creation attributes, handle inheritance and returned process/thread handles.
- [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes): process creation FILETIME, paired here with executable and exact handle.
- [SetNamedSecurityInfoW](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow) and [Mandatory Integrity Control](https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control): fixture-root-only access grant and low label needed for low-integrity marker writes.

Primary documents were read on 2026-10-02. API declarations and behavior are still hypotheses awaiting the first actual Windows run, not source-only qualification.

## Remaining gates and suggestions

Q03 broker/SDK launch and Q2 physical MT5 IPC remain OPEN. This fixture cannot certify all production entry paths, actual terminal compatibility, an IPC cancellation guarantee, filesystem tamper resistance or power-loss durability. The intent/ledger protocol is a fixture prototype; production common-acquisition integration/rollback is a separate reviewed architecture and scope. A missing exact process identity or an unresolved descendant outcome is retained rather than inferred from PID absence/TTL.

The useful next action is the dedicated exact-head Windows job on the Draft PR, retaining its first failure and each later refinement receipt. Contractor should also verify all four unchanged baseline workflows and the remote delta. No merge, rollout, physical pilot or product helper is authorized by a fixture PASS. Any failure to establish prevention leaves targeted IPC disabled under the existing policy.
