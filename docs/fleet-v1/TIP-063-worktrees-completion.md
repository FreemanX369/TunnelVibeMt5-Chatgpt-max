# TIP-063 completion — verified isolated Git worktrees

Status: SOURCE_COMPLETE / PHYSICAL_FLEET_QUALIFICATION_DEFERRED. This implements the Git portion of TIP-061B/063 using the existing principal/writer authority. Tests used disposable real Git repositories, temporary keys and verified local HTTPS. No external repository, remote fetch, merge, deployment, production key/installation, actual MT5/SDK or private VM was used.

YAGNI-3: node-owned isolated source commits need a writer fence and concrete Git proof. This implementation reuses NodePrincipalRuntime, NodeCommand, PhaseFence, the shared source guard and actual project session/checkpoint store. It adds only registered Git path policy, bounded effect journal, owned Git completion receipts and read-only worktree recovery head; Continuity remains the semantic task history.

## Source-to-acceptance result

| Requirement | Concrete source and tested result |
| --- | --- |
| Registered real worktrees | Trusted constructor registers exact project/repository/baseline/tracked-source allowlist, separate canonical worktree root and Git executable. Actual detached Git worktree creation/removal uses structured argv; caller payloads cannot select a repository/root/executable. Control state and executable locations cannot be selected as writable worktree roots. |
| Verified single writer | Exact sealed NodeCommand originates from authenticated TLS principal admission and signed assignment. Reused phase guard retains original principal/session/assignment/writer epochs and shared source lock. Fresh phase checks precede each file effect, stage/tree/commit; revocation between file write and commit prevents Git commit. |
| Source and HEAD boundaries | Existing project session/revision/checkpoint/live source ref is revalidated; configured baseline bytes match that EA. Main and task HEAD/clean state, prior source SHA, registered relative paths, replacement bytes/hash and staged tree paths/blobs are checked. Main checkout and authoritative project session remain unchanged by worktree operations. |
| Git execution restrictions | Fixed empty hooks directory checked before every invocation; fsmonitor, signing, automatic maintenance, global/system config and external attributes disabled. Includes/includeIf/worktree config, filters, grafts, alternates, attributes, submodule and symlink baselines refused. No fetch or caller shell. Output/process duration are bounded and the exact retained Git process is waited/closed. |
| Durable producer closure | Each mutating create/stage/write-tree/commit/retire step persists ATTEMPTED before launch and CLOSED only after retained process wait, reader completion and pipe closure. Receipt binds fixed argv/purpose, operation/phase/intent and observed head/tree. Loss of that receipt keeps UNKNOWN even when later HEAD is exact. |
| Original-effect recovery | Reopening under the same authority may perform read-only proof and acknowledge only an already completed original effect with all issued Git steps closed. Exact parent/tree/message/intent/owner are required for commit. File writes/Git mutations are never repeated during recovery; partial/dirty/unknown outcomes block successors without TTL or force cleanup. Completed historical receipts replay unchanged after later commits or retirement. |
| Journal integrity | Bounded persisted signed commands and request hashes, owner projections, typed step mappings, exact receipt/authority-ack agreement and finite malformed-state errors. Valid-shaped changed receipts and nested malformed bodies/requests/owners fail closed. |
| References and continuity | Source_ref is an actual existing node session/checkpoint projection. Worktree receipt records real Git HEAD/tree and source attribution. Optional opaque result_ref is explicitly UNVERIFIED_REFERENCE_ONLY and grants no native/artifact/SDK success. No second Continuity or project history. |
| All-authority restore | Read-only recovery_head binds deterministic journal digest, all original command/owner/receipt/closed-step mappings, clean active Git heads and linear history. Unknown/unclosed rows deny quiescence. Existing writer witness includes this configured head; disabled stores are null. Actual HTTPS restore test retains the exact head in a signed operator checkpoint, reopens the real worktree store and clears all configured journals together. |
| Concrete startup | Existing opt-in fleet NodeRuntime opens/binds/closes the configured worktree store. Startup and finite DTO/operator failure handling are documented in TIP-063-worktrees-operator.md. This is source integration; no service was provisioned here. |

## Verification

Builder historical focused worktree cases: **47 passed** within the combined run below. These use actual temporary Git and genuine signed TLS principal admission, covering prepare/commit/retire, untouched main/session, base/dirty/HEAD/CAS/source-ref/path errors, forged/mutated seals, shared lock exclusion, post-effect crash/reopen recovery, unknown partial effect and successor denial, fresh revocation, hooks/filter/include denial, attributes/submodule/symlink denial, ignored-file retirement safety, bounded output, malformed/cross-record journal failures, missing durable Git closure, deterministic read-only head and unknown/dirty head denial, portable Windows slash/drive-case parsing, actual native Git/path variant comparison and malformed-listing refusal. Git root/common-directory observations use native canonical paths; retired list comparisons use strict bounded NUL porcelain rather than raw path strings. Actual Windows Git lifecycle validation remains for the source CI full suite.

Builder historical combined checkpoint: **152 passed, 1 skipped**:

```bash
PYTHONPATH=/workspace/scratch/250985b4823e/audit/tunnel-venv/lib/python3.12/site-packages:app:tests/unit python -m pytest tests/unit/test_tip063_worktrees.py tests/unit/test_tip061b_writers.py tests/unit/test_tip064_integration.py tests/unit/test_tip057r_sdk.py tests/unit/test_tip060c_https_restore.py -q
```

