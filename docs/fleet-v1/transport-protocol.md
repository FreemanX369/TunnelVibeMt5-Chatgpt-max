# Fleet wire, transport and read contract

This is a source protocol, not a qualified deployment profile. The gateway endpoint, TLS certificate/CA, private-key locations and every policy value are explicit operator configuration. Private VM/SDK/MT5 acceptance is deferred by the owner. The existing 85-tool legacy catalog remains separate from the opt-in fleet client.

## Signed node request

Requests use POST, an exact listed path, UTF-8 JSON and six headers: `x-vibe-device`, `x-vibe-key`, `x-vibe-route`, `x-vibe-time`, `x-vibe-nonce`, `x-vibe-signature`. The public key is 32 bytes represented by 64 lowercase hex characters; signature is 64 bytes represented by 128 lowercase hex characters. Device IDs are persisted `dev_` plus 32 hex characters. Route/time are canonical unsigned decimal integers bounded by signed 64-bit range; route zero is permitted only for initial pair wire projection. Nonces are 32–128 lowercase hex characters. Duplicate/unknown `x-vibe-` headers, duplicate JSON keys, malformed Unicode, nonfinite/oversized numbers, unsupported fields, URL query/path aliases and oversized bodies are denied.

Ed25519 signs these ASCII lines, each terminated by LF:

```
fleet.wire/1
POST
<exact path>
<SHA256 of exact transmitted body bytes>
<device ID>
<public key hex>
<route generation>
<timestamp milliseconds>
<nonce>
<configured canonical HTTPS origin>
```

The HTTPS audience has no credentials, path, query or fragment. It is lowercase/canonical and includes a non-default port when applicable. A valid request for one audience fails verification at another. Parsed projections are fresh copies of sealed immutable transmitted bytes. The seal is an internal process trust boundary; a deserialized `verified=true` or caller `agent_id` has no authority.

Logical operation identity uses the domain request and excludes the transport nonce/timestamp. Every signed retry consumes a fresh persistent nonce. Pair consumes the exact grant-bound key/route, nonce and logical receipt atomically. The initial wire route zero is historical pairing evidence; it is never an active enrolled route. Revoke/re-pair/rotation fence old routes/keys. Admin operation IDs use `admin:`; pair operation IDs use `nodepair:`.

| Signed path | Bound domain purpose |
|---|---|
| `/fleet/v1/pair` | Single-use expiring pairing grant and durable logical pair receipt |
| `/fleet/v1/heartbeat` | Installation session transport presence; not SDK/runtime evidence |
| `/fleet/v1/poll` | Bounded typed node commands in signed `WORKLOAD` or `CANCEL_ONLY` mode |
| `/fleet/v1/results` | Exact read/native/domain result commitment |
| `/fleet/v1/read-authorize` | Still-pending delivered read command, session, target, digest and deadline |
| `/fleet/v1/native/start` | Fresh signed native effect authority; exact job/target/session/phase/event/sequence/challenge, predecessor completion receipt and nullable observed process digest |
| `/fleet/v1/writers/authorize` | Exact authenticated principal/assignment/writer phase and intent |
| `/fleet/v1/capacity/register` | Verified operator-signed scoped capacity roster and bound load/closure receipts; no heartbeat claim |
| `/fleet/v1/jobs/recovery-witness` | Read-only challenge-bound historical known terminal receipt; original job/UNKNOWN/capacity remains unchanged |
| `/fleet/v1/reconcile` | Dedicated fenced restore witness; never normal dispatch |

Owner and principal operations have separate finite paths and authentication. Owner credentials use a configured token digest checked in constant time over verified HTTPS. Principal paths are composed by the explicit principal authority; caller metadata does not authenticate an agent. Public response errors are codes and never raw SQLite, SDK, path or secret diagnostics.

The finite owner `/fleet/v1/principals/reconcile` produces an internal queued `SOURCE` command `/fleet/v1/writers/reconcile` to complete only an approved original `session_commit` intent after a partial source commit. This command is not a client principal HTTP route. `/writers/authorize` retains optional bounded prior `phase_acks` and exact `{body,signature}` `drain_approval`; authority checks the signed persisted approval and original epochs/intent. These fields cannot authorize a new source effect, replacement owner or force clear.

## Event owner and node control loop

`serve_gateway` is explicitly started once. Its factory runs on the sole event owner that holds the gateway store. Client/MCP processes do not start a server or open the control writer. TLS CA and hostname verification are required at every client request; there is no insecure option. Redirects and arbitrary URLs are unsupported.

Operator startup builds the server context from retained validated bounded certificate/key bytes through protected staging, then passes a trusted exact `SSLContext` with `PROTOCOL_TLS_SERVER` and minimum TLS 1.2. This is an internal startup object, never a wire/config dictionary. The server consumes the prepared identity without reopening the original key/certificate paths. Explicit-path startup remains available for labeled fixtures. Windows staging uses a held directory checked on the retained handle, current/SYSTEM protected ownership and no delete sharing; the handle stays open through TLS loading. Client CA contexts use the validated retained bytes.

A single total monotonic HTTP budget covers accepted TLS handshake, fragmented request headers, body and response. Client budgets cover connect/TLS, fragmented response headers/body and caller aggregate deadlines. Body/response limits are required policy. Standard library header count/line limits remain fixed parser ceilings. Policies also require polling/heartbeat intervals, session expiry, queue/history/fan-out/row/operation-token bounds, observation freshness and clock tolerance; fixed implementation ceilings are not deployment defaults.

Concurrent active sessions for one device/route conflict. A normal same-session reconnect does not change the route. Transport expiry never kills a native process. Copied key material cannot prove physical machine uniqueness.

