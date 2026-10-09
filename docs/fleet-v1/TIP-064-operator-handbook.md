# TIP-064 operator handbook

This source update provides an explicitly started HTTPS gateway, outbound nodes, a finite CLI and a separate optional fleet MCP client. The legacy 85-tool server stays separate. Source fixtures do not qualify a Windows host, MT5 installation, SDK payload, account or physical capacity profile. Run the deployment-specific VM/SDK acceptance after the complete source candidate is handed over.

## Configuration and authority

Copy and replace every placeholder in `config/gateway.example.json`, `config/client.example.json`, `config/principal-client.example.json`, `config/node-readonly.example.json` or `config/node-writer.example.json`. Templates are examples, not ready-to-run installations. Configure absolute paths, one exact HTTPS origin and the corresponding certificate hostname. Create the authority/database parent directories explicitly. Every required limit is supplied in the configuration; no hardware profile is inferred from RAM, heartbeat or caller labels.

Startup configuration, selected CA certificates, TLS certificate/key, owner bearer and private Ed25519 keys belong in an operator-owned directory named `secrets`. On POSIX the directory is mode 0700 and the files mode 0600, owned by the running identity. Windows uses the current user or SYSTEM owner and the exact protected ACL accepted by `fleet.node_keys`; inherited permissive ACLs, reparse points, symlinks and hardlinks are rejected. Provision protected Windows files through the supported exclusive retained-handle creation helper, which requests WRITE_OWNER and WRITE_DAC before writing bytes. Do not set that ACL using an ordinary Python file handle. Do not copy private keys, enrollment identity or journals into a cloned node.

The CA is loaded from validated retained bytes into an SSL context. Gateway TLS also loads validated bytes through a fresh protected staging directory: Windows retains a directory handle against rename/delete until the context owns the key. Temporary private files are removed before serving. HTTPS keeps hostname and CA verification enabled.

| Configuration | Authority available |
| --- | --- |
| Owner client, `owner_token_file` set | Inventory, routed reads/snapshots, project/job/artifact requests, control grants and principal provisioning |
| Principal client, owner token null, protected possession key plus public gateway-issued credential | Only assigned writer/source/worktree scopes verified on every request |
| Read-only node, writer/worktree policy null | Inventory, configured qualified reads, durable native journal access and quarantined historical recovery; no writer authority is opened |
| Writer node | Same exact node route/session plus node-owned writer and optional registered worktree authority |

A principal process receives no owner bearer. Owner-only client calls fail locally with `OWNER_CREDENTIAL_REQUIRED`. Its public signed certificate does not replace private-key possession. MCP agent names and caller metadata do not authenticate a client. `fleet_server_info` reports configured authority modes and the actual optional tool catalog.

## Start and pair

Use Python 3.12 and the candidate's locked verification dependencies. The application dependency declarations remain in `pyproject.toml`. Keep the local terminal configuration, project sessions, source/checkpoints, job history and Continuity in the existing node root.

Bootstrap local identity through the existing finite command after reviewing configured terminal executable/data bindings:

```sh
python -m vibemql5.adapters.cli --root /srv/vibemql5-node identity-bootstrap
python -m vibemql5.adapters.cli --root /srv/vibemql5-node identity-show
```

Generate/provision protected Ed25519 keys explicitly with `fleet.node_keys.create_node_key`; no startup command creates or substitutes one. Provision the owner bearer and matching HTTPS certificate/key separately. The exact gateway authority public key goes in the node configuration.

Start the single gateway authority:

```sh
python -m vibemql5.adapters.fleet_cli --config /srv/fleet/secrets/gateway.json gateway --initialize
```

Use `gateway` without `--initialize` on normal reopen. Initialize only absent authority files. A second authority owner is refused by lifetime locks. Opening a fleet CLI/MCP client never starts or initializes a gateway.

Use the owner client `admin/grant` request to admit the existing device ID and protected node public key with exact control revision and expected route. Save the returned initial grant secret in a protected pair file; never include it in chat logs, diagnostics or a reusable template. Its exact shape is `fleet.pair/1` with `grant_id`, `secret`, `operation_id` and `expected_revision`.

```sh
python -m vibemql5.adapters.fleet_cli --config /srv/fleet/secrets/owner-client.json client admin/grant --request-file /srv/fleet/requests/grant.json
python -m vibemql5.adapters.fleet_cli --config /srv/fleet/secrets/node.json node --initialize --pair-file /srv/fleet/secrets/pair.json
```

