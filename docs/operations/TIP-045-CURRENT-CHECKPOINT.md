# TIP-045 operating checkpoint — 2026-09-28

## Release and repository

Owner authorized merging and resolving pending work on 28 September.
- PR #47 merged: dfa1aef287cc6c67dcd9f4deb0b539e9c1ce2e7f.
- PR #15 historical certification/operator docs merged: 6a219d08ebece08ab226c071ac9a9402489e1615.
- Runtime observed before this merge: TIP-045 / 0.2.41, 79 server tools, 78 model-visible; app-only import_ex5_authorized_file.
- Catalog SHA-256: a0d2240862369aaf67039b34921bda2b0eeb3aba7e9dae1f4c71c44fd5c40106.
- Eight PR #47 runtime/provenance files matched deployed VPS SHA-256 during today's review. This is scoped parity, not full-tree certification.
- Exact PR #47 HEAD 8b58a8d73058354d6cfaadec1528948afabd1c9b had successful TIP-027 / TIP-028 / TIP-034 workflows.
- No source deployment or runtime restart was needed to merge already-deployed TIP-045.

## Direct evidence in the current chat

Before the later transport failure, health was READY, queue 0, active job and locks null. A/B/C each had one process and 200/200 health/ready. Runtime/watchdog provenance was fresh.
All 78 expected model tools were exposed in this chat, unlike the earlier 26 September snapshot.

MT5-2 live build 6230, connected=true. Live state, account snapshot, chart listing, Journal and inspect_terminal succeeded. Attached EA count remains UNKNOWN.
A direct default capture on chart 132050 (XAUUSDm/M1) returned PNG 960x540, 25194 bytes, SHA-256 9510cd08056a797d1f8de434d3778be08db7a8ca2efc75d52e7c0818c1a63ca8.
Its bytes were locally hash verified and embedded in the answer. Current-chat capture does not prove Business C widget UI acceptance, every account's schema, or complete placement rollback.

The earlier INVALID_ARGUMENT did not recur after MT5 startup/update, but no root cause or source fix was established. The earlier terminal crash is also unresolved.

## New blocker during post-merge verification

backend_run_tests(suite="unit") was invoked once on the existing VPS. The call ended with HTTP 502: {"detail":"Plugin service request failed"}. No suite receipt or final result was received.
A subsequent export_file request returned MCP -32603 Internal error; health and runtime_status also returned -32603 Internal error.
This is an UNKNOWN test outcome and a connector/transport blocker, not evidence that pytest failed or that the backend stopped.
Do not launch another suite until existing process/receipt status is known. Do not claim that the test caused the connectivity failure without logs.

## Pending gates and disposition

| Item | Status / next action |
|---|---|
| TIP-042–045 source merge | DONE, PR #47 |
| TIP-035 historical operator docs merge | DONE, PR #15 |
| Current Windows unit suite | UNKNOWN after transport error; recover receipt before retry |
| Current runtime health after test | BLOCKED by connector Internal error |
| Export without recapture | Attempt failed at connector; recheck after recovery |
| TIP-045 formal soak | Not started in this session; historical TIP-033 soak is not current TIP-045 certification |
| Build 6230 native compile/backtest qualification | Not run in this session |
| A/B/C separate Chat/UI acceptance | Requires each target chat; current chat cannot certify others |
| Fresh VPS/account portability | Requires actual fresh environment and external provisioning |
| PR #42 ordinary Chat event wakeup | Retain draft diagnostic channel; no marker/task created; BLOCKED receiver capability |
| PR #1 old bootstrap document | Superseded by implemented runtime, merged releases and this checkpoint; close as superseded rather than merging stale PENDING states |

## Recovery and continuation

1. Call server_info then health using the existing connector. If unavailable, record actual failure; do not manufacture receipts.
2. When access returns, inspect runtime_status and A/B/C status; resolve whether the unit suite is still running or has a durable result.
3. Read its result before retrying. Restore healthy idle gates without changing MT5 account, credentials or AutoTrading.
4. Run the existing tip033_soak suite only after the runtime is healthy and stable; it starts the existing 60-minute/30-second-sample current-build protocol. A STARTED receipt is not PASS.
5. Keep historical resilience evidence intact. Require final 120 samples, zero bad episodes/PID/generation changes and current-runtime binding before declaring certification.
6. Qualify native MT5 6230 only with the existing fixed-MT5-2 workflow and scoped DemoEA settings.
7. Preserve cross-account/portability gates as unverified until real evidence exists.

## New-chat prompt

```text
@TunnelVibemq5 @GitHub
Use Vibecode Kit v6 and YAGNI-3. Read docs/operations/TIP-045-CURRENT-CHECKPOINT.md first.
Continue the authorized pending-work completion, not the historical audit.
PR #47 and #15 are merged; main contains TIP-045 / 0.2.41.
Fixed MT5-2; latest observed terminal build 6230; catalog 79 server / 78 model tools.
The last Windows unit call returned HTTP 502 with no result; following health/runtime_status calls returned Internal error.
Recover connection and the original suite outcome before retrying.
Do not reset evidence, direct-commit main, expose secrets or change MT5 account/credentials/AutoTrading.
Use checkpoint + exact expected SHA/CAS for changes; use branch + PR.
Report current evidence separately from historical certification and account-specific UI gates.
Do not claim all pending work DONE while transport, soak, native qualification, target-chat acceptance or fresh-environment gates remain unresolved.
```
