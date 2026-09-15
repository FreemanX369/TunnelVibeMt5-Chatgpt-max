# TunnelVibeMQL5 TIP-033 Operator Guide

This document is the post-TIP-035 operating and handover guide for normal use, new ChatGPT conversations, and fresh-environment qualification.

## 1. Certified release authority

Repository:

`FreemanX369/TunnelVibeMt5-Chatgpt-max`

Certified baseline:

- version: `0.2.34`
- bridge build: `TIP-033`
- result schema: `1.4`
- server tools: `72`
- model-visible tools: `71`
- catalog SHA-256: `c3457dce5ad2e1e4461f49786a01278f45e10e411c301c447a6905b7f3eef670`
- fixed native terminal: `MT5-2`
- native parallelism: `1`
- source mutation parallelism: `1`
- certified GitHub baseline: `634e8878c62c541ade7bd64d1d8db4e3cf33426f`

A newer `main` is acceptable only when it is an authorized descendant with an explained change history.

Final TIP-033 formal certification:

- `120/120` samples
- max consecutive bad: `0`
- bad episodes: `0`
- tunnel PID changes: `0`
- generation changes: `0`
- final healthz: `200`
- final readyz: `200`
- final heartbeat fresh: `true`
- evidence role: `CURRENT_RUNTIME_CERTIFICATION`
- current runtime certification: `true`

TIP-035 is complete. Historical failed soak evidence remains part of the release history and must not be erased.

## 2. Standard operating contract

Use the canonical MCP operations whenever they exist. Do not replace them with generic shell or PowerShell control paths.

Keep these invariants:

1. Native execution remains fixed to `MT5-2` unless Owner policy explicitly changes.
2. Latest actually observed MT5 build is runtime authority when it differs from stale configured metadata.
3. Only one native MT5 operation may execute at a time.
4. Only one source mutation may execute at a time.
5. Replayable operations use stable `operation_id` values.
6. Existing-source/backend mutation requires the documented checkpoint plus exact expected-SHA/CAS contract.
7. GitHub changes use branch + PR. Do not direct-commit `main`.
8. Never expose, print, export, or commit runtime API keys, tunnel credentials, MT5 credentials, or secret bytes.
9. Do not infer security-grade ChatGPT account identity from MCP request metadata.
10. Preserve release evidence, including failed historical certification attempts.

Normal operations are allowed after the initial read-only health gate:

- source read/write through guarded operations
- checkpoints and CAS patching
- EA compile
- MT5 tests
- FIFO/idempotent job execution
- result, log, tester-event, and artifact readback
- runtime snapshot/comparison
- GitHub branch/PR work

## 3. New chat against the existing certified VPS

Enable the project tools:

`@TunnelVibemq5 @GitHub`

First perform read-only verification:

1. `server_info`
2. `health`
3. `runtime_status`
4. `tunnel_admin_status(instance="all")`
5. verify GitHub `main`

Expected release identity:

- `0.2.34 / TIP-033`
- `72` server tools
- `71` model-visible tools
- catalog SHA `c3457dce5ad2e1e4461f49786a01278f45e10e411c301c447a6905b7f3eef670`
- fixed terminal `MT5-2`

Expected healthy baseline:

- service `READY`
- queue `0`
- active job `null`
- native lock `null`
- mutation lock `null`
- terminal inventory healthy
- Tunnel A and B each have exactly one canonical process and healthy health/ready endpoints

Do not treat historical PIDs or supervisor generations as permanent release identifiers. A legitimate lifecycle event may change them. Unexpected drift during a protected certification window is different and must be investigated.

## 4. Canonical new-chat prompt

Copy the following prompt into a new conversation:

