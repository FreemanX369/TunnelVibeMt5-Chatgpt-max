# TIP-063 — Registered worktree source and operator contract

Status: source prepared and tested with disposable Git repositories, signed principals and verified local HTTPS. This creates isolated source commits; it does not merge them, update the authoritative node project session, qualify native jobs or activate an SDK installation. Physical fleet/client testing remains deferred.

## Configuration and startup

Use the existing explicit fleet node startup. `writer_policy` must be configured and the node must have a paired key, current route/session, gateway public key and registered node-owned project. The gateway provisions the client principal and project assignment through its existing owner-only principal routes. Caller agent names, MCP metadata and worktree identifiers never grant writer authority.

The node configuration adds two required-together fields: `worktree_policy` and `worktree_config`. Set both to `null` to disable worktrees. Enabling them requires every numeric policy field; the values below are an explicitly selected disposable source-test profile, not production defaults:

```json
{
  "worktree_policy": {
    "max_worktrees": 10,
    "max_operations": 50,
    "max_changes": 8,
    "max_change_bytes": 32768,
    "max_payload_bytes": 1048576,
    "max_git_output_bytes": 131072,
    "git_timeout_ms": 5000,
    "wait_ms": 50
  },
  "worktree_config": {
    "repositories": {
      "P": {
        "repository": "<absolute existing registered repository>",
        "base_commit": "<existing lower-case 40-hex SHA1 commit>",
        "source_paths": ["Experts/DemoEA.mq5"]
      }
    },
    "worktree_root": "<absolute separate canonical owner worktree root>",
    "git_executable": "<absolute trusted Git executable file>"
  }
}
```

Replace all placeholders locally. Repository, worktree root and executable are operator configuration; request payloads cannot supply or override them. Roots must be absolute and canonical without symlink/reparse ancestors. Worktree roots cannot overlap repositories or control state. Repositories are existing non-bare main checkouts with a real `.git` directory. Each allowed source path must already be a regular tracked file at the configured baseline. The project session's actual EA bytes and checkpoint must match that baseline before a worktree is prepared. The main checkout must remain clean and at that baseline.

Keep node configuration, gateway trust, principal private keys and owner credentials out of repositories and clone packs. This implementation fixes Git hooks, fsmonitor, signing and automatic maintenance off; disables system/global Git configuration; rejects repository include/includeIf/worktree-config, filters, grafts, alternates, external attributes, symlink baseline entries and submodules. The fixed disabled-hooks directory must remain empty. It never fetches from a remote, invokes a shell command supplied by a client, loads submodules or runs a configured filter. Git root/common-directory observations and NUL-porcelain worktree paths are parsed as canonical native paths, so Windows slash and drive-case spelling cannot bypass or falsely fail the registered-root comparison. Malformed or warning-contaminated listings cannot prove retired absence.

Start the already configured gateway separately. Node/client construction does not create a gateway. On a fresh disposable configured node, initialize the node stores once:

```bash
python -m vibemql5.adapters.fleet_cli --config <node-config.json> node --initialize
```

Reopen existing stores without `--initialize`. The worktree journal binds the registered roots, frozen baselines, limits and node/gateway identity. Mismatched configuration fails closed. Do not delete/reinitialize a journal or edit its configuration to abandon an unknown operation, change owner or silently advance a baseline. This source version has no automatic baseline migration, branch merge or unknown-owner reclamation.

In a trusted in-process node composition, instantiate `NodeWorktrees(root, principals=runtime, repositories=..., worktree_root=..., git_executable=..., policy=WorktreePolicy(...), initialize=False)` and call `runtime.bind_worktrees(store)`. The existing `NodeRuntime` configuration does this and closes resources in reverse order. `local_path()` is owner-side inspection; no HTTP filesystem selector is exposed.

## Finite request contract

Use the existing configured principal client:

```bash
python -m vibemql5.adapters.fleet_cli --config <principal-client-config.json> client worktrees/prepare --request-file <prepare-request.json>
```

A client request file has `{node, operation_id, payload}`. `node` contains the current device and route. The gateway signs and binds the complete logical request to the exact principal/session/assignment/writer epochs; the outbound node verifies that evidence and asks the gateway for a fresh phase proof. Use `worktrees/commit` and `worktrees/retire` with the same outer shape.

