# TIP-070 proposal — durable synchronous test invocation and finite timeout result

Contractor review required before implementation. Source parent is exact `7a4535b1cdaed3d7cb5d484642c099239944ab6b`, tree `96b5e4e553100655ecb304d14bf7e31ba114ffcb`. PR65 remains Draft OPEN/unmerged; main `70e2112da9fe8eaa6262f2ba896b55bf3e078260` remains unchanged. Source qualification remains NOT_ACCEPTED_6_OF_8.

## YAGNI-3 before code

1. Needed: actual installed-identical `BackendAdmin.run_tests` loses the structured invocation on a subprocess timeout, and even a successful synchronous return has no durable discovery record if the connector response is lost. A real bounded subprocess control reproduces that defect at the actual pinned MCP SDK boundary.
2. Reuse: keep the existing synchronous method, all six suite bodies, the existing allowlist, `write_json_atomic`, `_exclusive_file_lock`, and `backend_read_evidence`. Existing SDK offloading and async start/get remain unchanged. No new worker, scheduler, service, API or migration.
3. Minimum: change only `backend_admin/core.py` plus a focused regression module and contract/completion/evidence. Preserve normal returned payloads and signature. Add a small bounded RECENT discovery index and one atomic per-invocation record which preserves start facts; normalize only `subprocess.TimeoutExpired`.

## Proven causal control and negative controls

`causal-probe-v2.log` and `causal-probe-receipt.json` preserve real subprocess success, exit7, timeout and unexpected-error controls. The suite body still requested timeout300; only the external controlled child used .2 seconds to exercise the exception path. `TimeoutExpired` with retained `CONTROL_START` output escaped through the SDK as `UnexpectedToolError: Error executing tool backend_run_tests`; no durable invocation files existed. Successful and nonzero results also had no durable invocation receipt. Unexpected `ValueError` kept its original type/cause and SDK masking.

The SDK concurrently served a harmless read while the subprocess was still pending. Therefore synchronous tools do not prove event-loop starvation in this control. The first probe's failed read assertion is retained: its unparameterized `-> dict` control returned text with `structured_content=None`; the final control uses `dict[str, Any]`, as the actual backend tool does. This is a control correction, not a production fix.

The relevant installed hashes match exact source: core71407/SHA4f5b4b9b5002279d6daa1f8ad49e3d3701be719197e648fda87864bf50348573; tools4001/SHAb1eac2805743e24c93eaf9ecf81001220f694916fb57dc1f0c32a898338b818d; multitunnel6258/SHAefb49b676fa37bb05688ce23592ab5a7fd19bbb645285309aec0b784b14c8c7c.

## Concrete minimum design

Keep `run_tests(suite)` synchronous. Reject unsupported suites with exactly the existing payload and no invocation/child effects. Separate the current allowed-suite implementation into a private helper without changing argv, suite behavior, timeout180/300, baseline assertions, soak handling or output payloads.

For an allowed invocation, publish a per-invocation start record before calling the unchanged suite helper. Under the existing style of exclusive file lock, publish an atomic fixed-path index at `evidence/runtime/backend-admin/test-runs/sync-invocations.json`. Retain at most32 generated descriptors: invocation id, allowlisted suite, UTC start time, one generated evidence-relative path. Track total/evicted descriptor counts honestly. This index is only RECENT discovery; absence or eviction never proves completion, inactivity, process closure or an old run's identity. Every per-invocation file remains retained outside the bounded index, with its original start facts kept after final state publication. The index contains no status/PID claim which could become stale.

Each invocation uses one generated file under the same backend-admin test-runs directory. Terminal state is written atomically to that file, retaining the original invocation id, suite and start timestamp; this follows the existing async ledger style without adding event sourcing. The generated id is not an operator's idempotency key. Start means the wrapper was entered, not that a child is running. A missing final state means completion UNKNOWN. No lookup or reconstruction of the historical receiptless sync run is attempted.