```text
@TunnelVibemq5 @GitHub

Continue project FreemanX369/TunnelVibeMt5-Chatgpt-max from the certified TIP-033 / TIP-035 checkpoint.

Do not re-audit TIP-026 through TIP-035 from the beginning.
Do not reset or overwrite historical evidence.
Do not direct-commit main.
Do not expose/read/export secrets.
Do not change MT5 account, credentials or AutoTrading unless I explicitly authorize it.
Do not use generic shell/PowerShell MCP when a canonical TunnelVibemq5 operation exists.

CURRENT CERTIFIED RELEASE AUTHORITY

Repository:
FreemanX369/TunnelVibeMt5-Chatgpt-max

Certified main baseline:
634e8878c62c541ade7bd64d1d8db4e3cf33426f

Accept a newer main only if it is an authorized descendant and the change is fully explained.

Runtime release:
version = 0.2.34
bridge_build = TIP-033
result_schema = 1.4
server tools = 72
model-visible tools = 71
catalog_sha256 = c3457dce5ad2e1e4461f49786a01278f45e10e411c301c447a6905b7f3eef670
native_mt5_parallelism = 1
source_mutation_parallelism = 1
fixed native terminal = MT5-2

TIP-035 FINAL CERTIFICATION = PASS.

Final TIP-033 formal certification:
samples = 120/120
max_consecutive_bad = 0
bad_episodes = 0
tunnel_pid_changes = 0
generation_changes = 0
final_healthz = 200
final_readyz = 200
final_heartbeat_fresh = true
evidence_role = CURRENT_RUNTIME_CERTIFICATION
current_runtime_certification = true

FIRST ACTIONS — READ ONLY

1. server_info
2. health
3. runtime_status
4. tunnel_admin_status(instance="all")
5. verify GitHub main is the certified baseline above or an authorized descendant
6. confirm there is no unexplained repo/runtime drift

Do not rerun old TIP phases or the formal soak solely to reconfirm already-certified behavior.

If authority is healthy, continue directly with the task I provide after this prompt.

OPERATING RULES

A. Latest actually observed MT5 build wins stale configured metadata.
B. MT5-2 remains the fixed native execution terminal unless Owner changes policy.
C. One native MT5 operation at a time.
D. One source mutation at a time.
E. Preserve operation_id/idempotent replay semantics.
F. Existing-source/backend mutation requires checkpoint + expected SHA/CAS.
G. GitHub mutation requires branch + PR.
H. Never infer authenticated ChatGPT identity from request metadata.
I. Preserve historical failed certification evidence.
J. Use runtime evidence rather than assumption when declaring PASS.

After the health gate, report only material drift/blockers and then continue the requested task without restarting the historical audit.
```

## 5. Fresh Windows VPS deployment

Repository bootstrap authority is documented in:

`docs/bootstrap/WINDOWS-VPS-BOOTSTRAP.md`

Use that runbook rather than inventing a second installation path.

Target canonical root:

`C:\VibeMQL5`

A new VPS must provision the external prerequisites independently:

- supported Windows host
- Python 3.12 environment required by the repository
- MetaTrader 5 / MetaEditor
- registered fixed alias `MT5-2`
- authorized `tunnel-client.exe`
- approved tunnel profile
- fresh machine-bound secret provisioning
- MT5 account state external to Git

Do not copy an existing VPS DPAPI-encrypted secret blob to the new machine. Provision the destination secret independently.

Recommended fresh-host sequence:

1. Clone the authorized repository commit into `C:\VibeMQL5`.
2. Follow `docs/bootstrap/WINDOWS-VPS-BOOTSTRAP.md` exactly.
3. Run the documented mutation-free bootstrap dry-run first.
4. Provision external tunnel and secret prerequisites.
5. Install canonical scheduled tasks through the repository installer.
6. Keep the Scheduled Task as the single interactive Tunnel A lifecycle owner.
7. Verify health/ready endpoints and exact process count.
8. Connect ChatGPT and verify `server_info`, `health`, and `runtime_status`.
9. Run one bounded DemoEA native qualification on fixed `MT5-2`.
10. Verify exact replay does not spawn a duplicate native job.
11. Verify cleanup, reconnect, queue, and locks are clean.

## 6. New ChatGPT account/workspace

The Git repository does not provision ChatGPT account/workspace entitlement or secrets.

For a new account/workspace:

1. verify that the target account/workspace can add and use the required custom MCP/tunnel connection;
2. create/provision the tunnel credential through the supported OpenAI workflow;
3. bind the ChatGPT connection and VPS daemon to the same intended tunnel;
4. never commit the runtime credential to Git;
5. verify the expected VibeMQL5 tool surface before enabling production mutation;
6. run read-only `server_info`, `health`, and `runtime_status` before any write action.

Account/workspace capability must be qualified on the target account rather than assumed from the currently certified account.

## 7. Portability certification boundary

TIP-035 certifies the release on the qualified environment. It does not by itself prove that every clean Windows VPS and every new ChatGPT account can reproduce the deployment without external provisioning.

Use the stronger label `FRESH-ENVIRONMENT PORTABLE CERTIFIED` only after a genuinely fresh VPS plus target ChatGPT account/workspace pass the qualification below.

Required portability evidence:

- clean checkout needs no hidden worktree files;
- repository bootstrap succeeds using documented prerequisites;
- no old-machine secret/state dependency exists;
- runtime becomes READY;
- expected tool catalog is visible;
- health/ready endpoints return 200;
- exactly one canonical lifecycle owner/process exists per tunnel instance;
- fixed terminal is `MT5-2`;
- no terminal fallback occurs;
- DemoEA compiles with 0 errors / 0 warnings;
- native test finishes normally;
- cleanup/reconnect passes;
- exact replay spawns no duplicate job;
- final queue/locks are clean;
- target ChatGPT workspace exposes the expected read/write surface required by the deployment.

## 8. Fresh-environment qualification prompt

```text
@TunnelVibemq5 @GitHub

FRESH ENVIRONMENT QUALIFICATION — TunnelVibeMQL5 TIP-033 or authorized successor.

Goal:
prove that this new VPS + target ChatGPT workspace/account can reproduce the canonical deployment from the repository without relying on hidden state from the old VPS.

Do not copy secrets or DPAPI blobs from the old machine.
Do not change production MT5 credentials or AutoTrading.
Do not import historical runtime state as proof of the new installation.
Do not direct-commit main.

FIRST verify GitHub authority and identify the current authorized release.

Then qualify only portability:

1. Verify fresh checkout.
2. Verify documented repository bootstrap completes.
3. Verify all tracked dependencies and external prerequisites are explicit.
4. Verify C:\VibeMQL5 installation.
5. Verify tunnel profile uses newly provisioned credentials.
6. Verify Scheduled Task is the single lifecycle owner.
7. Verify watchdog and health/ready endpoints.
8. Verify exact process count.
9. Verify server_info identity and tool catalog.
10. Verify queue and locks are clean.
11. Verify fixed MT5-2 policy.
12. Verify MetaEditor/terminal availability.
13. Compile DemoEA.
14. Run one bounded native DemoEA acceptance.
15. Record latest observed MT5 build.
16. Verify cleanup/reconnect.
17. Replay the same operation_id and prove no duplicate native job.
18. Verify ChatGPT can call read-only MCP tools.
19. Verify one controlled non-trading write-capable operation only if the target ChatGPT workspace supports the required write surface.
20. Produce a final portability report.

PASS requires:
- no hidden checkout dependency
- no old-machine secret/state dependency
- runtime READY
- expected tool catalog
- health/ready 200
- exactly one canonical lifecycle owner
- no duplicate tunnel process
- fixed MT5-2
- no fallback
- DemoEA compile 0 errors / 0 warnings
- native test normal finish
- cleanup/reconnect PASS
- exact replay spawns no duplicate
- queue/locks clean
- target ChatGPT connector exposes the expected tool surface

If a prerequisite is missing, report the precise missing artifact/config/documentation instead of silently patching around it.

This is portability qualification only. Do not re-audit historical TIP-026 through TIP-035 behavior unrelated to fresh deployment.
```

## 9. Release versus portability status

Current project classification:

- `RELEASE CERTIFIED`: YES — TIP-035 / TIP-033.
- `FRESH-ENVIRONMENT PORTABLE CERTIFIED`: requires an actual clean-VPS + target-account qualification run before claiming this stronger status.
