# TIP-036 — ChatGPT Business Workspace C Onboarding

## Goal

Add a third independent ChatGPT Business workspace (`C`) as an operational peer of the existing A/B clients without creating a second VibeMQL5 backend or a second MT5 execution lane.

Backend invariants remain unchanged:

- one shared VibeMQL5 backend;
- fixed native terminal `MT5-2`;
- native MT5 parallelism `1`;
- source-mutation parallelism `1`;
- global FIFO/idempotency/CAS contracts remain authoritative;
- MCP tool catalog remains `72 server / 71 model-visible`;
- MCP request metadata is provenance only, not security-grade ChatGPT account identity.

## Workspace-C tunnel identity

TIP-036 adds the allowlisted instance:

- instance: `C`
- profile: `vibemql5-vps-c`
- runtime config: `ops/windows/vibemql5.windows.c.json` (generated locally, not committed)
- runtime secret reference: `secrets/tunnel-runtime-key-c.dpapi`
- health/ready port: `8082`
- interactive task: `VibeMQL5-OpenAI-Tunnel-C`
- watchdog task: `VibeMQL5-Watchdog-C`
- background task (enabled for certified A/B/C boot parity): `VibeMQL5-OpenAI-Tunnel-Background-C`

The generated C config is derived from the canonical A Windows config while assigning C-specific profile, secret reference, task names, log/state paths, and health port.

## External OpenAI provisioning boundary

Workspace C is independent, so its tunnel object and authorization must be created inside the Platform organization/workspace that owns ChatGPT Business workspace C.

Required operator setup:

1. In ChatGPT Business workspace C, an admin/owner enables Developer mode / custom MCP apps.
2. In OpenAI Platform, create a tunnel scoped to the correct ChatGPT workspace C.
3. The runtime principal used by the long-lived daemon receives `Tunnels Read + Use`.
4. Create a Restricted runtime API key with `Tunnels Read + Use`.
5. Keep any admin key used for tunnel CRUD separate from the runtime key.
6. In ChatGPT workspace C connector settings, use `Connection: Tunnel` and select/paste the workspace-C tunnel ID.
7. Configure the custom MCP app with the intended full action permissions for workspace C.

Do not commit tunnel IDs, API keys, DPAPI blobs, MT5 credentials, or ChatGPT workspace secrets to Git.

## VPS provisioning boundary

Before `tunnel_admin_install_autostart(instance="C")` can succeed, provision these external runtime artifacts on the certified VPS:

- the `vibemql5-vps-c` tunnel-client profile bound to workspace C's tunnel ID;
- a machine-bound DPAPI runtime key at `C:\VibeMQL5\secrets\tunnel-runtime-key-c.dpapi`.

Use the supported tunnel-client profile/doctor workflow rather than hand-writing secret material into YAML. The repository intentionally does not create or read these secrets.

After those prerequisites exist, the canonical control-plane action is:

```text
tunnel_admin_install_autostart(instance="C")
```

Expected result:

- generated C config passes drift validation;
- Scheduled Tasks for C are installed;
- exactly one `vibemql5-vps-c` tunnel-client process is active;
- `http://127.0.0.1:8082/healthz = 200`;
- `http://127.0.0.1:8082/readyz = 200`;
- A and B remain untouched.

## Credential-backed boot parity for B/C

The certified VPS now uses `enableBootTunnel=true` for A, B, and C. Each
instance has its own interactive, watchdog, and background Scheduled Task.
The background task starts under the same Windows Administrator identity
using Task Scheduler password logon, which can read that user's machine-bound
DPAPI secret before an interactive sign-in.

For B/C, run the existing `Install-VibeMQL5ScheduledTasks.ps1` with the
instance-specific `-ConfigPath`, `-EnableBootTunnel`, and a `PSCredential`
entered directly in an interactive Administrator PowerShell session. Keep the
Windows password out of ChatGPT and the repository. Verify the config flag,
background task `Password` logon type, and A/B/C health/ready after each
install. Task registration alone does not certify an actual pre-logon boot;
that needs a separately controlled restart observation.

The MCP `tunnel_admin_install_autostart` tool is for initial
interactive-only provisioning. If `enableBootTunnel=true` is already set,
it refuses before running the noninteractive installer, preserving the
credential-backed task and config. Repair/re-register a boot-enabled task
from the interactive Windows session using the installer above.

## Acceptance sequence

### Gate 1 — read-only

From A/B control plane:

1. `server_info`
2. `health`
3. `runtime_status`
4. `tunnel_admin_status(instance="all")`

Require A/B/C each to have exactly one expected process and healthy endpoints before any symmetry test.

From a new chat in Business workspace C:

1. enable the custom `TunnelVibemq5` app;
2. call `server_info`;
3. call `health`;
4. call `runtime_status`.

Require the same release identity and `72/71` tool surface.

### Gate 2 — controlled write capability

From C, perform one guarded non-trading mutation/readback flow using checkpoint + exact SHA/CAS, then restore/reconcile if the test contract requires it.

The purpose is to prove C is not read-only.

### Gate 3 — native capability

Run one bounded DemoEA acceptance from C on fixed `MT5-2` using a stable `operation_id`.

Require:

- compile `0 errors / 0 warnings`;
- fixed terminal `MT5-2`;
- fallback `false`;
- normal tester finish;
- cleanup/reconnect PASS;
- exact replay recovers the same job and does not spawn a duplicate.

### Gate 4 — A/B/C symmetry

Submit controlled A/B/C operations so the shared backend proves:

- global native FIFO remains serial;
- source mutations remain serial/CAS protected;
- C cannot bypass existing idempotency rules;
- no tunnel restart for one instance cross-kills another;
- final queue and locks are clean.

Formal acceptance wording after PASS:

`A/B/C = operational peers with equivalent VibeMQL5 tool capability.`

Keep the security statement separate:

`authenticated_account_identity = false`

The backend does not use A/B/C labels as authentication identities; OpenAI workspace/tunnel authorization remains the access-control boundary.

## Certified live acceptance — 2026-09-23

All four gates passed on the certified VPS with Bridge `0.2.34 / TIP-033`,
`72 server / 71 model-visible` tools, shared backend, and fixed `MT5-2`.
A, B, and C are operational peers with equivalent VibeMQL5 tool capability.
Each workspace uses its own OpenAI tunnel authorization and client profile;
backend `authenticated_account_identity=false` remains unchanged.

| Gate | Live evidence |
| --- | --- |
| 1 — read-only | Business C exposed the expected tool surface and READY backend; A/B/C each had one tunnel process and health/ready 200/200. |
| 2 — guarded write | C patched and restored `demo/Experts/DemoEA.mq5` using checkpoint `CP-20260923-131540-1B1C44D9BD64`; source returned to SHA-256 `a80e47af086a210825a32f26faa681fc12932a8b99d57540aec6eafa38d3b66c` (2026 bytes). |
| 3 — native and replay | C job `BT-20260923-134405-6E6273` passed on MT5-2, no fallback, compile 0 errors/0 warnings, normal tester finish, cleanup/reconnect PASS; identical replay recovered the same job without spawning another. The raw MetaEditor `process_exit_code=1` remains in the receipt alongside compile PASSED and immutable EX5 output; it is not a general rule that exit code 1 means success. |
| 4 — shared concurrency | Overlapping B → C → A jobs `BT-20260923-140624-BCF201`, `BT-20260923-140629-9DF4C4`, and `BT-20260923-140643-75AA2B` passed with serial native leases. B's guarded comment patch produced SHA-256 `0b27f54b08abdddf0520a85652f5703dc2b586edf13fdd75b0e9ddd8b1cb51c3`; A's stale restore was rejected without changing it; C's CAS restore receipt matched the baseline. Restarting C alone preserved the A/B PIDs. |

Cold boot was observed while Windows remained at its sign-in screen:
A/B/C background tasks were Running, interactive tasks Ready, each tunnel had
one process and health/ready 200/200, and B/C chats directly called
`server_info` and `health` in background mode. After Administrator sign-in,
all three handed off to interactive tasks with one process per instance and
health/ready 200/200. The final backend was READY with queue=0,
active_job=null, native_lock=null, mutation_lock=null; DemoEA was byte-exact
at the baseline hash above. No MT5 account, credentials, or AutoTrading change.

Repository CI for the TIP-036 code candidate passed TIP-027, TIP-028, and
TIP-034 workflows; the certified VPS unit suite passed 405 tests. Detailed
receipts and exact commit CI are linked in PR #16.

## Rollback

If C onboarding fails, stop/disable instance C only and preserve A/B plus the certified TIP-033 backend. Do not downgrade or restart A/B unless evidence shows they were affected.

Do not merge/promote TIP-036 solely because repository tests pass. Live workspace-C tunnel provisioning and A/B/C acceptance remain required for final TIP-036 completion.
