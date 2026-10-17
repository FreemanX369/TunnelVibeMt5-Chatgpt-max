# TIP-081 — Deployed pilot reliability fixes

Source: `9d2f53764cf1a1dac5f3de1835484eede58db03e`, based on the accepted `745147f` Fleet source. Scope: the existing single-VPS control pilot and composed legacy85 + Fleet31 catalog. No native SDK qualification, account changes, trading, credential rotation, journal reset or new authority.

## YAGNI-3 and implementation

The fixes are required by the retained deep-test failures and fix1 predeploy failures. Reuse the existing journal validators, signed request builder, HTTPS client, MCP error boundary and explicit scheduled runner. Keep the wire schemas, authority checks and durable pending evidence. Add no new service or framework.

| AC | Observed defect | Required result |
|---|---|---|
| AC-01 | A request was signed before full history validation consumed its 5-second freshness window. | Validate and acquire the transaction before minting the exact proof; an expired deadline creates no new intent. |
| AC-02 | Node exceptions closed the shared gateway. | Bounded transient retries; permanent or exhausted errors fence the node while gateway remains independently alive. No automatic reset or restart. |
| AC-03 | Repeated full scans grew with the retained journal. | Reuse validation only at the exact validated SQLite/file/policy revision; invalidate on external or same-connection edits. Preserve full cold validation and every pending record. |
| AC-04 | MCP hid actionable failures. | Fixed safe codes with explicit retryability; never arbitrary exception strings, paths or credentials. Native serialization busy remains a truthful retryable result. |
| AC-05 | A late routed read killed control. | Keep the original deadline, failed status and independent witness; do not acknowledge or invent a successful effect. Continue heartbeats. |
| AC-06 | `localhost` connection waited on a non-listening address family while IPv4 gateway was idle. | Explicit operator loopback-family selection for the IPv4-only pilot, preserving signed origin, TLS SNI/hostname and CA verification. Remote or ambiguous targets must be rejected. |

## BUILD / VERIFY separation

Build changes are in `node_transport_journal.py`, `gateway_control.py`, `transport.py`, `fleet_mcp.py`, `pilot_runtime.py`, and `test_tip081_pilot_reliability.py`. Operator composition and runner files live with this release; the active legacy application files remain pinned to their original baseline.

Verify with the official Linux/Windows source workflows, targeted real-TLS and tamper regressions, synthetic journals at 1k/10k/50k records, retained live journal compatibility, protocol schema comparison, malformed typed inputs, three-client reads and mixed load, idempotent routed inventory, truthful unqualified denial, clean final guards and a bounded control soak. A profile switch requires accepted predeploy evidence. B/C additionally require acceptance of A. Record actual results separately in the completion report.

## Rollback and rejected attempts

The original integrated116 entry and its protected profile backups are retained. `bind-integrated-profile.py --instance X --mode rollback` accepts only the exact applied profile hash and restores the original bytes. Restore a scheduled action only after proving the current pilot stopped; never reset its keys, SQLite files, pending witnesses or qualification state. The original pre-fix pilot was stopped following its recorded failure; restoring its action does not establish that it is healthy.

Keep fix1 full-Windows timeout and TLS-fixture failures, failed 3-client initialization and failed/cancelled soak as evidence. They are not passing release gates. Fix2 is a separate immutable release path.