The outbound node serializes complete read lifecycles. Cached commands/results preserve callback-once behavior across lost result ACKs; changed repeats conflict. Qualified SDK entry additionally requires a sealed `NodeReadAdmission` issued from an actual authenticated poll delivery, exact device/route/session and current `/read-authorize` check. Gateway restart, completed command, stale route/session and elapsed deadline deny entry. The installed SDK capability remains separately sealed/operator-qualified; a routed target cannot activate a legacy local fallback.

Native/cancel/source/worktree callbacks use the composed bounded async dispatcher. Their finite authority/result RPC requests pass through `NodeRpcProxy` to the control owner so heartbeat/poll continue while an effect is blocked. The owner alone writes the transport journal and makes the authoritative HTTPS request. Each node step sends heartbeat first, services one RPC round, then drains one bounded result round. RPC HTTPS requests borrow the earlier of their original queue deadline and one heartbeat-interval round budget; remaining queued requests retain their original deadlines. An expired request is skipped before issuing authority. Native requests retain the exact finite event and predecessor completion receipt rather than inventing progress from a timeout. No generic shell, path/RPC callback or SQL callback is exposed.

Native cancel/termination authority additionally binds the current exact observed process digest; other requests explicitly carry null. The control owner flushes the current job progress and waits for its ACK before requesting process-bound authority. Missing progress, lost ACK or an elapsed shared deadline denies authority; the gateway separately checks the durable observed process digest.

The trusted `OutboundNode.step(poll_commands=False)` stop lane keeps heartbeat, queued authority RPC and result drain running. Its signed `fleet.poll/1` mode `CANCEL_ONLY` receives only explicit owner cancellation of an already admitted exact job/process; the gateway skips reads and new native/source/worktree workload, and the node rejects every non-cancel response before dispatch. Normal polling uses `WORKLOAD`; mode is required and echoed in the receipt. Stop does not automatically kill a process, expire an uncertain effect, release an active journal or promise a hard exit. The configured runtime reports `STOP_PENDING` and continues this lane when workers/processes/results remain unresolved. Historical recovery uses a finite `NATIVE_RECOVERY` command and signed node witness after explicit owner `/jobs/recover`; it never restarts the historical native effect.

## Observation and snapshot

Read commands freeze exact `fleet.target/1`, operation, request digest and deadline. Only terminal state and account snapshot are automatic reads. Gateway accepts successful observations only with exact requested/resolved target, bounded current time, the six legacy terminal fields, the 21 legacy account fields, masked login, exact executable/data-root/process binding and `PROVEN` cleanup/`CLOSED` ownership. Unknown fields, raw login, secret fields, nonfinite values and unproven closure fail. The production broker rejects `SYNTHETIC_TEST`; the explicit test factory exercises positive routing with that label.

Results remain attributable to their device/route/session/command/digest. Identical commits recover the same receipt; changed/cross-node/stale/late results never become current successes. Gateway read state is ephemeral because it describes observations; restart returns `READ_INTERRUPTED`. Durable native effects use the separate domain journal.

Snapshots use bounded fan-out and one total deadline. Rows contain exact target, source/time/age/freshness/status/reason and nullable account/terminal data. Coverage states requested/succeeded/failed. Disconnected/unavailable accounts are null; a partial snapshot is useful and explicitly non-atomic. No monetary totals, account deduplication guesses, FX, charts/rates/ticks or automatic capture occur.

## Private keys and independent transport witness

Node keys are explicit fresh Ed25519 PKCS8 files under a `secrets` directory. Creation is exclusive and never overwrites an existing key. POSIX files are 0600 with an owned restrictive parent; Windows creation uses an exclusive retained handle with explicit `WRITE_OWNER`/`WRITE_DAC` to assign the current identity and a protected DACL for that identity and SYSTEM before private bytes. Loading queries owner and DACL together on the opened handle: owner must be the current identity or SYSTEM, with the exact protected identity/SYSTEM DACL. Reparse/symlink/hard-link ambiguity fails. Git excludes `secrets/`; private keys must also be excluded from machine backups/clone images by the operator. Public-only creation receipts and silent HTTP logging avoid key disclosure.

`NodeTransportJournal` is initialized/opened explicitly with its own persistent path and required policy. It commits exact nonce, audience, device/key, path, route, time and body/request hashes before outbound HTTPS. It never persists the body, grant secret or private key. A matching validated TLS response records its response digest and exact gateway control head. Missing/lost/rejected responses remain pending across restart and later successful requests; timeouts do not erase them. Capacity fails rather than evicting uncertain requests.

Interrupted initial pairing may reuse an existing transport journal only before other authority stores exist. The readonly `assert_pair_replay(body, signed_route_generation=...)` requires a nonempty validated history containing only `/fleet/v1/pair` intents with the exact `fleet.pair/1` body hash and configured pre-pair route. Journal device/key/audience must still match its original identity. Changed grant, secret, operation, revision, route or any mixed request history denies replay. The helper performs no admission or journal mutation; the subsequent fresh signed retry recovers the gateway's original logical pair receipt and preserves all old pending intents.

Challenge-bound signed recovery witnesses report journal digest, pending count and latest ordinary control head. Recovery-envelope ACKs do not advance the ordinary live head. The gateway restore coordinator separately validates the exact backup anchor, owner checkpoint, node registry/session and domain job witnesses. Missing/newer/pending witnesses remain fenced; DB-only anti-rollback and instant cancellation/revocation are not claimed.

Windows API implementation references: [SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo), [file access rights](https://learn.microsoft.com/en-us/windows/win32/fileio/file-security-and-access-rights), [CreateFile](https://learn.microsoft.com/en-us/windows/win32/fileio/creating-and-opening-files). Source tests and later Windows/physical acceptance establish the actual supported scope.