The configured node route is the intended admitted generation. Pairing signs generation minus one, persists the transport intent first and requires the resulting route to match. Heartbeat is authenticated before command dispatch. Normal reopen uses `node` without initialization or a pair flag. `--once` performs one admission cycle then drains all admitted work before closing.

A lost pairing ACK preserves PENDING transport evidence. Reuse the exact same grant, operation and revision only if the compatible transport journal is the only initialized journal; it never creates a second logical pair. Changed pairing input or mixed initialized authority is refused. On `FLEET_INITIALIZATION_PARTIAL`, retain all files and evidence, revoke/quarantine the admitted device through the owner authority and use the supported fenced recovery process. Do not delete/reinitialize files, clear PENDING or assign a new session to old writer authority to make initialization succeed.

## Read and operate

```sh
python -m vibemql5.adapters.fleet_cli --config /srv/fleet/secrets/owner-client.json client inventory --request-file /srv/fleet/requests/inventory.json
python -m vibemql5.adapters.fleet_mcp --config /srv/fleet/secrets/principal-client.json
```

An empty inventory request returns attributed gateway control cache. A request containing `{node, operation_id}` discovers terminal targets through a signed outbound node command. Review identity conflicts and exact IDs/generations before reads or freezes. Inventory does not observe SDK readiness, terminal connection or live account state. A legacy positive routed target remains denied even when a local SDK manifest is installed.

Finite CLI operations are listed by `client --help`. Domain operations use `{node, operation_id, payload}`. Durable request IDs replay the exact original operation; changed payload conflicts. Projects are created/read/enrolled/frozen on the node through existing project-session/checkpoint APIs. The gateway stores references and command receipts, never a second mutable project history. Frozen target and session hashes remain fixed when a default target changes.

Native launch takes `fleet.native/1`: an exact frozen placement, normalized logical config, nonempty verified input manifest and STRICT build policy. Production native effects require installed signed qualification, owned leases and fresh signed phase/effect proofs. Uninstalled nodes return a durable qualification denial without a native attempt. Worker capacity defaults to one. Higher capacity requires an installed operator-signed full-resource profile and exact measured load/closure receipts, freshly verified locally and registered over authenticated HTTPS before higher-slot dispatch. Configure the same current owner public key at gateway reopen; persisted roster bytes are reverified against it.

Native workers are bounded and run beside the outbound heartbeat/status loop. Each phase/effect uses a durable intent and exact sequence/challenge; completed predecessor evidence is required before a different next step. Expired or lost grants cannot be renewed into a second start. Cancel uses the exact current PID/creation/image receipt and a fresh signed grant after progress was acknowledged. Heartbeat or grant expiry never kills a native process.

Artifacts use registered immutable IDs plus exact global job/local job/frozen target/SHA scope. Fetch bounded chunks and verify offsets, SHA and final manifest size/hash. No artifact route accepts an arbitrary filesystem path or invokes native `get_job`.

Owner provisioning issues a signed principal certificate for the client's protected public key and finite scopes, then assigns a project/target/writer epoch. Writers check the current assignment again before source and session commits. Revoke, voluntary release and owner release install DRAINING fences; outstanding phases must be reconciled before replacement ownership. There is no TTL reassignment. An approved `principals/reconcile` request permits only the original incomplete session commit from the recorded source bytes; it cannot write new source or adopt another writer's intent. Original UNKNOWN domain receipts stay immutable. Only an exact completed reconciliation in the same journal can contribute a verified resolution to a quiescent recovery head.

Registered Git worktrees require the writer-node template's explicit repository, base commit, tracked source allowlist, separate worktree root and Git executable. Client DTOs contain no repository/executable/shell selection. See `TIP-063-worktrees-operator.md` for exact prepare/commit/retire payloads and recovery boundaries. Result references are explicitly unverified source references, never physical test evidence.

## Stop, history and restore

SIGINT/SIGTERM stops new workload admission. The owner loop keeps heartbeats, queued phase requests, progress and final result ACKs running. A finite cancel-only lane admits an exact operator cancel for an already admitted active job. New reads, native starts, source and worktree commands remain queued. At the configured drain deadline the agent reports `STOP_PENDING` and keeps servicing control; it does not kill work, clear unknown authority or claim closed. Quiet completion closes resources in reverse order. Retained OS handles or a lost final ACK keep stop pending. Metadata-only durable UNKNOWN exclusions remain preserved even after the process has no retained work.

