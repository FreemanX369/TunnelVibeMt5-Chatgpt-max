# TIP-066 — Preserve anticipated legacy live-read failures

Contractor dispatch, 2026-10-06, under the approved continuous source build.
Parent accepted head `fe6ef1baa359ea2acbba7e3e0f78ae872ed1c55f`, tree
`e0881d89cca4663805af8de22e8ca7649a0f95f5`; Draft #65 remains open/unmerged.

## Trigger and YAGNI-3

Legacy live reads raise finite RuntimeError codes from LiveTerminal.state(). The
source MCP invocation boundary propagates them unchanged. Independently inspected
MCP SDK 2.1.1 Tool.run masks an arbitrary exception as UnexpectedToolError, while
an explicitly raised ToolError preserves its anticipated safe message. This is a
reproducible diagnostic loss. The external connector's previous INVALID_ARGUMENT
mapping, actual MT5 IPC/login cause and current -32603 outage remain UNKNOWN.

1. Needed: let three existing legacy live reads retain their known failure code.
2. Reuse: existing _invoke, SDK ToolError, literal codes, actor scope and guards.
3. Smallest change: operation-and-exact-code conversion at the MCP boundary;
   real SDK regression tests. No new tool, runner, module or thread offload.

## Scope and acceptance

Only get_terminal_live_state, get_account_snapshot and inspect_terminal convert
exact RuntimeError messages FIXED_TERMINAL_NOT_RUNNING,
MT5_LIVE_IPC_INITIALIZE_FAILED, MT5_LIVE_TERMINAL_INFO_UNAVAILABLE,
MT5_LIVE_TERMINAL_BINDING_MISMATCH and MT5_LIVE_ACCOUNT_INFO_UNAVAILABLE to
the SDK's anticipated ToolError. Do not parse prefixes, inspect SDK last_error,
expose raw account/path/credential text or blanket-map arbitrary errors.

* All five codes across all three operations survive real SDK dispatch safely.
* Unexpected exceptions remain the original exception at the adapter boundary;
  real SDK masking continues to withhold their sensitive text.
* Known-looking errors on other operations are not converted. Native busy,
  ownership/admission and runtime-capability errors preserve their prior behavior.
* Invalid arguments remain SDK validation failures. Successful result and every
  tool input/catalog schema remain unchanged.
* Targeted reads retain their existing fleet.read/1 validation/qualification
  denial; no target, SDK, account or native capability is opened.
* Actor scope is active during the facade call and restored on all outcomes.

Builder owns implementation, focused tests and a Completion Report. Contractor
reviews the frozen diff and runs independent SDK/compatibility checks. The new
candidate requires its own exact-head eight original workflows, complete artifact
digests/manifests/JUnit/proofs before any allowed update. Failed evidence is retained.

## Runtime and deferred work

Fresh server_info, health, runtime_status, diagnose and tunnel_admin_status all
returned MCP -32603 on 06/10 at 18:34 ICT. Current READY/PID/queue/locks remain
UNKNOWN; no restart, rerun, install, ownership initialization or native demo is
authorized by absent guards. Preserve both failed demo jobs and the old sync unit
call UNKNOWN_NO_RECEIPT. Existing async start/get test APIs do not look up that call
and are not callable in this session. SDK 2.1.1 already offloads synchronous functions;
no event-loop cause or fix is claimed. Full Fleet physical qualification, actual
client visibility, sync-test durability and production merge remain OPEN.