Bound/read/validate the existing index before mutation; malformed, oversized or write-failed discovery publication blocks the suite helper, so no new child starts without a discoverable start receipt. Generated record collisions also block rather than overwrite retained evidence. Retain a start written before an index failure, with completion UNKNOWN; do not erase it. Use no automatic retries or repair/reset.

On an ordinary return, atomically publish the final record with `INVOCATION_RETURNED` and the existing result, then return the identical result object/payload. A soak `STARTED` result records a returned invocation and does not claim the soak has passed or completed.

On `TimeoutExpired` only, atomically publish an `INVOCATION_TIMEOUT` final state and return a truthful finite result: statusFAIL, suite, reason_codeTEST_RUN_TIMEOUT, returncodeNone, the original finite timeout and bounded stdout/stderr tails. Handle CPython's bytes or text exception output explicitly; tails remain capped at the existing4096 characters. Keep the cause type in the receipt, without copying argv or `str(exception)`. Do not claim descendant closure from subprocess.run's direct-child timeout handling; descendants remain UNKNOWN. Do not change production timeout budgets.

On any other exception, attempt an atomic `INVOCATION_EXCEPTION` final state with safe exception_type only, then re-raise the exact original object. Preserve the SDK's existing masking; do not dump raw args/error text/credentials. A secondary final-record write failure must not replace the primary unexpected exception. If ordinary-result or timeout final publication fails, preserve failure/unfinished evidence and surface the publication failure rather than return an unreceipted PASS. No guard state is cleared or reinterpreted.

Existing async `start_test_run`/`get_test_run` behavior, catalog85/schema hashes, signatures and source/legacy adapter schemas stay unchanged. An internal async worker calling `run_tests` gains an invocation record without another worker or control-flow change. The records describe calls to this method, not an asserted MCP transport or known historical operation.

## Meaningful verification before review

- Real bounded subprocess success, nonzero, timeout with flushed partial stdout/stderr, and unexpected exception: exact returned payload/signature compatibility and timeout FAIL without PASS conversion.
- Start is discoverable through the existing `backend_read_evidence` before a held child is released; all per-invocation files and start facts remain retained after index cap eviction; cap/counts truthful and no PID/activity inference.
- Child never starts if start/index publication fails, index is corrupt/oversized, or generated evidence would overwrite a prior retained invocation record.
- Original unexpected exception object survives independent final-write failure; successful/timeout final-write failure cannot produce an accepted result. Safe exception_type receipt omits secret exception text/args.
- Unsupported suite stays identical and has no new files/subprocess effects; existing baseline framework-error denial stays FAIL; soak STARTED stays open rather than PASSED.
- Actual MCP SDK dispatch and normal-success/nonzero controls; all existing async idempotency/conflict/get controls remain compatible. Catalog/input/output schemas unchanged.
- Freeze source before focused tests; preserve command/env/log/JUnit/manifests, including failed probe/control versions. Contractor reviews independently before publication or deployment.

## Compatible deployment mapping and limits

Only production file proposed for a legacy overlay is `app/vibemql5/backend_admin/core.py`, derived from bytes that historically match the installed hash above. No full-source MCP/facade/preflight is copied. Before deployment, root must obtain fresh installed source/hash, ensure exact byte compatibility or review a narrow derivation, checkpoint/CAS the live file, review source gates/artifacts, use current typed guards, read back hash and verify current loaded runtime/catalog without a blind restart. If connector/guards remain unavailable, deployment remains BLOCKED; authorization does not supply missing readiness evidence.

No source edit has been made for this proposal. It repairs a proven future test-invocation receipt/timeout defect. It does not prove or repair the current all-tool MCP-32603 outage, establish the old synchronous run outcome, solve MT5 IPC login/session/data-root, qualify native tester/FIFO overlap/fresh feed, or make source6/8/physical/production gates accepted. Historical installed derived MCP/preflight/facade bytes are not recoverable from the retained evidence seen so far; their differing hashes prohibit treating full-source variants as the installed legacy code.
