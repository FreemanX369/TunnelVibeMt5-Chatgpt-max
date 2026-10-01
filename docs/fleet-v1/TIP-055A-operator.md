# TIP-055A — Local identity operator guide

This release adds a persisted identity overlay to inventory. It does not enable fleet transport, multi-terminal native jobs or new MCP tools. Native execution still uses the existing fixed MT5-2 policy and global locks. `LOCAL_PERSISTED_REGISTRY` is local registration provenance, not authenticated node enrollment or native execution evidence.

## State and read-only behavior

The authority is `<root>/state/fleet/identity.json`, schema `fleet.identity/1`. Enrollment/update writers coordinate through `identity.lock` and publish one atomic JSON replacement using the existing job metadata helpers. Do not edit IDs, generations, revisions or operation receipts by hand. Config remains in `config/terminals.json`; identity operations never rewrite it or historical jobs/results/sessions/checkpoints/Continuity.

Inventory/show reads never bootstrap or repair a registry. Missing state is `UNENROLLED`; corrupt/unsupported/duplicate persisted state is `INVALID`. Neither case produces replacement IDs. A malformed legacy config still needs explicit config repair before enrollment.

Terminal IDs are opaque and persisted. Build, binary contents, hostname and process restart do not change them. The identity revision advances for each accepted update/new enrollment; a new operation that makes no terminal change still commits its receipt at a new identity revision. Terminal generation advances only when an explicit replacement changes the recorded binding, including its canonical path observation. Rename and disable/re-enable preserve generation.

## Explicit bootstrap

Run these commands only in an authorized local installation or isolated fixture. The examples use an operator-selected root; deployment to the existing VPS is a separate gate.

```powershell
python -m vibemql5.adapters.cli --root C:/VibeMQL5 identity-show
python -m vibemql5.adapters.cli --root C:/VibeMQL5 identity-bootstrap
```

Bootstrap enrolls the full configured terminal list, including disabled rows, all-or-none. Repeating identical enrollment returns the existing registry. Adding a genuinely new binding requires the current revision explicitly:

```powershell
python -m vibemql5.adapters.cli --root C:/VibeMQL5 identity-bootstrap --expected-revision 3
```

Changing an enrolled alias/path/enabled configuration is not inferred as a new identity. Bootstrap rejects it and requires an explicit update. Supplied stale revisions are rejected even if the proposed bootstrap is already enrolled. Keep a verified backup before every identity transition; never delete the registry to fix a config mismatch.

## Rename, replacement and enabled state

Read `identity-show` and use its exact terminal ID and identity revision. Use a unique operation ID for each intended change and reuse that ID with the exact original arguments on retries.

```powershell
python -m vibemql5.adapters.cli --root C:/VibeMQL5 identity-update term_<32-hex-id> --expected-revision 1 --operation-id operator/rename/01 --alias MT5-LAB
python -m vibemql5.adapters.cli --root C:/VibeMQL5 identity-update term_<32-hex-id> --expected-revision 2 --operation-id operator/replace/01 --terminal-path C:/MT5-LAB/terminal64.exe --data-root C:/MT5-LAB-DATA
python -m vibemql5.adapters.cli --root C:/VibeMQL5 identity-update term_<32-hex-id> --expected-revision 3 --operation-id operator/disable/01 --enabled false
python -m vibemql5.adapters.cli --root C:/VibeMQL5 identity-update term_<32-hex-id> --expected-revision 4 --operation-id operator/enable/01 --enabled true
```

The placeholder is not a literal shell argument; copy the actual persisted ID. These examples assume each preceding operation committed. If another writer changed the revision, read fresh state and review the intended update; do not silently rebase a stale operation.

Executable and data-root replacement arguments are required together. A matching original operation replay returns its original committed receipt even after subsequent updates or filesystem disappearance; its revision may differ from the current registry. Divergent input under an existing operation ID is `IDENTITY_OPERATION_CONFLICT`. A new operation with a stale expected revision is `IDENTITY_REVISION_CONFLICT`.

Review and coordinate `terminals.json` separately so it matches the committed alias/path/enabled registration. Until aligned, target validation fails closed. Registry-disabled bindings remain `DISABLED` even if legacy config still says enabled. **M0 identity disable does not disable the legacy native terminal:** existing native policy uses the old config and must be administered through that existing policy.

## Resource and target interpretation

Inventory preserves all old fields and `ok` retains its old config/file-validation meaning. Added fields include device/terminal IDs, generation, identity revision/status/source, `resource_qualification`, conflicting aliases and `routed_native_enabled=false`.

`RESOURCE_CONFLICT` detects shared normalized executable/data-root paths, observed symlink/junction canonical paths or file IDs. Case/separator normalization applies to Windows paths. Duplicate case-insensitive aliases cannot qualify independently even though the legacy inventory dictionary historically collapsed them.

`QUALIFIED` here only means the enrolled paths are physically observable, match their persisted canonical bindings and have no detected conflict in this local inventory. It is not a native concurrency/deployment certificate. Missing/unobservable roots and Windows paths in a POSIX fixture remain `UNQUALIFIED`. Symlink/junction retargeting after enrollment yields `TARGET_MISMATCH` or an explicit resource conflict; it never silently advances generation. The local validator rejects unqualified bindings and has no dispatcher/fallback path.

The local `fleet.target/1` reference consists of `device_id`, `terminal_id` and positive `terminal_generation`. M0 does not invent a paired route generation. A non-null route generation or a capability other than inventory fails with `ROUTED_NATIVE_NOT_ENABLED`. Registry/config reads are point-in-time observations; later native TIPs must revalidate immediately before side effects.

## Recovery and rollback

1. Stop coordinated identity writers before manual recovery. Retain the corrupt file and temporary files as evidence; do not bootstrap over corruption.
2. Restore a previously verified complete registry backup only as a reviewed recovery action. Stale backup generations/receipts must not be used to authorize future fleet work. M0 has no remote routing or native identity consumer.
3. Reconcile configured paths and inspect inventory. Missing canonical observations remain unqualified until an explicit reviewed binding update captures them.
4. Code rollback may remove the identity overlay while leaving `identity.json` and its operation receipts intact. Legacy config/native tools remain usable. Returning to compatible M0 code restores the same IDs; do not rename/reset state during rollback.

The existing atomic writer proves process-crash/pre-replace safety in fixtures, not hardware power-loss certification. Abandoned `.identity.json.*.tmp` files are ignored by readers; do not promote one automatically. All writers must use the shared lock/API.

## Verification boundary

The implementation suite covers independent spawned writers, killed pre-replace writer, corruption/receipt validation, CAS/idempotency, config/build compatibility, resource collisions and point-in-time target consistency. POSIX symlink/hardlink evidence is not Windows junction evidence. A Windows-only junction fixture runs in the existing Windows CI unit suite; if junction creation is unavailable it reports a skip, not a qualification PASS. Windows CI fixtures are still separate from deployment-specific Windows/VPS acceptance. No existing VPS enrollment, native tester, account/credential or AutoTrading action belongs to this TIP's implementation verification.
