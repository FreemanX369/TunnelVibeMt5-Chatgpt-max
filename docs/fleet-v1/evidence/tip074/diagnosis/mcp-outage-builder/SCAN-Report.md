# MCP outage boundary review — Vibecode Kit v6 SCAN

Status: DONE read-only boundary review; live outage cause and deployment remain BLOCKED/UNKNOWN.

Exact source: `ef31be719b090c14effa96e69c08d405ac0ceceb` in `tip073-candidate`. No source, test, workflow, dependency, VPS, tunnel, account or AutoTrading edits were made. No live connector calls were invoked by this Builder. Root owns live read-only observations and any later deployment decision.

## YAGNI-3 before diagnostic code

1. Needed: determine whether the unavailable MCP calls have an independent observation path, and whether a proposed extra offload would repair a demonstrated defect. Freeze source to keep the review attributable.
2. Reuse: existing 217-entry Contractor source manifest, SDK controls in `test_tip070_sync_test_receipts.py` and `test_tip066_live_diagnostics.py`, pinned local SDK source and existing admin/status/evidence tool definitions. Reuse `hashlib`, `subprocess` and pytest; no product code is necessary.
3. Shortest: hash the existing file list, run only the five pre-existing owned SDK controls, and inspect exact source functions. No new service, transport, worker, API or generic recovery shell is justified.

## Demonstrated boundaries

`adapters/mcp.py::create_server` imports SDK types, constructs `ToolFacade`, reconciles cancellation recovery, constructs one MCPServer, then registers ordinary tools and backend-admin tools on that same server. The admin object is separate, but its connection and startup are shared. Admin registration also retains the historical hardcoded `C:\VibeMQL5` root; this is existing source behavior, not a demonstrated current runtime defect.

`server_info` invokes provenance loading, fixed-terminal resolution, runtime provenance and deployment preflight. `health` invokes resource/inventory/job/concurrency state. These functions have different per-call dependencies. The source admin `backend_get_file_hash` and `describe_capabilities(workspace="")` bypass those facade read/preflight functions, but still require the same server and transport to exist. They are discriminating probes, not an independent recovery channel.

Local SDK2.1.1 `FuncMetadata.call_fn` already invokes synchronous callables with `anyio.to_thread.run_sync`. The existing held-run control proves the same SDK serves a harmless read and retrieves the invocation index while a synchronous backend test is pending. Adding another offload cannot be justified by the one-held-call/event-loop-starvation theory.

Local SDK2.1.1 `_handle_call_tool` turns anticipated, unexpected and argument-validation errors into an error `CallToolResult`; the existing controls prove safe `is_error=True` content, with no leaked private error text. Current live raw JSON-RPC `Mcp error: -32603: Internal error` does not identify a specific facade or MT5 exception. The external connector may remap errors; its behavior and the current installed/loaded SDK remain unknown.

## Ranked mechanisms for further observation

Rank is investigation priority, not a probability or causal conclusion.

| Rank | Mechanism | Current support | What discriminates it |
|---|---|---|---|
| 1 | Shared ingress, transport/session, server startup or connector error boundary | Five historical distinct typed reads failed with the same raw envelope; root reports current hash bypass also fails. Backend admin shares server/startup. | Exact root live receipts; current tunnel status/poll episodes or supervisor/stdio startup facts from an independently usable ingress. No such independent ingress is exposed here. |
| 2 | Installed mixed legacy initialization/source/package/config problem | Historical source differs from installed derived adapter/facade/preflight, so source code cannot establish current initialization. Current server creation eagerly constructs the facade before any tool is registered. | Fresh loaded process/version/source hashes and bounded startup failure type/phase. Current identity and loaded package/config facts remain unknown. |
| 3 | Held synchronous call, descendant pipe cleanup or shared worker exhaustion | Existing runner waits synchronously in a worker thread; direct test timeout is300s. Actual CPython source has an unbounded Windows post-kill `communicate()` to collect stdout/stderr. A descendant retaining a pipe is a credible cleanup mechanism. | Actual Windows owned child/descendant pipe control and fresh old-run/child process facts. One held-call control does not establish shared-pool exhaustion. No actual Windows/VPS causal reproduction occurred in this review. |
| 4 | Particular health/preflight/MT5 per-call failure | These functions may fail, but the bypass hash probe reportedly fails too. Expected source live exceptions produce safe SDK tool error results. | A successful admin bypass alongside failed facade reads, or exact backend error phase. No such success is available. |