After an explicitly admitted replacement route/session, a read-only node configuration can leave old writer/worktree policies null. This preserves their files and opens no stale writer authority. The owner `jobs/recover` operation binds the original global job to the current same device/route/session. The node supplies a signed complete terminal journal/closure witness with no pending effect or cancel. The returned reference is `HISTORICAL_QUARANTINED`; the original job, target, UNKNOWN/capacity fence and original session stay unchanged. No execution or cancel occurs through this path. Unresolved or incomplete historical evidence remains refused.

Backups and restoration use the supported `GatewayControlStore.backup/restore`, `GatewayJobJournal.backup/restore_backup` and `RestoreCoordinator` APIs; copying SQLite files while live is not a backup protocol. Retain node identity, transport, native, domain, writer and configured worktree journals and Git objects. Keep an independent canonical `fleet.quiescent-checkpoint/1` outside restored-store parents, binding control ledger, complete fleet, job mappings and configured domain/principal/worktree heads. Operator approval is Ed25519 signed and bound to checkpoint SHA, challenge, origin and time.

A restored gateway stays fenced until all configured readiness checks and exact freshly signed node transport/job/domain/principal/worktree witnesses agree with the independent checkpoint. Lost ACK, newer control anchor, missing node history, dirty worktree, unresolved phase or mismatched key/route/session prevents readiness. There is no boolean clear. Use the accepted scoped reconciliation APIs and preserve failed/superseded receipts. Do not advertise physical readiness from a source-only recovery PASS.

The reopened node accepts `--reconcile-file` containing a protected `fleet.node-recovery-input/1` document with `coordination_sha256`, `joint_scope` from `RestoreCoordinator.scope()` and `job_scope` from the prepared gateway job journal's `restore_state()`. It rechecks the exact origin, coordination digest, local identity SHA, key, route, session, challenge and fleet/export scope, then builds witnesses from its actual local journals before persisting the current outbound intent. A configured writer supplies its persisted phase/assignment/worktree witness. A never-writer node can supply a typed empty-absence witness only when all writer/worktree authority data and markers are absent, the checkpoint worktree head is null and the gateway has no corresponding assignment, phase or command history. Stale disabled writer files still refuse recovery.

```sh
python -m vibemql5.adapters.fleet_cli --config /srv/fleet/secrets/node.json node --reconcile-file /srv/fleet/secrets/recovery-input.json
```

Installed SDK selection uses a bounded `sdk_qualifications` list of `{manifest_file, operator_public_key, payload_manifest_file}` entries. Each entry must produce a sealed qualified installation; one adapter selects the exact target among at most 16 approved bindings. `capacity_trust` is null until the installed scoped coordinator is qualified, then contains explicit `trusted_owner_public_key`, `candidate_sha256` and `runtime_sha256`. A fixture marker, caller target flag or heartbeat resource claim cannot select either capability.

## Verify this candidate

The `verify-fleet-v1.yml` workflow checks the exact PR head on Linux and Windows. `tests/proofs/fleet_v1/run_source.py` captures the source manifest, complete unit JUnit/logs and retained harmless Q1/G03A/B1 evidence. The manifest includes Python, workflows, project/dependency locks and operator templates; before/after changes fail qualification. Platform skips are explicitly reported. A harmless Windows process fixture is separate from an MT5/SDK physical qualification.

The full-unit harness budget is 600 seconds; each required proof has 120 seconds. The workflow remains bounded to 20 minutes. Verbose unit IDs, per-test 90-second fault dumps, slowest-test durations and per-case timeout/elapsed fields identify a stalled case. These are source verification budgets; they do not change runtime request, stop or authority deadlines.

After the complete source build, test the exact handed-over commit on the private VM: enrollment/clone exclusions; CA/key/ACL startup; inventory/read/qualification denial then actual installed SDK paths; STRICT frozen source; one-slot native ownership and signed phases; explicit cancel and lost ACK; verified two-slot resource/load/closure roster; principal-only write/revoke/drain and isolated worktrees; immutable artifacts; complete and deliberately incomplete restores. Keep the final commit/hash and all logs/receipts. Roll back source/config to the retained candidate without replacing current authority journals with old unfenced copies.
