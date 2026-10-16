# Single-VPS Fleet pilot — 16 October 2026

The isolated control/inventory pilot is deployed on the existing VPS. Full Fleet release remains unqualified. The ChatGPT Fleet plugin has not been created; its form is prepared for the action-time permission required by the browser's security-sensitive access rule.

Accepted application source: `745147f525caefbec66505e5cdb6a4fb7013c2d7`; APP89 and its separate93-file staged payload are unchanged. Operators are published separately on `ops/single-vps-provision-745147f-20261016`; no main merge or new source-CI claim.

## Current operation

- Pilot root: `C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a`.
- HTTPS gateway: `https://localhost:8443`, bound only to `127.0.0.1`; pilot TLS certificate lasts7days from16October. No certificate-verification bypass.
- Scheduled Task: `VibeMQL5-Fleet-Pilot-745147f`, RUNNING as the existing interactive Windows identity. It reopens existing journals with `--resume`; AtLogOn trigger, no password change and no automatic restart. A reboot without Windows logon has not been qualified.
- Device: `dev_e488e5a0105847febf7ed46c9e15e9d0`, route1, session `pilot-745147f-20261016-a`. Five terminal identities belong to this one VPS.
- TunnelA/B retain the legacy85 catalog. TunnelC now targets `operator-fleet-mcp.py` and separately serves Fleet31. Its tunnelID is `tunnel_6ab364eabc8c8191b66b96b9d7e9ad0b`; health/ready200 with one process. The existing A app remains `TunnelVibemq5`.
- Prepared new ChatGPT plugin: `TunnelVibemq5 Fleet Pilot`, TunnelC, no extra OAuth for stdio (control-plane tunnel access still applies). Final create has not been clicked.

## Actual verification

| Acceptance | Evidence |
|---|---|
| Windows protected provisioning | PSHELL-20261016-131059-2DA0A20C, nine protected TLS/key/token/config files; private values never printed |
| Pair + heartbeat | STARTUP receipt at06:16:54UTC, ACTIVE route1 |
| Actual stdioMCP31 | PSHELL-20261016-131836-607B0A63; exact catalog and real calls |
| Routed inventory | `dcmd_6af727b8db384e78892ebf37a912e0e2` COMPLETED, five identities |
| Idempotent replay across reopen | Same original operation/command/result after normal reopen; PSHELL-20261016-132351-D1B87A4C |
| Fresh post-reopen command | `dcmd_47c871ac0f9347908571be85d4463474` COMPLETED, five rows at06:24:41UTC |
| Qualification denial | `read_2258435877ac4d828029f725388dce24` FAILED with `LIVE_ATTACH_ONLY_UNPROVEN`; expected boundary, no qualified live read claim |
| Graceful stop | PSHELL-20261016-132250-570250D0; runtime2604 STOPPED and8443 listener gone; no force kill |
| Persistent reopen | PSHELL-20261016-132332-4F3AC474; taskRUNNING, new runtime5660 owns127.0.0.1:8443 |
| TunnelC switch | Protected originalprofile retained, exact one-command replacement; BADMIN-20261016-132825-987FC8FB restartREADY |
| Exact tunnel entryMCP | PSHELL-20261016-133019-37B91F90;31tools and ACTIVEdevice |
| Tunnel doctor | PSHELL-20261016-132948-8328B8AF PASS using ephemeral diagnostic port; stdio network probe explicitly SKIP |

Verification is performed by the same assistant with tools, not independent review of the new operator scripts. Earlier source-CI/R05/R06 acceptance is unchanged.

## Retained deviations

First gateway startup failed before any grant/pair: the example journal payload1MiB exceeds the journal implementation's256KiB maximum. It created only an empty control store. The explicit recovery verified revision1 with zero devices/grants/nonces/operations, preserved that store, retained protected originalconfigs, changed only gateway/node journal payload to262144, and initialized only absent ancillary journals. Original failure and repair receipts remain. No ledger deletion, replacement or new identity/session was used. Future provisioning is corrected on the operator branch; original staged templates/application remain exact745.

The first tunnel doctor failed only because its diagnostic health bind collided with the already-running8082 listener. The next call used an ephemeral health port and passed; it did not restart or alter live listener configuration. An early read-denial polling harness used `state` instead of `status` and observed onlyPENDING; follow-up polled the same original command to its actual terminal denial, without resubmission.

## Final test and stop

After plugin creation, select the new Fleet plugin in a fresh turn and call `fleet_server_info`, then `fleet_inventory`. For fresh terminal inventory, submit exact device/route with a new operationID and poll `fleet_command_status`. Cached inventory alone does not prove terminal connection or SDK readiness. Existing six core tools can still be tested through `@TunnelVibemq5`.

For local repeatable smoke on VPS:

```powershell
& 'C:\VibeMQL5\.venv\Scripts\python.exe' 'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a\operator-verify-pilot.py'
```

For graceful pilot stop, create `runtime\STOP` and wait for the matching currentPID's `STOP-RECEIPT.json` with STOPPED. Preserve all journals, keys and receipts. Do not use Stop-ScheduledTask/force kill as a normal stop. A normal reopen archives/removes only the explicit stop signal and starts the existing task; do not use initialize/pair flags again.

The protected original tunnelC YAML is retained at `runtime\secrets\tunnel-c-profile.before-fleet.yaml`. Rollback requires exact current profile hash `0b56e8a9ec8c19e9cd66a62ad1f0409c5c5aa64677db4f51091d998f54d7127d`, restoration of that exact original profile and a bounded C restart. Never restore older live authority journals as part of source rollback.

## Remaining release limits

ChatGPT plugin registration/discovery and direct model-call exposure are PENDING. Actual SDK/no-start qualification, live routed reads, native jobs, writer/worktree authority, capacityQ2, multi-VPS rollout and full restore/soak acceptance are NOT_RUN/NOT_QUALIFIED. No marker is fabricated from source CI. Journal retention is finite and fail-closed; the pilot is not qualified for unattended long-term production. MT5 accounts, credentials and AutoTrading remain unchanged.
