# TIP-038: Read-only tunnel poll diagnostics

Call `tunnel_admin_status(instance="all")` to inspect A, B and C on the Windows VPS. Each instance now includes `poll_diagnostics`, sourced from its own loopback tunnel-client `/api/logs` endpoint. `instance="A"`, `"B"`, or `"C"` narrows the report.

The response includes the oldest and newest retained log timestamps, total retained poll failures, and up to 32 recent failure episodes. An episode begins at `poll failed; backing off` or `poll timed out; backing off` and ends at `poller recovered; polling operational`. It contains failure count, first and last failure timestamps, optional recovery timestamp, bounded retry/timeout values and a finite error category such as `AWAITING_HEADERS_TIMEOUT`, `PROXY`, `DNS`, or `HTTP_403`.

Compare overlapping episode timestamps across A/B/C before attributing an outage to one instance. When `oldest_event_at` is later than the incident, zero failures cannot rule out earlier failures. `poll_diagnostics.status=UNAVAILABLE` means the local logs could not be read; the existing process, task, `/healthz`, and `/readyz` fields remain available.

The endpoint address is constructed from the fixed A/B/C instance table and always connects to `127.0.0.1`; no arbitrary URL or PowerShell text is accepted. Raw log messages, URLs and credentials are never returned. The existing PowerShell-backed process and Scheduled Task checks remain unchanged, and the MCP tool name, arguments, catalog and build label remain unchanged. Restart the bridge's stdio child for a deployed change to take effect.
