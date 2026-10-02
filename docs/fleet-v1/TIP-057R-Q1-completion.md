# TIP-057R-Q1 Builder Completion Report

**Status: PARTIAL — six unsuccessful Windows receipts retained; receipt 6 passed its required checkpoint and 15/16 tests. The next narrow borrowed-handle probe refinement is frozen.** This report accompanies the Draft proof, not a production implementation or no-start certification. Broker/SDK paths and actual MetaTrader5 compatibility remain OPEN even if every harmless fixture test later passes. The next exact-head Windows run must preserve the positive controls and pass the full qualification suite. Earlier frozen payloads and pending statements below record their state at the time; receipt 6 and the current payload appear at the end.

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

Primary documents were read on 2026-10-02. Actual Windows receipts below distinguish observed behavior from the mechanisms still awaiting successful qualification; source inspection does not qualify a gate.

## Remaining gates and suggestions

Q03 broker/SDK launch and Q2 physical MT5 IPC remain OPEN. This fixture cannot certify all production entry paths, actual terminal compatibility, an IPC cancellation guarantee, filesystem tamper resistance or power-loss durability. The intent/ledger protocol is a fixture prototype; production common-acquisition integration/rollback is a separate reviewed architecture and scope. A missing exact process identity or an unresolved descendant outcome is retained rather than inferred from PID absence/TTL.

The useful next action is the dedicated exact-head Windows job on the Draft PR, retaining its first failure and each later refinement receipt. Contractor should also verify all four unchanged baseline workflows and the remote delta. No merge, rollout, physical pilot or product helper is authorized by a fixture PASS. Any failure to establish prevention leaves targeted IPC disabled under the existing policy.

## Actual Windows receipt 1 — retained BLOCKED result

Contractor supplied and independently retained the first exact-head receipt from Draft PR **#61**:

| Field | Receipt |
|---|---|
| Reviewed head | `a93e4b9b34830926e6fa3100d54c3c8852e3fe47` |
| Dedicated run / job | `36979951811` / `110751975744` |
| Platform | Windows Server 2025; Python 3.12.10 |
| Result | `BLOCKED`, `FIXTURE_COMPILATION_FAILED`; **zero tests executed** |
| Failure | Nested quoting caused the quoted `vcvars64.bat` path to be treated as an unrecognized command. No AppContainer/process/ownership case was reached. |
| Exact-head check | PASS; runtime source hashes additionally exposed normal LF-to-CRLF checkout conversion, independently reproduced by Contractor. |
| Artifact | `11214762919`; ZIP SHA-256 `f945ec121b872c99b5e6be76e225cea7c41c96f35b6c1681967bc7754e5f1713` |
| Retained raw receipts | [summary.json](evidence/tip057rq/first-a93e4b9/summary.json), [compiler.log](evidence/tip057rq/first-a93e4b9/compiler.log) |

All four unchanged baseline workflows succeeded for that first candidate: TIP-027 run `36979951816`, TIP-028 run `36979952026`, TIP-034 bootstrap run `36979951789`, TIP-053 run `36979951792`. These baseline successes do not qualify Q1 prevention. The dedicated first run qualifies no actual Windows AC and is not erased by a later green result.

## Bounded receipt-driven refinement 1

Only the dedicated runner and new workflow changed after receipt 1:

- Compiler invocation now writes a runner-owned batch file containing the quoted `vcvars64.bat` call and compiler arguments. Its raw Windows command line preserves cmd's outer quote pair and avoids the nested `list2cmdline` transformation that failed.
- The dedicated checkout uses Git's per-command `GIT_CONFIG_COUNT` environment with `core.autocrlf=false`, without writing global Git settings. In CI, every proof source's raw working bytes must also hash exactly like its actual `HEAD` blob, or the job fails `CHECKOUT_SOURCE_BYTES_MISMATCH`. [Git's primary configuration reference](https://git-scm.com/docs/git-config#Documentation/git-config.txt-GITCONFIGCOUNT) documents these per-process overrides.
- `proof.log` now has an enforced 64,000-byte artifact cap, with original byte count/SHA-256 and truncation metadata retained in `summary.json`. A portable 171,000-byte multibyte log check retained 63,992 valid UTF-8 bytes and preserved the original hash; this is file-format validation, not Windows qualification.
- Q06 known-worker/profile cleanup covers the whole subprocess/assertion/read/open failure path. The crash helper writes the owned profile receipt before arming and cleans known resources on ordinary setup failure. `tearDown` attempts all known exact resources and then fails visibly with aggregated bounded cleanup codes. Unknown creation identities are retained as uncertainty; no guessed PID, broad process kill or unowned profile removal was added.

Refinement local checks: **8 portable tests, 0 failures/errors/skips**, suite 0.011 s, elapsed 15.1289 ms; three Python proof files compile; whitespace and unchanged production/existing-workflow checks PASS. Evidence: `/workspace/scratch/250985b4823e/audit/tip057rq-portable-v2/summary.json` and `proof.log`. The first portable and first Windows receipts remain separate.

| Frozen refinement payload | Bytes | SHA-256 |
|---|---:|---|
| `.github/workflows/verify-tip057rq.yml` | 1,266 | `cc9efd3faee7b3646bdc29c76c067ba85df6a6b9274db5f9af61d442936467ed` |
| `tests/proofs/tip057rq/authority.py` | 8,423 | `604aeae2fb3da5e9985c3ea28f2f92e1c69d765a5ddda7df15ee43ac251299ff` |
| `tests/proofs/tip057rq/fixture_worker.c` | 6,786 | `9c2259dcc5b75c64e3e59d531e5752b0a674908f59772c58c0bc7cfdb64b95d5` |
| `tests/proofs/tip057rq/run_proof.py` | 33,920 | `97e6c311f0b9625e64b70cc166b8e6d6af1227fece78de41fc13aa56bbff2244` |
| `tests/proofs/tip057rq/windows_boundary.py` | 12,397 | `d35fc9024e30570a732125f028023e50ac734a0446bbd7e4e14dba89b0a6f061` |

At that refinement's freeze, actual C compilation and the 16-case Windows/portable run were pending. Receipt 2 below records its actual failure. Expected Windows evidence still includes the five Q04 fault modes, unrestricted direct-launch control, exact process/termination records and explicit broker/SDK OPEN. No product architecture, dependency or existing workflow/test changed during refinement.

## Actual Windows receipt 2 — retained failed and cancelled result

| Field | Receipt |
|---|---|
| Reviewed head / tree | `783f9a9f7aa2bdbff62a56a1b170d0b5f363d586` / `1d9f1e46f6154001d267950352a446b1665c60bb` |
| Dedicated run / job | `36981015785` / `110755305263` |
| Platform | `Windows-2025Server-10.0.26100-SP0`; Python 3.12.10 |
| Job conclusion | Cancelled at the 15-minute ceiling, at 2026-10-02T08:09:13Z |
| Retained summary | `FAIL`; 16 tests, 3 failures, 7 errors, **0 skips**; elapsed 885,344 ms; unittest suite 873.286 s |
| Compilation | PASS; compiler output `fixture_worker.c`; executable SHA-256 `69aabdc623eba026433cc562162031c92ea65d5ee31515c900fda2accda17218` |
| Exact head / source blobs | PASS / PASS; the four working source hashes exactly match their checked-out HEAD blobs and the frozen refinement-1 manifest above |
| Artifact | `11215538983`; independently verified ZIP SHA-256 `c3806c321b0431df8fb92db2bb45cc8ef87b360ca625781b43c25ab3bc487e3e` |
| Retained raw receipts | [summary.json](evidence/tip057rq/second-783f9a9/summary.json), [proof.log](evidence/tip057rq/second-783f9a9/proof.log), [compiler.log](evidence/tip057rq/second-783f9a9/compiler.log) |
| Proof-log integrity | 18,238 bytes, untruncated, SHA-256 `ba123a3eaa040d0ca4d266f6449595ae28aacb1f33795fe317c1457ea1bde570` |

The second receipt proves that the first compiler/checkout failures were corrected. Actual restricted workers reported AppContainer=1, child restriction=1, policy query success, separate parent privileged-right denials with error 5, and no inherited parent handle. Actual shutdown-raise and combined initialize/shutdown-raise modes recorded one/two caught exceptions, unproven cleanup, null account values and preserved primary failure. These are observed partial records; they do not convert the failing full cases into PASS.

Seven errors share one lifecycle defect: after the exact worker exited, `QueryFullProcessImageNameW` returned WinError 31. This affected normal completion/reconciliation and post-termination confirmation in Q01, three Q04 submodes, Q05, Q07 and Q08. Q02's unrestricted control and race target lacked `started.json`; that candidate did not retain their exit codes, so the cause remains unqualified. Q06 timed out its pipe-captured intentional-crash helper, then `subprocess.run` entered its unbounded fallback `communicate()` after killing the helper. Its pipe-reader join remained blocked until CI cancellation; the receipt does not identify every remaining pipe holder. Subsequent cleanup retained an unknown creation state. No successful Q06 durable-crash/recovery claim is made from this receipt.

Contractor reports all four unchanged baseline workflows succeeded again. Baseline success does not qualify Q1. The raw failed/cancelled receipt is retained even if the next revision passes.

## Bounded receipt-driven refinement 2

Only the isolated C worker, launcher and runner changed. The fixture authority, dedicated workflow, all four existing workflows, production files and existing tests remain unchanged.

- An image is cached only after a successful actual image query while the same owned process handle is still live. Before and after termination, the runner checks PID and creation time from that retained handle, and confirms signaled exit without re-querying a dead executable image. Cache/handle or lifetime mismatch fails explicitly. A fresh already-dead process handle has no such cache and cannot qualify identity; it is rejected rather than populated from the expected durable record. Q07 checks this rejection, and Q05/normal completion record the post-exit identity basis.
- The unrestricted control uses ordinary `STARTUPINFO` sizing without the extended-attributes flag. Both unrestricted and restricted fixtures, and their matching child attempts, use `CREATE_NO_WINDOW` to remove unrelated console construction from fixture I/O. This is a narrow startup correction and diagnostic hypothesis, not an assertion that it solves the unobserved control failure. The C worker records an early `entry.json`; missing-output handling records the exact worker exit code/hex, PID/creation time and phase-marker presence, or a bounded live-worker timeout. Entry is also checked absent while suspended and cleared with all other per-attempt phase markers.
- Q06 and Q08 use file-backed stdout/stderr, a bounded controller wait, and a bounded stop/wait of the Popen-owned Windows process handle. They do not call `communicate()` or wait for pipe EOF. Only bounded diagnostic tails enter the JSON evidence. Q06 additionally records controller phases around setup/create/bind/resume/crash, checks that the durable parent PID matches the owned controller, and retains unknown worker creation as uncertainty. Best-effort exact worker/profile cleanup still runs after controller failures.
- The Q06 known-image guard compares the actual fixture file using `os.path.samefile`, covering Windows long-path/8.3 aliases. A freshly opened worker must still match its actual live queried image, PID and creation time to the durable expected identity. This does not broaden authority to arbitrary images or guessed PIDs.

The lifetime reasoning follows Microsoft's [process termination documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/terminating-a-process): termination signals the process object, while an externally retained handle keeps the object valid. [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes) supplies creation time from that handle. [Process creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags) distinguish suspended/no-console creation and extended startup information. These references support the mechanism; receipt 3 must verify this implementation on actual Windows.

**Recovery limit:** Q06 deliberately reopens a still-live orphan worker after its parent crashes, captures its actual live image on that new handle, then terminates and reconciles using the same handle. If a restarted parent first encounters an already-dead worker without its own previously captured live-image identity, recovery remains required. The cache is process-memory evidence tied to one retained handle; it is not a durable replacement for an unavailable image query. Late-dead restart recovery, broader production entry paths, SDK/broker prevention and production liveness remain OPEN. No new durable architecture was added to force those gates closed.

Local checks for this frozen refinement: **8 portable tests, 0 failures/errors/skips**, suite 0.010 s, summary elapsed 13.7230 ms; three proof Python files compile; whitespace and unchanged product/existing-workflow checks PASS. A separate local sensitivity check verifies cached same-handle post-exit behavior without a dead-image query, rejection of a fresh dead handle, rejection of a changed creation time, and a promptly stopped owned Linux controller after timeout. It uses a fake kernel/Linux process and is explicitly **not Windows qualification**.

Retained local evidence:

```text
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v3/summary.json
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v3/proof.log
/workspace/scratch/250985b4823e/audit/tip057rq-lifecycle-v3.json
/workspace/scratch/250985b4823e/audit/tip057rq-v3-frozen-manifest.json
```

| Frozen refinement-2 payload | Bytes | SHA-256 |
|---|---:|---|
| `.github/workflows/verify-tip057rq.yml` | 1,266 | `cc9efd3faee7b3646bdc29c76c067ba85df6a6b9274db5f9af61d442936467ed` |
| `tests/proofs/tip057rq/authority.py` | 8,423 | `604aeae2fb3da5e9985c3ea28f2f92e1c69d765a5ddda7df15ee43ac251299ff` |
| `tests/proofs/tip057rq/fixture_worker.c` | 6,964 | `1329f7edd038f800c32ead096acb2abc5026669cd093b0c79382c296cc598a14` |
| `tests/proofs/tip057rq/run_proof.py` | 39,662 | `05a447abbc55648885d9388fd154ff82db96c0437ae1fb02210417b0d1d57c27` |
| `tests/proofs/tip057rq/windows_boundary.py` | 13,810 | `e9bad995c98254636729d56c86146b319ee6b926053dc4c03f260d976af20f33` |

Code/workflow are explicitly frozen pending Contractor review/publication and the next real Windows receipt. Required gates are not skipped for green, FIFO timeouts are not lengthened, and no existing workflow/product integration changed.

Contractor published this frozen executable payload as PR #61 head `07316a4a66301eb471112528c2c0e31f781f2bc6`, tree `ce2f4455a3d75cfd14e5940de46688da54495ed8`, with 199 remote blobs verified. Independent portable/static checks again passed. The third real Windows receipt is pending; this report append was not included in that published head.

## Actual Windows receipt 3 — retained failed result

The pending third run above subsequently failed; its retained result is not replaced by the next diagnostic candidate.

| Field | Receipt |
|---|---|
| Reviewed head | `07316a4a66301eb471112528c2c0e31f781f2bc6` |
| Dedicated run / job | `36998399463` / `110810267413` |
| Platform | Windows Server 2025; Python 3.12.10 |
| Summary result | `FAIL`; 16 tests, 12 failures including Q04 submodes, 0 errors, **0 skips**; elapsed 12,391 ms |
| Compilation / exact head / source blobs | PASS / PASS / PASS |
| Compiled fixture | SHA-256 `3a38edd4d9fa7a6ec3b8abeda19c916abe852c5171eeb22316c9f02eaa593f97` |
| Artifact | `11221823821`; independently verified ZIP SHA-256 `a61cec71a148fcceeeb47e92e5021e37674bbd9c7dd3ef92cfc6487eb96e6796` |
| Retained raw receipts | [summary.json](evidence/tip057rq/third-07316a4/summary.json), [proof.log](evidence/tip057rq/third-07316a4/proof.log), [compiler.log](evidence/tip057rq/third-07316a4/compiler.log) |
| Proof-log integrity | 29,186 bytes, untruncated, SHA-256 `02891cf0fa55fac1f820aae4780642d1eba080b3f5c55ee0860772ad244bba77` |

All eight portable cases passed on Windows. The controller no longer hung: Q06 returned controller exit 1, with a bounded error tail and a durable `BOUND_BEFORE_RESUME` phase, instead of reaching intentional exit 73. This demonstrates bounded failure collection, not successful crash recovery.

The newly introduced no-console setting correlated with a regression: every restricted worker exited `0xc0000142` before `entry.json` or `started.json`. Both unrestricted controls instead reached C and returned **95**, which this C revision specifically assigned to entry-marker write failure. It did not record the underlying file API error, so neither exit 95 nor the missing marker proves child-launch denial or an ACL cause. The receipt therefore contains two distinct unresolved startup/writer causes. Q06's cleanup then attempted to reopen the already-dead worker, received WinError 87 and retained recovery uncertainty, consistent with the declared fresh-dead identity limit. No live-reopen crash proof or process-lifecycle AC is qualified by this failing run. Contractor reports all four baseline workflows succeeded again.

## Bounded receipt-driven refinement 3 — focused checkpoint

After three unsuccessful receipts, the next revision isolates startup and marker writing before running broad qualification. It preserves the cached live-image/same-handle lifetime checks and file-backed bounded controllers. No profile capability, ACL access grant, production policy or global setting is broadened. The existing Microsoft wide `%s` formatter remains unchanged; the receipts do not establish a formatting defect.

The default fixture startup returns to the earlier console mode that successfully entered restricted C workers in receipt 2. The no-console flag is an explicit matched diagnostic parameter only. Full worker/controller and C-child defaults consistently use console startup. Four independent temporary roots run the same bounded `write_probe` mode:

| Debug variant | Required outcome before full suite |
|---|---|
| Plain unrestricted console, without AppContainer root grants | Actual positive marker from the owned finite Popen controller, exact marker PID, completed file write and observable token/policy diagnostics. |
| Granted unrestricted console | Same positive writer outcome using a suspended exact process handle, no inherited handles and the existing fixture-root grants. |
| Granted restricted console | Same positive writer outcome with actual AppContainer=1 and child restriction=1; no inherited handles. |
| Granted restricted no-console | Bounded diagnostic observation only; a loader/startup failure cannot count as process-creation denial or prevention proof. Its owned-resource cleanup must still be proven. |

`write_probe` returns before initialize, observation, hang or child-launch branches. The plain finite writer is controlled by its Popen-owned handle and file-backed stdio; granted probes own exact suspended process/thread handles before resuming. All launch-capable/full Windows cases retain the unchanged arm → durable create attempt → exact worker binding → resume protocol. Every root/profile is unique and is cleaned through the bounded owned-resource paths.

Before and after each checkpoint launch, the parent records its actual user SID, mandatory integrity SID, AppContainer bit and elevation bit. It separately observes `CreateFileW`, `WriteFile` byte count and flush results for owned parent marker files. The runner reads back actual root and executable DACL/mandatory-label security descriptors. It requests only DACL plus LABEL (`READ_CONTROL`), formats the selected in-memory descriptor, and never enables a security privilege or queries a full SACL.

C writer diagnostics record the actual failing stage and immediately captured native error, requested/written byte counts, CRT `errno` separately from native errors, and a distinct short-write outcome. They also report bounded root/computed-path/current-directory strings, root attributes/error, actual worker AppContainer/integrity values and queried child restriction. A relative diagnostic file independently tests formatted-path versus working-root access. If that diagnostic cannot be created, the standalone control has bounded file-backed stderr; restricted probes continue to inherit no handles. The process error exit retains the captured writer failure; missing diagnostics remain unqualified, not inferred values.

The full suite runs only if all three required positive controls pass and every probe's owned-resource cleanup succeeds. Otherwise the dedicated job returns nonzero `BLOCKED`, `WINDOWS_STARTUP_CHECKPOINT_BLOCKED`, `tests_run=0`, `full_suite_attempted=false`, and `skips=0`. The blocked result retains the actual debug matrix and bounded logs. It cannot become portable-only green. Once checkpoint controls work, the original full **16-test** suite and all five Q04 fault modes must still pass; the debug matrix does not qualify Q01–Q09 by itself. No-console remains outside the selected qualified fixture path unless its separate observation supports a narrower statement.

Relevant primary references read for this refinement: [GetNamedSecurityInfoW](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getnamedsecurityinfow), [SECURITY_INFORMATION](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-information), [ConvertSecurityDescriptorToStringSecurityDescriptorW](https://learn.microsoft.com/en-us/windows/win32/api/sddl/nf-sddl-convertsecuritydescriptortostringsecuritydescriptorw), [TOKEN_INFORMATION_CLASS](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-token_information_class), and [Microsoft `swprintf_s` documentation](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/sprintf-s-sprintf-s-l-swprintf-s-swprintf-s-l?view=msvc-170). These specify diagnostic APIs and support retaining the wide formatter; actual startup/writer causes await the matched Windows receipt.

Final local checks after the evidence-cap correction: **8 portable tests, 0 failures/errors/skips**, suite 0.012 s, summary elapsed 15.0061 ms; three proof Python modules compile; unchanged product/existing-test/workflow and whitespace checks PASS. A separate injected required-checkpoint failure proves the driver returns BLOCKED/nonzero with zero tests, no attempted full suite and no skips; it is explicitly a local driver injection, not Windows evidence. The first injection harness attempt failed before candidate execution when a global `os.name` change made pathlib request WindowsPath on Linux; the corrected module-local stub and that harness limitation are retained in the evidence JSON.

Independent review found a summary-size defect before this candidate was published: removing only `records` on overflow could leave the duplicated `startup_checkpoint` above the 256 KiB limit. The repair fails the job and replaces both oversized evidence sections with original serialized UTF-8 byte count, SHA-256 and explicit omitted/no-qualification disposition. It rechecks the final serialized size and falls back to a minimal failure receipt if other metadata is still oversized. Exact UTF-8 `write_bytes` prevents Windows newline conversion from adding bytes after the cap check; console output also uses the bounded final payload. The underlying oversized data is omitted, with its integrity receipt retained; it is not represented as complete qualification evidence. A sensitivity case with 1,400,347 original bytes retained a 624-byte FAIL receipt with verified original/checkpoint hashes; an additional oversized-metadata case retained a 439-byte minimal FAIL receipt. This is local serializer sensitivity, not Windows evidence.

If a granted worker cannot write even the relative diagnostic file, its exact C stage/path/token data may remain unavailable. The runner preserves the process exit and parent token/file/SD observations, reports the missing diagnostic as unqualified, and blocks required positive controls. It does not substitute assumed token, path or ACL values.

```text
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v4-cap-final/summary.json
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v4-cap-final/proof.log
/workspace/scratch/250985b4823e/audit/tip057rq-checkpoint-v4.json
/workspace/scratch/250985b4823e/audit/tip057rq-evidence-cap-v4.json
/workspace/scratch/250985b4823e/audit/tip057rq-v4-cap-frozen-manifest.json
```

| Frozen refinement-3 payload | Bytes | SHA-256 |
|---|---:|---|
| `.github/workflows/verify-tip057rq.yml` | 1,266 | `cc9efd3faee7b3646bdc29c76c067ba85df6a6b9274db5f9af61d442936467ed` |
| `tests/proofs/tip057rq/authority.py` | 8,423 | `604aeae2fb3da5e9985c3ea28f2f92e1c69d765a5ddda7df15ee43ac251299ff` |
| `tests/proofs/tip057rq/fixture_worker.c` | 12,288 | `bbe7ec83099217cde3f96b996bde9bd7316831faad4d654dc210087a533c6305` |
| `tests/proofs/tip057rq/run_proof.py` | 47,720 | `6263fec47894b960cf4f696add32cfab5ada1011c26c42c8e010288bc757e0d8` |
| `tests/proofs/tip057rq/windows_boundary.py` | 17,303 | `c248ce8d0abda7cce8bd18fdae8d493009cd36edb649338b38f5478a007c56e6` |

These code/workflow bytes are frozen for Contractor publication and independent review. All three unsuccessful Windows receipts remain preserved. Broker/SDK paths, late-dead restart recovery and product integration remain OPEN; no real VPS/terminal or production API was used.

Contractor published the corrected checkpoint/cap payload as head `6b84209a0af2db23e0f64cf4aa866e1580333555`, tree `c4f3526293121fa2dd22783e738888ff604b9a2d`, parent `07316a4a66301eb471112528c2c0e31f781f2bc6`. All 203 remote blobs were verified; independent portable/static checks and the reviewer's final cap/source check passed. The authoritative executable manifest is `tip057rq-v4-cap-frozen-manifest.json`; the earlier v4 manifest is superseded and retained. The fourth Windows receipt is pending, and this still-editing report append was omitted from that published head. Builder now freezes this report revision as well; a later receipt will be recorded as a separate revision.

## Actual Windows receipt 4 — required positive control BLOCKED

Contractor retained the fourth exact-head receipt and independently verified its artifact digest:

| Field | Receipt |
|---|---|
| Reviewed head | `6b84209a0af2db23e0f64cf4aa866e1580333555` |
| Dedicated run / job | `37001271851` / `110819284042` |
| Platform | Windows Server 2025, build 10.0.26100; Python 3.12.10 |
| Result | `BLOCKED`, `WINDOWS_STARTUP_CHECKPOINT_BLOCKED`; **0 tests, 0 failures/errors/skips**, `full_suite_attempted=false` |
| Elapsed | 10,187 ms; bounded checkpoint returned without attempting the 16-test suite |
| Compiler / exact head / source blobs | PASS / PASS / PASS |
| Fixture executable SHA-256 | `ec8a787caa2c3259b2a59e9a10a7225343667be5e7d28b6f23e199aee8be3dd0` |
| Artifact | `11223937630`, 4,338-byte ZIP; SHA-256 `5d466151daadecfd54db52ec3608575b08377ce3fb6276ee19ed7ac179f9cbc5` |
| Proof log | 9,066 bytes, untruncated; SHA-256 `76ac6d010bf29ef87617f642e0026e74c86406dec588b588cc9ac4e9baf8fe94` |
| Retained raw receipts | [summary.json](evidence/tip057rq/fourth-6b84209/summary.json), [proof.log](evidence/tip057rq/fourth-6b84209/proof.log), [compiler.log](evidence/tip057rq/fourth-6b84209/compiler.log) |

The matched writer checkpoint produced these limited observations:

| Variant | Actual receipt | Qualification |
|---|---|---|
| Plain unrestricted console | Exit 0; marker PID 6584; actual C writer completed with error 0, AppContainer 0, integrity RID 12,288, child restriction 0. | Positive startup/marker control PASS only. |
| Granted unrestricted console | Exact owned worker PID 9072 exited 5; marker and relative writer diagnostic absent. | Required positive control FAIL. The receipt does not establish its C entry stage, actual child token or file-failure API. |
| Granted restricted console | Exit 0; marker PID 6164; actual C writer completed with error 0, AppContainer 1, integrity RID 4,096, child restriction 1. | Positive startup/marker control PASS only; no child-launch or lifecycle qualification. |
| Granted restricted no-console | Exact owned worker PID 8784 exited `0xc0000142`; marker and writer diagnostic absent. | Separate startup path unqualified. This is not evidence of process-creation denial. |

The parent token was observed unchanged before/after each launch: elevated 1, AppContainer 0, integrity SID `S-1-16-12288`, user SID `S-1-5-21-1643835476-1616584234-1346609752-500`. Parent-owned CreateFile/WriteFile/Flush observations all succeeded before/after. Every checkpoint row recorded an empty cleanup-error list and exact-handle exit where applicable. These parent observations cannot substitute for the failing child's token or failed API stage.

The granted root and executable read-back SDDL included current-user/SYSTEM and unique AppContainer access entries, with `S:AI` but no visible mandatory-label ACE. That string alone does not establish the actual selected label descriptor, an effective low label, or a causal ACL defect. The succeeding restricted writer and failing unrestricted writer remain distinct observations. No ACL, capability or inheritance repair is inferred from them. All four existing baseline workflows again passed, as reported by Contractor. The full process-prevention, fault-cleanup, crash/recovery and lifecycle acceptance cases remain unqualified by this checkpoint-only receipt.

## Bounded receipt-driven refinement 4 — direct facts without broader grants

This revision changes only the isolated C fixture, Windows boundary diagnostic reader and proof runner. Authority, workflow, process-creation restrictions, no-inheritance policy, capabilities and root/executable grants remain byte-identical to receipt 4. The diagnostic mode remains a finite `write_probe` branch returning before any initialize/observation/child-launch work. Full qualification still requires real positive controls followed by all 16 original tests and five Q04 fault modes.

The parent now queries the actual child token through its owned suspended process handle before `ResumeThread`. It records actual user SID, integrity SID, AppContainer and elevation values. It does not inherit a handle into the worker, look up the child by an unbound PID, or copy expected journal values into observed identity. Query failure records uncertainty and blocks a required checkpoint; all owned process/thread/profile cleanup still runs.

The selected LABEL descriptor is read directly from the returned security descriptor. The reader reports whether the selected SACL is present, null or populated, its actual ACL byte count/ACE count/raw-byte SHA-256, and each selected mandatory-label ACE's flags, mask and SID. It limits parsing to 64 ACEs and preserves truncation as `TRUNCATED_LABEL_PARSE_NO_QUALIFICATION`, which blocks a required control. ACL/ACE sizes, returned pointer ranges and mandatory SID extent are checked before reading or converting the SID. Mandatory SID revision, identifier authority and single-RID shape are validated before conversion. Malformed or inaccessible descriptors fail visibly; absent/null selected labels remain explicit observations, not proof that the requested low label took effect. The query requests DACL plus LABEL only and enables no security privilege.

When the C writer cannot create either its positive marker or diagnostic file, the known `write_probe` mode can emit a compact diagnostic exit. Its emitter uses `0xE5100000 | (stage << 16) | native_error` only for a known CreateFile/WriteFile/FlushFile/CloseHandle stage and a native error fitting 16 bits. Wider errors, CRT errors, short writes and unknown stages retain the fixture's raw exit fallback. Existing file diagnostics still carry immediately captured full native errors when available. The runner always preserves the actual raw 32-bit exit and exact worker/source identity.

An exit value alone does **not authenticate this protocol**: a full-width raw error could itself equal `0xE5110005` or another matching tag. The runner therefore describes an exact tag/version/known-stage match in `write_probe` only as `PARTIAL_PROTOCOL_SHAPED_DIAGNOSTIC_CANDIDATE_KNOWN_PROBE_ONLY`. Its stage and low-16-bit error are explicitly **inferred**, provenance is `NOT_AUTHENTICATED_BY_EXIT_ALONE`, `tag_collision_possible=true`, and `qualification=NONE`. It describes the emitter's fit rule rather than asserting that the observed exit was checked by the emitter. A missing full diagnostic leaves full-error/stage provenance unavailable even when this candidate inference is useful. Selected nonmatching loader/exception values including `0xc0000142` and `0xe0570001` remain undecoded; this is not a claim that every possible native or exception DWORD is disjoint from the tag. A raw matching collision remains a partial, unqualified inference with its raw value preserved. No matching exit can qualify entry, marker writing, child denial, cleanup or prevention.

The required gate still depends on an actual matching-PID positive marker, successful C writer diagnostics, actual token/policy observations, parent file observations, readable selected descriptors and proven cleanup. Nonzero or tagged exits cannot pass it. Any required checkpoint failure remains nonzero BLOCKED with zero tests/full-suite false/no skips. Existing summary/log caps and same-handle cached live-image lifetime checks are unchanged. Q06 still reopens a deliberately live exact worker; a fresh parent first opening an already-dead worker without independently captured live image remains recovery-required. This revision does not establish late-dead recovery or a production entry-path guarantee.

Primary references read for this diagnostic refinement: [GetLastError](https://learn.microsoft.com/en-us/windows/win32/api/errhandlingapi/nf-errhandlingapi-getlasterror), [SYSTEM_MANDATORY_LABEL_ACE](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-system_mandatory_label_ace), and [GetAce](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getace). These document immediate native error capture, application-defined error bit 29, mandatory-label ACE structure and selected-ACE access. They support the reader/emitter design; they do not supply an observed cause for receipt 4.

Final local checks after the collision wording/output correction: **8 portable tests, 0 failures/errors/skips**, suite 0.012 s; summary elapsed 16.0003 ms. All three proof Python modules compile and whitespace checks pass. The product/existing-test/packaging/four existing workflow paths remain byte-identical to the supplied base. Local fake-descriptor sensitivity checks passed for actual flags/mask/SID output and raw ACL hash, explicit absent/null/truncated dispositions, and malformed SID revision/authority/extent/minimum rejection before conversion. This is a fake API/descriptor harness on Linux, not Windows label qualification.

Exit-protocol sensitivity checks passed for all four known-stage candidates, the 65,535 error boundary, selected nonmatching loader/exception/version/stage/mode/raw values, and an explicit **simulated raw matching collision `0xE5110005`**. The latter is preserved as an unauthenticated partial candidate with qualification NONE. Portable/model checks do not establish native startup, child token, selected Windows LABEL behavior or prevention. The initially frozen v5 manifest before collision-output correction is retained as superseded; the final manifest below is authoritative.

```text
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v5-collision-final/summary.json
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v5-collision-final/proof.log
/workspace/scratch/250985b4823e/audit/tip057rq-exit-protocol-v5.json
/workspace/scratch/250985b4823e/audit/tip057rq-label-parser-v5.json
/workspace/scratch/250985b4823e/audit/tip057rq-v5-frozen-manifest.json
/workspace/scratch/250985b4823e/audit/tip057rq-v5-pre-collision-manifest.json
```

| Frozen refinement-4 payload | Bytes | SHA-256 |
|---|---:|---|
| `.github/workflows/verify-tip057rq.yml` | 1,266 | `cc9efd3faee7b3646bdc29c76c067ba85df6a6b9274db5f9af61d442936467ed` |
| `tests/proofs/tip057rq/authority.py` | 8,423 | `604aeae2fb3da5e9985c3ea28f2f92e1c69d765a5ddda7df15ee43ac251299ff` |
| `tests/proofs/tip057rq/fixture_worker.c` | 13,043 | `886f8324aa69b1feabe7a9aa55b32bfd62ec9cbd09157a17cec6cd47c16af44f` |
| `tests/proofs/tip057rq/run_proof.py` | 48,967 | `ae5f6cb7d7be1b48fefd06d10efb0941fb2ca214e9edf257092c8cfc41f85bdf` |
| `tests/proofs/tip057rq/windows_boundary.py` | 20,755 | `3c482885485549780afade171241b1bac43527bef35c11899cd2abb5b2285076` |

Builder freezes these code/workflow bytes and this report for Contractor review/publication. All four unsuccessful Windows receipts remain preserved. The next exact-head Windows receipt must first establish the required positive controls; full Q1 remains PARTIAL, broker/SDK/Q2/product integration OPEN. No production policy, real VPS, terminal, account or SDK operation occurred.

Contractor published the refinement-4 executable payload as head `d156c5ecfef5c1874b2babe9658810cae429db65`, tree `d76da1dc5303f8bf2d0a5e85f6678088d25a383b`, parent `6b84209a0af2db23e0f64cf4aa866e1580333555`. All 207 remote blobs were checked. The still-editing report was excluded from that code publication, then separately frozen at 49,627 bytes, SHA-256 `dd411a3b1854651cc1c382552b48b4083346f646a7aaee452704771c5a03312f`. The following receipt reopens and supersedes that report revision while preserving its findings.

## Actual Windows receipt 5 — executable-label contamination observed

| Field | Receipt |
|---|---|
| Reviewed head | `d156c5ecfef5c1874b2babe9658810cae429db65` |
| Dedicated run / job | `37003376225` / `110825934332` |
| Platform | Windows Server 2025, build 10.0.26100; Python 3.12.10 |
| Result | `BLOCKED`, `WINDOWS_STARTUP_CHECKPOINT_BLOCKED`; **0 tests, 0 failures/errors/skips**, `full_suite_attempted=false` |
| Elapsed | 10,812 ms |
| Compiler / exact head / source blobs | PASS / PASS / PASS |
| Fixture executable SHA-256 | `6a7689dcb70934d0f2e756f50e95fbdef05300019e5bdc5ab1e3d234c1ed70ef` |
| Artifact | `11225385055`, 5,954-byte ZIP; SHA-256 `e62e5781474e0fd6879343d15830758830e244013f686dd58c1222cd4d4ba0ee` |
| Proof log | 14,923 bytes, untruncated; SHA-256 `99011958822f31b447980ca1f48ff363ceca19fa55aad2fa481885ddcfda272c` |
| Retained raw receipts | [summary.json](evidence/tip057rq/fifth-d156c5e/summary.json), [proof.log](evidence/tip057rq/fifth-d156c5e/proof.log), [compiler.log](evidence/tip057rq/fifth-d156c5e/compiler.log) |

The new owned-handle token and direct LABEL reader establish these actual OS facts:

| Variant | Actual observation | Result |
|---|---|---|
| Plain unrestricted console | Writer AppContainer 0, integrity RID 12,288, restriction 0; no selected root/executable label. | Exit 0, marker PID 6340, positive writer PASS. |
| Granted unrestricted console | Suspended child AppContainer 0, elevated 1, same user SID as parent, **integrity SID `S-1-16-4096`**; parent remains `S-1-16-12288`. Root has one low/NW mandatory ACE, flags 3; executable has one inherited low/NW mandatory ACE, flags 16. | Exit `0xe5110005`; marker/diagnostic absent, required writer FAIL. Inferred CreateFile/error 5 remains an unauthenticated diagnostic candidate. |
| Granted restricted console | Suspended child AppContainer 1, integrity SID `S-1-16-4096`; C reports restriction 1 and completes writing. Same actual root/executable low-label pattern. | Exit 0, marker PID 7120, positive writer PASS only. |
| Granted restricted no-console | Suspended child AppContainer 1, integrity SID `S-1-16-4096`; same low-label pattern. | Raw exit `0xc0000142`, no marker/diagnostic; selected path remains unqualified. |

The failing unrestricted worker's exact reference is PID 8632 with creation timestamp `134354155466883123` and the recorded fixture image. Its root mandatory-label ACE is SID `S-1-16-4096`, mask 1, flags 3 (`OBJECT_INHERIT` plus `CONTAINER_INHERIT`). Its executable mandatory-label ACE is the same SID/mask with inherited flag 16. Both selected ACLs contain exactly one ACE and parsing is complete. The parent SID/elevation/IL is unchanged before/after; all before/after parent CreateFile/WriteFile/Flush observations pass. All checkpoint cleanup-error lists are empty, with exact-handle exit recorded for granted probes. Contractor reports all four baseline workflows PASS again.

These facts expose control contamination: the worker called unrestricted did not retain the parent control's integrity level, and its executable actually inherited low integrity from the fixture directory. Microsoft documents that executable integrity can lower the new process token; its ACE inheritance rules apply to SACLs as well as DACLs. This is a supported mechanism for the token difference, and a concrete variable to isolate. It does **not** establish that the integrity change alone caused the prior file access denial: a low-integrity AppContainer writer already succeeds in the matched root, and the failing writer has no authenticated full diagnostic payload. The raw/tag collision limitation from refinement 4 remains unchanged. No prevention, crash-recovery or complete Windows lifecycle case is qualified by this zero-test receipt.

## Bounded receipt-driven refinement 5 — directory-only label and genuine control

Builder proposed the label applicability correction before editing; Contractor approved it within Q1. It changes the mandatory label from `S:(ML;OICI;NW;;;LW)` to `S:(ML;;NW;;;LW)` on each **fresh unique temporary fixture root**. The flat writer directory remains low with no-write-up; its label no longer propagates onto the fixture executable. The inheritable DACL template, current-user/SYSTEM/AppContainer rights, zero capabilities, child restriction, no inherited privileged handles and exact suspended-handle ownership are unchanged. No old object is repaired in place and no broader access mask or privilege is introduced.

The runner records actual executable DACL/LABEL observations before boundary setup and after it, together with the root's post-setup observations. A granted checkpoint must read back exactly one effective root low/NW mandatory label with flags 0, with complete nontruncated parsing. Its executable's complete mandatory-label ACE semantics — type, flags, mask and SID — must match the pre-boundary baseline. Empty selected-SACL/autoinherit/header metadata may differ without adding a mandatory label; the gate compares actual mandatory ACE semantics rather than SDDL or raw empty-header bytes. The intentional inherited DACL grants are still recorded but are not incorrectly required to leave the executable DACL unchanged. Unreadable/truncated/malformed observations retain explicit uncertainty and block qualification, with before/after facts preserved in the bounded receipt.

The granted unrestricted checkpoint now requires its exact suspended child's actual user SID, integrity SID, AppContainer and elevation observations to equal the actual parent control token. This conservative equality is a fixture acceptance gate, not a universal claim about every Windows process launch. A low child can no longer be counted as an unrestricted positive control merely because AppContainer is 0. The restricted checkpoint requires actual suspended AppContainer 1 and low integrity, with the unchanged C child-policy gate. In all variants the C writer's integrity RID must match the corresponding actual parent/owned-child observation. Real matching-PID marker, completed writer/API results and proven cleanup remain mandatory; a token or label readback alone cannot pass the checkpoint.

Microsoft documents that created objects receive their creator's integrity level. The candidate therefore retains the low worker's directory access while isolating the binary's baseline label. Actual Windows writer success remains the acceptance test for new marker/diagnostic files; this documentation is not substituted for that receipt. If the narrower label prevents a required real write, the checkpoint stays BLOCKED with zero tests/no full suite/no skips. No label restoration, broad grants or additional startup flags are used to force green.

Relevant primary documents read for this refinement: [Mandatory Integrity Control](https://learn.microsoft.com/en-us/windows/win32/secauthz/mandatory-integrity-control) and [ACE Inheritance Rules](https://learn.microsoft.com/en-us/windows/win32/secauthz/ace-inheritance-rules). They support the executable-token clamp, creator/object label behavior and root-only label semantics. They do not certify the previous CreateFile failure cause or the next candidate's native outcome.

Final local checks: **8 portable tests, 0 failures/errors/skips**, suite 0.011 s; summary elapsed 14.7611 ms. Three proof Python files compile; whitespace checks pass; all production, packaging, existing unit-test and four existing workflow paths remain byte-identical to the supplied base. C, authority and workflow bytes are unchanged from receipt 5. No native Windows operation occurred locally.

A focused read-back sensitivity check uses receipt 5's retained actual root/executable observations: the previous inherited low binary fails the new isolation gate. A synthetic corrected root and unchanged mandatory ACEs with different empty-descriptor metadata pass; inherited root, changed binary SID/mask/low label, unreadable descriptor and truncation cases reject. This proves gate sensitivity with retained/synthetic input only, not actual Windows correction or prevention. The existing lifecycle, exit-tag collision and evidence-cap sensitivity records remain retained.

```text
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v6-final/summary.json
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v6-final/proof.log
/workspace/scratch/250985b4823e/audit/tip057rq-label-isolation-v6.json
/workspace/scratch/250985b4823e/audit/tip057rq-v6-frozen-manifest.json
```

| Frozen refinement-5 payload | Bytes | SHA-256 |
|---|---:|---|
| `.github/workflows/verify-tip057rq.yml` | 1,266 | `cc9efd3faee7b3646bdc29c76c067ba85df6a6b9274db5f9af61d442936467ed` |
| `tests/proofs/tip057rq/authority.py` | 8,423 | `604aeae2fb3da5e9985c3ea28f2f92e1c69d765a5ddda7df15ee43ac251299ff` |
| `tests/proofs/tip057rq/fixture_worker.c` | 13,043 | `886f8324aa69b1feabe7a9aa55b32bfd62ec9cbd09157a17cec6cd47c16af44f` |
| `tests/proofs/tip057rq/run_proof.py` | 51,797 | `5b84125564ec027eb7cf6afb14db95ed3e5f3ad667ff90c98bea9c9c769650de` |
| `tests/proofs/tip057rq/windows_boundary.py` | 20,910 | `36cc06ea8a80e2f7c6f24cb973c9aede62df4183d8d2c4b56d4d31cb0f542c84` |

Code/workflow and this report are frozen for Contractor review/publication and the next exact-head Windows receipt. All five unsuccessful receipts remain preserved. Full Q1 remains PARTIAL; Q03 broker/SDK, late-dead recovery, Q2 physical MT5 and product integration remain OPEN. Even successful positive controls must be followed by the original full 16-test/five-fault-mode suite before bounded lifecycle claims can be assessed. No application, production policy, real VPS, terminal, account or SDK was changed or invoked.

Contractor published the refinement-5 executable payload and consolidated frozen report together as head `8f2a0d1d08dae0aad0409348f9c7320f0b24d45c`, tree `58b2afe3be6736ad0815ba5f47411729009d6bc8`, parent `d156c5ecfef5c1874b2babe9658810cae429db65`. All 211 remote blobs were verified; independent portable checks and source/report review passed. This receipt reopens the report after its 59,839-byte revision, SHA-256 `490147a71bb200a6a9e783d3322db42f993d2eb016f33feae36db36bed906a4a`.

## Actual Windows receipt 6 — checkpoint PASS, one full-suite failure

| Field | Receipt |
|---|---|
| Reviewed head | `8f2a0d1d08dae0aad0409348f9c7320f0b24d45c` |
| Dedicated run / job | `37004481970` / `110829439538` |
| Platform | Windows Server 2025, build 10.0.26100; Python 3.12.10 |
| Result | `FAIL`; **16 tests, 15 PASS, 1 failure, 0 errors/skips**, `full_suite_attempted=true` |
| Timing | Runner elapsed 13,453 ms; unittest suite 2.991 s |
| Compiler / exact head / source blobs | PASS / PASS / PASS |
| Fixture executable SHA-256 | `ccf4ef2261a2819d4a9aa8aa7b02069fa1f914c6ddc5a959ea231010546c3845` |
| Artifact | `11224633998`, 9,344-byte ZIP; SHA-256 `20627556a457c728c2dfa127953aaf2183a71bdb40b709933a886ea9ea12706e` |
| Proof log | 4,491 bytes, untruncated; SHA-256 `f7799aa4f164b6c0714fd35e5ac0ff24f2fff4ac05b1301c8483fc78896429cf` |
| Retained raw receipts | [summary.json](evidence/tip057rq/sixth-8f2a0d1/summary.json), [proof.log](evidence/tip057rq/sixth-8f2a0d1/proof.log), [compiler.log](evidence/tip057rq/sixth-8f2a0d1/compiler.log) |

All three required writer controls passed. Actual root labels are low/NW with no inheritance flags; actual executable mandatory-label semantics match their pre-boundary baseline. The granted unrestricted suspended child matches the high-integrity parent control (`S-1-16-12288`, AppContainer 0, elevated 1, same user SID), and its actual writer succeeds at integrity RID 12,288. The restricted console writer succeeds at RID 4,096/AppContainer 1/child restriction 1. The nonrequired no-console observation still fails with raw `0xc0000142` and remains unqualified. These matched facts support the narrower label applicability correction; they do not retroactively authenticate the previous writer exit's stage/error or certify an SDK path.

The full suite contains eight portable cases and eight Windows cases. All eight portable cases and seven Windows cases passed; all five Q04 fault submodes completed. The current bounded fixture acceptance is:

| Case / boundary | Receipt 6 |
|---|---|
| Q01/Q09 real pre-work restriction and setup failure before create attempt | PASS; actual restricted startup and no-attempt release case. |
| Q02 target exits before gated replacement attempt | PASS for the tested direct fixture path. |
| Q02/Q03 unrestricted/restricted paired launch and inherited privileged-handle probe | FAIL; unrestricted half works, restricted half exits before reporting its probe/startup. Complete paired denial remains unqualified. |
| Q04 initialize false, initialize SEH, observation SEH, shutdown SEH and combined primary/shutdown fault | PASS for all five synthetic callback modes, including observable cleanup attempts and precedence. No SDK shutdown claim. |
| Q05 hang holds lease until exact worker termination | PASS; 250 ms observation budget, actual total 359 ms, recorded termination sample 0 ms. Timer-resolution sample is not an instantaneous or hard-10-second guarantee. |
| Q06 parent crashes before failure marker | PASS; actual controller exits 73, intent survives, worker remains live for exact reopen/termination and acquisition stays blocked. Fresh already-dead recovery remains OPEN. |
| Q07 creation mismatch, stale generation, descendant uncertainty, fresh-dead identity refusal | PASS; PID reuse is simulated by changing a real process's creation timestamp, not actual forced PID recycling. |
| Q08 two independent blocked callers and stale recovery thread/successor race | PASS; both process callers BLOCKED and checked thread outcomes `STALE_REJECTED`/`BLOCKED` preserve generations 1/2. |
| Q03 breakaway control | OPEN: matching unrestricted API returns error 5 without creating a child. Ambient host-job denial cannot qualify candidate-caused breakaway denial. |

The working unrestricted launch control is worker PID 2620 under actual parent PID 8092. It reports the inherited parent handle resolving to PID 8092, and both separate `OpenProcess` probes for `PROCESS_CREATE_PROCESS` and `PROCESS_VM_WRITE` succeed with error 0. Its direct child is actually created, terminated and writes the marker; breakaway fails with error 5. After that lifecycle closes, the restricted worker PID 7596 enters C (`entry.json` present), then exits raw `0xc0000008` before `started.json`, initialize, cleanup or child markers. Receipt 6 cannot authenticate which call raised it because this version has no per-probe phase/exception observation. The borrowed numeric-handle `GetProcessId` call is the focused hypothesis, not an established fault-site attribution from the raw exit alone. Contractor reports all four unchanged baseline workflows PASS.

## Bounded receipt-driven refinement 6 — observable borrowed-handle rejection

Contractor approved the smallest probe correction within Q1. Only the harmless C fixture and its runner change. The helper guards **only `GetProcessId` on the supplied borrowed numeric handle**, using the existing MSVC SEH mechanism with an exact `EXCEPTION_INVALID_HANDLE` filter. A different native exception uses `EXCEPTION_CONTINUE_SEARCH`; unknown faults remain visible and fail the worker. There is no strict-handle policy change, inherited-handle change, extra capability or access grant. The borrowed numeric value is never closed, and no expected-parent PID is reopened.

For a nonzero supplied argument C writes a pre-call phase marker carrying its actual worker PID and argument. Completed `started.json` carries structured probe evidence with the same actual PID/argument, attempted flag and disposition. An actual successful API call records the returned PID/value with no claimed failure error. An actual zero API return records return value 0 and immediately captured Win32 error, with PID null because no PID was obtained. A captured invalid-handle exception records its actual exception code and null API-return/PID/error fields. A zero argument records no attempt. The code never substitutes PID 0 or an invalid-handle error because the worker was expected to be restricted. These probe exceptions are distinct from Q04's injected callback counts.

The paired test now requires the unrestricted inherited-handle control to actually return the parent PID with no fault, match the supplied argument/active worker, and independently open both privileged rights successfully. The restricted probe must attempt the same nonzero argument in its actual worker and report either actual API return 0 plus `ERROR_INVALID_HANDLE` 6, or captured `EXCEPTION_INVALID_HANDLE` `0xc0000008` with no claimed API return. An unrelated valid PID alias, other error, unknown exception, mismatched worker/argument, nonattempt or inconsistent mixed result is rejected. A rejected borrowed-handle probe is not itself child-launch denial: AppContainer 1, child restriction 1, both separate parent rights errors 5, actual child API creation failures/nonzero errors and no child markers still remain required. The matching breakaway control may still leave that path OPEN.

The new marker is in the per-attempt cleanup allowlist. If a worker exits before completed evidence, the runner retains the bounded pre-call marker, raw exit, exact lifetime and ordinary phase-marker observations without assigning a fault site or treating the absence as denial. Exact process ownership, durable arm/create/bind/resume sequence, shared lease recovery, cleanup, source/head verification and evidence caps are unchanged. Required Windows cases are still never skipped or relaxed to force green.

Primary references read for this refinement: [GetProcessId](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocessid), [Exception-Handler Syntax](https://learn.microsoft.com/en-us/windows/win32/debug/exception-handler-syntax), [MSVC try-except](https://learn.microsoft.com/en-us/cpp/cpp/try-except-statement?view=msvc-170), and [GetExceptionCode](https://learn.microsoft.com/en-us/windows/win32/debug/getexceptioncode). They document PID/error returns, exact exception filters and observing the code inside a handler. They do not establish the receipt-6 fault site or replace the next real Windows receipt.

Final local checks after required-keyset review correction: **8 portable tests, 0 failures/errors/skips**, suite 0.015 s; summary elapsed 18.1938 ms. Three proof Python modules compile; whitespace and protected source/existing-test/packaging/four-workflow checks PASS. No native C compilation or execution was performed on Linux; the dedicated Windows job must compile the exact new C blob and qualify its real handler/probe behavior. Boundary/authority/workflow bytes are unchanged from receipt 6.

A local evidence-gate sensitivity check accepts the two fully specified recognized forms and rejects ten adverse forms: unrelated PID, unknown API error/exception, synthetic PID zero, claimed API return after SEH, mixed API/SEH result, wrong argument/worker, nonattempt and wrong API. A zero argument also rejects. This uses synthetic dictionaries only and is explicitly not native C execution or Windows qualification. All earlier native/raw failures and local sensitivity evidence remain retained.

Independent review found that `.get()` treated an omitted nullable field as explicit null. Before publication the gate was corrected to require an object and the full probe keyset. Deleting each of nine required fields from each recognized form now rejects (18 deletion cases), and five non-object inputs reject. C already emits the complete payload; this correction prevents incomplete evidence from being accepted by the runner. The pre-keyset manifest is retained as superseded; the final manifest below is authoritative.

```text
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v7-keyset-final/summary.json
/workspace/scratch/250985b4823e/audit/tip057rq-portable-v7-keyset-final/proof.log
/workspace/scratch/250985b4823e/audit/tip057rq-borrowed-probe-v7.json
/workspace/scratch/250985b4823e/audit/tip057rq-v7-frozen-manifest.json
/workspace/scratch/250985b4823e/audit/tip057rq-v7-pre-keyset-manifest.json
```

| Frozen refinement-6 payload | Bytes | SHA-256 |
|---|---:|---|
| `.github/workflows/verify-tip057rq.yml` | 1,266 | `cc9efd3faee7b3646bdc29c76c067ba85df6a6b9274db5f9af61d442936467ed` |
| `tests/proofs/tip057rq/authority.py` | 8,423 | `604aeae2fb3da5e9985c3ea28f2f92e1c69d765a5ddda7df15ee43ac251299ff` |
| `tests/proofs/tip057rq/fixture_worker.c` | 15,684 | `8c56e060a9f3010f74e4acde73631975486d64ab0c4e74119623253489f0974a` |
| `tests/proofs/tip057rq/run_proof.py` | 53,917 | `bd4d2d159a07aa7a2a81cb4b7f1dbe5ec400b4c044381ec92f4d2372ab1c4365` |
| `tests/proofs/tip057rq/windows_boundary.py` | 20,910 | `36cc06ea8a80e2f7c6f24cb973c9aede62df4183d8d2c4b56d4d31cb0f542c84` |

Builder freezes code/workflow and this report for Contractor review/publication and receipt 7. All six unsuccessful receipts remain preserved, including the 15-PASS/one-failure receipt. Full Q1 remains PARTIAL; Q03 broker/SDK/breakaway, late-dead recovery, no-console startup, Q2 physical MT5 and production integration remain OPEN. A fully successful bounded fixture suite would still not authorize production no-start or physical rollout. No app, production policy, VPS, terminal, account or SDK was changed or invoked.