| Operation | Exact payload fields |
| --- | --- |
| Prepare | `project_id`, `worktree_id`, `base_commit` |
| Commit | `project_id`, `worktree_id`, `expected_head`, `changes`, `message`, `source_ref`, `result_ref` |
| Retire | `project_id`, `worktree_id`, `expected_head` |

Worktree identifiers are bounded simple references without separators; the actual path is derived from the registered root and project. A commit change is exactly `{path, expected_sha256, sha256, source_base64}`. Paths are registered relative tracked source paths only. Expected SHA256 binds the actual prior bytes; base64 and SHA256 bind the frozen replacement. For a deletion both replacement fields are `null`; the prior file must exist. Recreating a previously committed deletion uses `expected_sha256=null`. All changes share the required byte/count budgets and at least one change must alter bytes. Control/configuration/key paths, traversal, case-duplicate paths and symlink sources are refused.

`message` is a bounded single line. The implementation adds exact intent and owner trailers to the Git commit. `expected_head` must match both the durable worktree head and actual Git HEAD. The worktree must have no staged, modified, untracked or ignored files before commit/retirement. Staged paths and blobs are checked against the frozen change list before the commit.

`source_ref` is the exact existing node project session projection returned by the project API: `revision_id`, `revision_sha256`, `workspace`, `ea`, `checkpoint_id`, `source_sha256`, `source_bytes`. Its current revision/checkpoint/live bytes are revalidated under the shared source guard. A worktree commit does not change that main source or session. An optional `result_ref` is exactly `{reference, sha256}` and is explicitly returned as `UNVERIFIED_REFERENCE_ONLY`; it cannot assert artifact/native/SDK success. Use `null` when no external task reference is needed. Continuity remains the semantic task history; this journal records concrete Git effects and ownership only.

## Recovery and failure handling

The worktree journal persists the signed original request and intent before a Git mutation. Each mutating Git step records ATTEMPTED before launch and CLOSED only after the exact retained process wait, output-reader completion and pipe closure. The durable CLOSED receipt binds operation/phase/intent, fixed argv/purpose and observed head/tree before post-effect fault points. The existing writer phase records the exact issued authorization before file effects. Fresh phase checks run before each file effect, staging, tree creation and commit. Gateway revocation, expired proof, dirty bytes or HEAD drift prevents the next effect and retains the original unknown operation.

Git output and process duration are bounded. A timeout is an uncertain outcome, not proof that a worktree is safe to delete. There is no TTL reclaim, force removal, checkout reset, rollback inference or successor adoption.

Replay the exact original admitted command after reopening the same journals and authority. Recovery performs read-only Git observation under the same source guard. It requires every issued Git step and the final matching effect to have a durable CLOSED completion receipt. A parent crash or failed closure publication leaves UNKNOWN even if Git later produces the expected HEAD; filesystem state alone cannot establish producer closure. It may acknowledge only an already completed original create/remove, or a clean commit whose parent, tree, message, intent and owner match the durable journal. It never repeats file writes, staging or Git commit. Completed receipts remain immutable on later replay even after subsequent commits or retirement.

A partial file write, dirty tree, missing provenance, changed head or changed request remains blocked. Keep the old journal, assignment and writer phase records. Operator revoke/drain does not authorize a new owner to finish that worktree; unresolved outcomes stay pending until concrete original-effect reconciliation is available. The implementation exposes no generic cleanup/admin shell to bypass this boundary.

Keep gateway principal/assignment/phase journals and node writer/worktree journals with the existing coordinated recovery checkpoint. Store Git objects and worktree metadata alongside node-owned repositories; restoring only a receipt or copying another installation's metadata cannot establish the original owner. Later physical tests should exercise two assigned clients, network loss and process interruption on the final source candidate before production use.

A configured worktree store contributes `recovery_head()` to the existing node principal witness. This bounded read-only projection binds the full durable journal digest, signed original command/request/owner/receipt hashes and every closed Git step. It rechecks the registered clean main baseline, actual clean active worktree heads, retired absence and linear original commit history. Unknown, attempted, unclosed, dirty or inconsistent worktrees refuse a quiescent head even if a writer phase was marked committed. Disabled worktrees contribute explicit `null`. The retained operator checkpoint and freshly signed node witness must match this exact configured head before joint restore clears all journals.
