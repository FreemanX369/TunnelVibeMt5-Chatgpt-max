# TIP-066 — Builder completion

Status: **DONE, source implementation and focused verification**. Parent accepted
`fe6ef1baa359ea2acbba7e3e0f78ae872ed1c55f`; Contractor independent review and
the new candidate's exact-head eight-workflow/artifact gate remain separate.

## YAGNI-3 before implementation

1. Necessary: three legacy reads lose five anticipated finite failure codes at
   the MCP SDK's unexpected-exception boundary.
2. Reuse: existing `_invoke`, lazy SDK import, `ToolError`, exact literals and
   actor/native authority paths.
3. Smallest change: one guarded conversion in `_invoke`, with no new tool,
   module, worker, runner, dependency or policy.

## Files and behavior

Builder modified `app/vibemql5/adapters/mcp.py` and created
`tests/unit/test_tip066_live_diagnostics.py` plus this report. The dispatch
contract and other Contractor documentation/evidence are separate contributions.

Only `get_terminal_live_state`, `get_account_snapshot` and `inspect_terminal`
convert an exact anticipated RuntimeError message to the SDK's `ToolError`.
The original exception remains its cause. Codes are
`FIXED_TERMINAL_NOT_RUNNING`, `MT5_LIVE_IPC_INITIALIZE_FAILED`,
`MT5_LIVE_TERMINAL_INFO_UNAVAILABLE`, `MT5_LIVE_TERMINAL_BINDING_MISMATCH`
and `MT5_LIVE_ACCOUNT_INFO_UNAVAILABLE`. Other exceptions are re-raised unchanged.
No prefix parsing or raw account/path/credential diagnostic collection was added.

## Acceptance and evidence

| Acceptance | Builder result |
|---|---|
| Five codes across three operations | PASS: 15 real SDK dispatch cases retain the safe exact code |
| Unexpected, prefix-extended, busy, ownership and other runtime failures | PASS: original exception identity at adapter; generic SDK masking |
| Same known reason outside three operations | PASS: no conversion on chart inventory/journal |
| Invalid arguments | PASS: SDK validation rejects before facade invocation |
| Actual protocol result | PASS: `_handle_call_tool` returns `is_error=True`; anticipated code retained, unexpected secret absent, invalid input remains validation failure |
| Success and actor scope | PASS: payload retained; scope active during calls and restored afterward |
| Targeted denial | PASS: real routed `fleet.read/1` denial, ownership NOT_ACQUIRED; no legacy observation |
| Catalog/input/output schemas | PASS: all 85 match accepted-parent schema SHA `3e17166f81acf897aa3de3c55964e117923897c5658391de37d528c40d234f06` |
| Existing live/C1/identity/ownership/backend controls | PASS: compatibility suite, with one existing Windows junction skip |

Focused v1: **44 PASS, 0 skip, 6.86 s**. After Contractor requested the actual
protocol-handler result coverage, focused v2: **47 PASS, 0 skip, 6.13 s**.
The first receipt remains preserved; these counts overlap and are not summed.
Compatibility v1: **196 PASS, 1 existing Windows skip, 5.28 s**. `git diff --check`
passed. Native/VPS effects and physical qualification were NOT_RUN.

Retained evidence is `evidence/tip066/builder/` beside this report, copied from
`/workspace/scratch/b4674f0ac496/resume-20261006/builder/`:
`focused-v1.log`, `focused-v2.log`, their JUnit files, `compatibility-v1.log/JUnit`,
`parent-schema.json`, `environment-setup.json`, dependency installation logs and
`completion-summary.json` with final file digests/dependency versions,
`commands.json` and `file-manifest.json` with every retained evidence digest.

## Retained environment failures and limitations

The saved previous virtual environment had a broken Python symlink (exit 127).
Loading its saved native cryptography files with the current Python produced
SIGBUS (exit 135) before tests. These are retained local tooling failures; they
do not identify the VPS outage. The old environment was not repaired or reinstalled.

Contractor authorized a fresh scratch test environment, using Python 3.12.14 and
the existing `requirements-bootstrap.lock`: MCP/MCP-types 2.1.1, pytest 9.1.1,
cryptography 50.0.1. The initial unconstrained resolver log was preserved before
applying existing constraints. Explicit PYTHONPATH selected the current worktree
instead of any old editable installation. Repository dependencies were unchanged.

No commit, push, deployment, restart or old-evidence modification occurred in this
Builder task. MCP SDK 2.1.1 already offloads synchronous functions; no additional
offload or outage fix is claimed. Connector INVALID_ARGUMENT mapping, current
MCP availability/guards, MT5 IPC/login cause and the old synchronous unit call
remain UNKNOWN. Async client exposure, sync-test durability, full Fleet physical
qualification and production merge remain OPEN.