The `subprocess.run` limit follows directly from the local CPython3.12.14 source: on timeout it kills the direct process; in the Windows branch it calls `process.communicate()` with no new timeout. This review ran on Linux and did not observe this Windows branch or any VPS descendant. It is not a proven explanation for the all-tool outage and supplies no authority for process-tree termination. TIP-070's durable START record describes entry to the method; a missing final record remains completion UNKNOWN.

## Existing observation and recovery routes

| Tool or route | Safe use and interpretation | Limit |
|---|---|---|
| `backend_get_file_hash(path="app/vibemql5/backend_admin/core.py")` | Hash-only read of allowlisted source, bypasses facade health/preflight. | Root reports raw-32603 currently; no current installed hash was learned. |
| `describe_capabilities(workspace="")` | Literal backend metadata, no requested workspace read or native action. | Exists in source but root reports no exposed function in this session. Do not invent a function call or infer installation from exposure. |
| `backend_read_evidence(relative_path="backend-admin/test-runs/sync-invocations.json", max_bytes=262144)` | TIP-070 RECENT discovery index under `<root>/evidence/runtime`; retained descriptors can lead to individual invocation records. | No `runtime/` prefix. On a legacy runtime without TIP-070 it may not exist; absence/error cannot identify the earlier receiptless call. RECENT eviction is not completion/idle proof. Root reports one wrong-prefix read returning-32603 and is retaining it as non-discriminating. |
| `runtime_status()` | Current facade reports supervisor/watchdog state plus provenance classification. | Requires shared server. Root reports raw-32603 currently. Historical files are not current readiness. |
| `tunnel_admin_status(instance="all")` | Existing allowlisted status reports A/B/C process count, tasks, healthz/readyz and bounded poll diagnostics. | Same ingress; root reports raw-32603 currently. Local HTTP endpoints are queried only from inside the VPS tool; they are not exposed external recovery endpoints. |
| `backend_restart_runtime`, `tunnel_admin_restart` | Existing typed mutation routes after actual current guards and target identity are observed. | Same unavailable ingress. These change tasks/processes and do not independently prove idle/old descendant closure; no call is proposed or invoked while those facts are unknown. |
| `backend_start_test_run` / `backend_get_test_run` | Existing source asynchronous API uses operation-id receipts for future starts. | Not exposed in the current chat according to retained evidence; cannot look up the historical receiptless sync invocation. |

There is no callable independent remote read-only/recovery transport demonstrated by this repository or by current connector exposure. A/B/C profiles do not imply this chat has another connected ingress. Fleet source functions are a separate catalog and do not provide a working legacy escape channel.

## Owned verification and evidence

Five existing controls ran once in an owned local directory, using exact candidate `app` on PYTHONPATH, local Python3.12.14/MCP2.1.1/pytest9.1.1. Result: **5 PASS, 0 failure/error/skip, pytest1.35s, wall1.82s**, child external deadline45s. This is not a VPS test, Windows qualification, new product suite or rerun of the historical effect.

- `test_actual_sdk_can_discover_held_invocation_and_read_concurrently` — held synchronous invocation remains pending while a read and index read succeed.
- `test_unexpected_error_identity_and_secret_mask_at_actual_sdk` — direct original error identity survives; SDK masks private text and records safe type.
- `test_protocol_handler_returns_safe_error_result[anticipated|unexpected|invalid_arguments]` — three actual protocol-handler error-result shapes remain safe.

Commands, environment overrides, original stdout, complete JUnit and exact local SDK/stdlib snippets+hashes are retained in this folder. `source-before.json` uses the existing Contractor `combined-source-before.json` 217-file list and matches every frozen SHA. The first diagnostic attempt selected the metadata receipt instead of that manifest; it failed before source writes or tests and remains preserved in `diagnostic-bootstrap-failure.json`. The corrected source manifest is explicit. `source-after.json` verifies all217 source files still match before and the candidate remains unchanged.

## Completion / recommendation

No new outage-fix production change is supported by a causal proof. TIP-070 already corrects the independently proven future synchronous invocation receipt/timeout diagnostic loss; it does not recover the receiptless old call or guarantee descendant closure. Keep that distinction when deploying any eligible one-file legacy overlay.

Continue justified source fixes in parallel with the runtime blocker. For runtime, use current typed read-only observations and preserve raw errors. If all usable routes fail, the technical next dependency is an independently reachable VPS/tunnel status source, not another unverified source replacement or a blind restart. Any eventual deployment still needs fresh installed/loaded identity, compatibility of derived legacy bytes, guard facts, checkpoint/CAS, hash readback and loaded runtime verification. Full-source adapter/facade/preflight must not be substituted for the historical mixed legacy variant based on only repository head.
