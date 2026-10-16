# Integrated116 deployment — 2026-10-16

The existing TunnelVibemq5 deployment now combines the 85 installed legacy tools with 31 isolated Fleet tools. The legacy application files and original protocol schemas remain unchanged. The shared entry is `operator-integrated-mcp.py`, SHA256 `525bb848f40c96d953e8a3a4568f4aac5b987106aefc79fdef560f3af10a00c9`. Fleet source is frozen at `745147f525caefbec66505e5cdb6a4fb7013c2d7`; the operator implementation branch was recorded at `578f52123b9a667cafaeacef9c31337e53335c81` before deployment.

All receipts below are under `C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a\integrated116`, except backend restart receipts under `C:\VibeMQL5\evidence\runtime\backend-admin`.

| Gate | Result and evidence |
| --- | --- |
| Before deploy | `E2E-predeploy-a4-RECEIPT.json`: 15 PASS; earlier failed harness attempts retained |
| A live tunnel | `server_info` returned 116 tools, the exact entry SHA, and runtime PID5816 |
| A restart | `BRESTART-20261016-180915-306372EC`: PASS, terminal_touched=false |
| A postdeploy MCP | `E2E-A-a1-RECEIPT.json`: 15 PASS; SHA256 f87e15877b9cf52ac001616ac73047f456b2bb404aec44a59913b1269177b120 |
| A ChatGPT discovery | Existing app refreshed; visible catalog Write86 + Read30, including Fleet names |
| B profile/restart | Protected original backup and byte-exact command replacement; `BADMIN-20261016-181348-357A2D38`: READY, HTTP200, one tunnel PID3324 |
| B postdeploy MCP | `E2E-B-a1-RECEIPT.json`: 15 PASS; SHA256 1e2611d05d705a8e4f63f089d15eed786dd556890bf71f5e859d96e99a2d627c |
| C profile/restart | Protected original backup and byte-exact command replacement; `BADMIN-20261016-181446-98F70609`: READY, HTTP200, one tunnel PID3256 |
| C postdeploy MCP | `E2E-C-a1-RECEIPT.json`: 15 PASS; SHA256 b0d937ce1ab16fadbed323f4f4e6614655d8747c3060a57bc0285c6376c4e669 |
| B/C ChatGPT discovery | User confirmed manual refresh on both accounts at22:18ICT; no additional login needed. Separate authenticated B/C calls were not independently observed. |

All three profile hashes were re-read and matched their apply receipts. A/B/C share one physical VPS. The local MCP tests exercise the deployed entry through real stdio, legacy quote/OHLC/tick reads on MT5-2, Fleet inventory/idempotency, and the expected `LIVE_ATTACH_ONLY_UNPROVEN` denial. These tests do not authenticate ChatGPT accounts B/C and do not qualify Fleet native execution, capacity, writers, multi-node operation, rollback exercise or unattended production.

Rollback: run `bind-integrated-profile.py --instance A|B|C --mode rollback` only after checking idle native/mutation guards and the current profile hash, then restart that exact tunnel instance. The binder enforces CAS and restores the protected original bytes. Do not clear Fleet journals or install synthetic qualification markers.

Final user checks after each account's app refresh: `server_info` should return tool_count116, legacy85, Fleet31 and the exact entry SHA; `health` should return READY; `fleet_server_info` and `fleet_inventory` should be callable. One tool is app-only, so expected model-visible count is115. Start a fresh conversation if the existing conversation retains its old tool definitions.

Final status at18:17ICT: all three tunnels have HTTP200 health/ready and exactly one process; no retained poll failures. Legacy health READY, queue0, no active job or native/mutation lock. Backend software deployment complete; B/C ChatGPT catalog refresh remains blocked on account sign-in.

## Refresh confirmation and pilot recovery — 22:26ICT

Owner confirmed manual refresh on B and C. Do not request another account login. The current ChatGPT tool surface now exposes all31 Fleet tools; actual fleet_server_info succeeds. Fresh runtime server_info116 and exact entrySHA remain verified. A/B/C health/ready HTTP200, one process each, no retained tunnel poll failures; legacy health READY, idle guards.

The first actual fleet_inventory call failed. Runtime failure receipt shows gateway/node PID5660 exited at20:00:48ICT with WireError HTTPS_UNAVAILABLE. Root cause is UNKNOWN; no causal fix is claimed. Task was stopped, listener8443 absent; control revision9700/nonces9698 remained below configured65536 capacities. Original receipts were copied under runtime/retained-2225-* before a single existing-task resume (PSHELL-20261016-222453-A0AC7A29); no journal reset or source/config change. New PID4268, fresh LIVE22:25:36, same route/session. Through the actual ChatGPT plugin, routed inventory command dcmd_950357f2e7d84ad3af39d1a1bfbf5c17 COMPLETED with5 rows, and identical operation replay returned the same command. MT5-2 XAUUSDm quote also succeeded. These checks demonstrate current recovery, not uninterrupted availability or production soak acceptance.

Status: backend deployment and owner-confirmed B/C refresh complete; ready for the owner's final pilot test. Full physical Fleet release and unattended reliability remain unqualified; preserve the20:00 failure for follow-up.
