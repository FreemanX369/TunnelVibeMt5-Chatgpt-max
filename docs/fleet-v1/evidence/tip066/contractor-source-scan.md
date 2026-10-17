# Independent source diagnostics — 2026-10-06

Accepted parent fe6ef1baa359ea2acbba7e3e0f78ae872ed1c55f and tree
e0881d89cca4663805af8de22e8ca7649a0f95f5 match the freshly cloned detached
checkout, PR #65 and GitHub Git API. Main remains 70e2112da9fe8eaa6262f2ba896b55bf3e078260.
Eight raw GitHub run resources independently confirm accepted head/attempt1/success.

All five current typed runtime observations fail with raw MCP -32603. Their
timestamped original tool envelopes were preserved before parsing. No current
runtime, process, queue, native/mutation guard or old sync-test outcome is available.
No recovery, restart, test rerun, authority initialization or native effect ran.

Source backend_admin/tools.py exposes both async start/get test APIs; session
tool discovery does not expose either. Synchronous core.run_tests(unit) calls a
300-second subprocess without a durable operation/run receipt. Its old effect
cannot be looked up using the async API. Missing visibility, synchronous durability
and old run outcome remain OPEN; no speculative runner change is dispatched.

An existing local verification environment was observed at the prior workspace's
source-venv, with SDK distribution mcp2.1.1. Its FuncMetadata.call_fn already
offloads synchronous handlers through anyio.to_thread.run_sync. A direct new
offload wrapper is unnecessary. This observation does not establish current loaded
VPS SDK identity or the outage cause.

The SDK's Tool.run preserves deliberate ToolError messages and masks arbitrary
RuntimeError as UnexpectedToolError. Source LiveTerminal.state emits five literal,
safe anticipated runtime codes; source MCP _invoke propagates them without this
expected-error boundary. TIP-066 corrects only this demonstrated diagnostic loss.
The connector's historical INVALID_ARGUMENT mapping remains unlocated/UNKNOWN.

Observed SDK tools/base.py SHA256
3d0c9dfbe3ab9f6f641f2434752396345a3fb0eb6728e9b1054078c52b77671e;
utilities/func_metadata.py SHA256
cb4327569c0bdbb3af3d04e113b5cf589216dba3855645afce87c00895608636.

Original artifact ZIPs independently reverified with the packaged existing verifier
against exact Git blobs: all five digests/sizes, 211-entry integrated manifests,
Linux1229 PASS/18 skip and Windows1235 PASS/12 skip, 1247 testcase each, zero
failure/error, and nine harmless proof receipts PASS. No product suite was rerun
for that unchanged accepted parent. Fresh source candidate gates remain separate.

Both failed native jobs, unavailable fresh feed, old sync UNKNOWN_NO_RECEIPT,
historical owner-grant/COMMIT causes and all physical qualification gates retain
their previous state. Account/credentials/AutoTrading and installed runtime untouched.