The one skip is the retained SDK Win32 construction check on Linux. No worktree test was skipped on this Linux run. Windows symlink tests may require platform privilege; Windows behavior will be assessed by the Contractor's source workflow without implying physical fleet/SDK qualification.

Builder original configured HTTPS restore checkpoint: **3 passed**, preserving empty and nonempty-source variants and adding actual configured-worktree prepare/CLOSED phase ACK/operator head/reopen/signed witness:

```bash
PYTHONPATH=/workspace/scratch/250985b4823e/audit/tunnel-venv/lib/python3.12/site-packages:app:tests/unit python -m pytest tests/unit/test_tip060c_https_restore.py -q
```

The authority Builder subsequently added two read-only EMPTY_ABSENCE variants to the shared HTTPS restore test, bringing that file to five variants. The Contractor reports the later authority checkpoint as **145 passed in the authority-owned scope, 188 tests total in the shared checkpoint**. These follow-up results are separate from this Builder's historical 47-case, 152-pass and three-variant checkpoints above. At that authority checkpoint only the shared test changed; the historical worktree product and focused test bytes were unchanged.

Windows source-CI parser refinement after candidate `3b955d6`: drive-less malformed Git paths could raise WORKTREE_PATH_INVALID on Windows before the unknown-field check, while Linux returned GIT_OUTPUT_UNPROVEN. Parser-internal rejected path/HEAD observations now consistently return GIT_OUTPUT_UNPROVEN. Accepted absolute/canonical/no-symlink grammar is unchanged. Added relative-path and invalid-HEAD output negatives. The updated focused Linux run passed **49 cases**; compile and diff checks passed. This is a portable source regression checkpoint; combined Windows CI on the new candidate remains authoritative.

The QA Builder later changed only actual HTTPS fixture origins to numeric IPv4 with a matching certificate SAN, preserving the exact signed audience. Its reported worktree/writer/060C/064 diagnostic checkpoint passed **107 cases**. This shared-test follow-up is distinct from the worktree checkpoints above; the source table includes the current authorized joint test bytes.

Python compilation of product and tests and `git diff --check` passed. The joint restore test refinement was explicitly handed off by the authority Builder; principal, coordinator, CLI and transport code remain owned by their respective Builders.

## API and limitations

`WorktreePolicy` requires max_worktrees, max_operations, max_changes, max_change_bytes, max_payload_bytes, max_git_output_bytes, git_timeout_ms and wait_ms; booleans and out-of-range numbers fail. `NodeWorktrees(root, principals=sealed_runtime, repositories=registered_map, worktree_root=canonical_root, git_executable=trusted_file, policy=policy, initialize=False)` is trusted local construction only. `principals.bind_worktrees(store)` connects the existing verified finite routes. `apply_command(path, sealed_command, operation_id=...)` accepts only prepare/commit/retire. `recovery_head()` is bounded read-only; `local_path()` is trusted owner inspection.

Prepare payload: `{project_id, worktree_id, base_commit}`. Commit: `{project_id, worktree_id, expected_head, changes, message, source_ref, result_ref}`. Retire: `{project_id, worktree_id, expected_head}`. Each change is `{path, expected_sha256, sha256, source_base64}`; deletion sets both replacement fields null. See the operator contract for exact required references and safe failure behavior.

The configured project baseline is frozen; this source has no automatic baseline migration, branch merge, source adoption, forced retirement, TTL reclaim or generic Git shell. A crash before durable producer closure, partially written source, dirty tree, altered HEAD or drained unresolved owner remains blocked. A worktree result does not update authoritative node source/session or qualify a native artifact. Actual final-source multi-client/network/process testing remains for later physical qualification.

## Source checkpoint

The bundle below covers this Builder's product, focused tests, authorized joint-test refinement and operator handbook. It is a source checkpoint, not a physical installation approval. Shared authority/startup files are independently owned and reviewed by the Contractor.

Current bundle SHA256: `340c9664d8044df140099d90737d62e2e0b95799804b6d6e495b3d9d7ea71c7c`.

| File | SHA256 |
| --- | --- |
| `app/vibemql5/fleet/worktrees.py` | `dbefac5d6be391e8b0acfb9368eed624b4edd3d58127dbf2cb7c9174d2fb3396` |
| `tests/unit/test_tip063_worktrees.py` | `6156b0e99d4dbb50a69b4db1bdfba998a6d7759406f34fbbe517c2dd9be9eaa6` |
| `tests/unit/test_tip060c_https_restore.py` | `c126e415dae9de63d71d598c3dd8b4a35dd133dbf2cb80901c5fe548b623a769` |
| `docs/fleet-v1/TIP-063-worktrees-operator.md` | `4e3f68fc8a0c708619dbf1bb6fdc37fffda2e956d59886a0b9817ab6d570ceaa` |

## Windows Git include fixture refinement

Candidate `ebbb56c` exposed Windows backslashes written unescaped into the included-filter fixture's Git config. The fixture now writes POSIX path syntax and confirms Git reads `filter.bad.clean` from the include before applying the unchanged application rejection and no-execution/no-worktree assertions. Product Git policy and timeouts remain unchanged. The signed-roster/native/worktree joint diagnostic passed **141 tests, zero skips**, 14.07 seconds, recorded in `evidence/tip060056-windows-fixture-refinement.txt`/`.xml`. The table identifies current fixture bytes; earlier counts and prior bundle `ac53102c418b1cbb7ccb77627559b5bfd026c686d2f457d2013ebb0cf094dc15` retain their earlier snapshot meaning. Exact next-candidate Windows confirmation remains pending.
