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
- optional background task: `VibeMQL5-OpenAI-Tunnel-Background-C`

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

## Rollback

If C onboarding fails, stop/disable instance C only and preserve A/B plus the certified TIP-033 backend. Do not downgrade or restart A/B unless evidence shows they were affected.

Do not merge/promote TIP-036 solely because repository tests pass. Live workspace-C tunnel provisioning and A/B/C acceptance remain required for final TIP-036 completion.
