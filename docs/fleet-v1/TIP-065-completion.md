# TIP-065 Builder completion report

STATUS: DONE for bounded implementation/focused source verification and overlay preparation; new exact candidate CI, live deployment and all physical qualification remain pending Contractor verification. No commit/push/merge/live write or authority initialization occurred.

Source parent: `f25ec99e174a662928b05db5c21f92c5ef47a0cc`. Six product/test files are frozen in `frozen-source-manifest.json`; Contractor-owned documentation is separate. No code edits after the final focused run.

YAGNI-3 before code: actual ownership/dependency observations were missing before activation; reuse ownership validation, SHA, existing server_info and CLI; the shortest implementation is one read-only observer, pure shared helpers and two existing entry points. No new MCP tool, migration/initializer, process manager, backend file allowlist or authority fallback was added.

## Behavior and scope

`core/deployment_preflight.py` observes only the fixed native installation/state records (64 KiB each), scoped-install presence without opening its contents, fixed observer/validator/provenance/MCP source bytes (1 MiB each), executing Python version and standard-library distribution metadata for MCP/cryptography. Two matching passes are explicitly unlocked/non-atomic; changed, unsafe, unreadable and overlarge observations remain CONCURRENT/INCOMPLETE. Only finite status/reason/disposition/phase/generation and fixed-file digests/sizes are emitted. Epochs, tokens, operations, process identities/images, raw record/exception contents, credentials and configs are not emitted or collected.

Matching CLOSED is `OBSERVED_CLOSED`, never admission/ready. Every result retains `activation=NOT_QUALIFIED` and `physical_qualification=NOT_RUN`. Metadata ordinary-release ranges are Python >=3.12,<3.13, MCP >=2.1,<3, cryptography >=50,<51; missing/error/unsupported version syntax is unevaluated. Source identity is current on-disk bytes, never loaded-code identity. Metadata is not SDK, wheel/DLL, native or physical qualification.

Pure marker/snapshot validation was extracted unchanged from OwnershipAuthority.load; its file-read/error priority and all guard paths remain unchanged. `provenance.sha256_bytes` shares the existing SHA implementation without reopening capped snapshots. The CLI preflight branch runs before facade/concurrency/configuration construction. Existing server_info has one additive result field and unchanged input schema/catalog. Runtime version/build provenance was not bumped.

Windows reads compare retained and fresh file handles through the same read-only kernel32 file-information API, avoiding CPython path/fd stat identity aliases. No process handles, ACL/key modules, SDK/native producer or crypto package loading occurs. POSIX uses NOFOLLOW and NONBLOCK, checks regular-file descriptor identity before reading, and rejects a controlled regular-file→FIFO swap without blocking. These file observations remain snapshots, not retained admission proof.

## Files and tests

Changed source: adapters/cli.py, adapters/mcp.py, core/native_ownership.py, core/provenance.py. New source: core/deployment_preflight.py. New tests: tests/unit/test_tip065_deployment_preflight.py. Full exact hashes/sizes: `frozen-source-manifest.json`.

Final command, from repo with locked isolated Python 3.12.14 environment:

```
PYTHONPATH=app:tests/unit /workspace/scratch/1818a0d45fa0/deploy-20261005/source-venv/bin/python -m pytest tests/unit/test_tip065_deployment_preflight.py tests/unit/test_tip057rg03a_native_ownership.py tests/unit/test_tip055a_runtime_forensics_identity.py tests/unit/test_tip055b_runtime_forensics_release.py tests/unit/test_tip058a_gateway_control.py::test_all_85_actual_mcp_schemas_remain_at_c1_baseline -q --tb=short --junitxml=/workspace/scratch/1818a0d45fa0/tip065-20261005/builder-focused-final.junit.xml
```

Result: **165 PASS / 5 explicit Windows skips / 0 FAIL, 4.64s**. Two skipped TIP-065 tests require actual Win32 retained-file identity: positive CLOSED/source observation plus differing real file IDs, and fresh-path replacement rejection. They must execute on the new Windows CI candidate; Linux skips do not satisfy that boundary. Remaining skips are the three existing Windows concurrency release fixtures. POSIX FIFO/symlink controls passed locally.

Meaningful coverage includes absent/nonexistent roots, marker/state loss, corrupt/non-object/migrating/epoch/ACTIVE/CLOSED records, oversized/read-denied/nonregular paths, simultaneous authority replacement, capped read counts, mutation/guard/process/network/package-import prohibition, scoped content never opened, metadata unavailable/malformed/out-of-range and Python boundary, CLI facade/config bypass, and all 85 catalog/input schemas.

Original first run **34 PASS / 1 FAIL** is retained: the MCP result fixture omitted existing settings.json needed by existing `_fixed_terminal`; only the disposable fixture was corrected. Intermediate **160 PASS / 5 skips** and final **165/5** logs/JUnit are retained separately. Contractor independently recorded 606 validator/read-fault equivalence controls in contractor-validator-equivalence.json. No full canonical source harness was run for TIP-065 by Builder; Contractor owns that and new-head 8/8 CI.

## Live overlay prepared, not deployed

`live-overlay-payload.json` contains five deployable files with content/digests and required fresh live CAS: observer, pure ownership validator/helper module, provenance helper, CLI command and separately derived old-live MCP overlay. Fresh hash/CAS checks are required. INVALID_ARGUMENT does not establish absence. For the new observer, empty expected SHA and empty checkpoint use the supported server-enforced create-only CAS; success plus receipt before-SHA empty establishes absence at that serialized mutation. Its basis remains NEW_PATH_SERVER_CREATE_ONLY_CAS_PENDING until the live write receipt exists. Old live concurrency/facade/compiler/jobs/tester bytes are not replaced.

Contractor binds the variant in [tip065-legacy-overlay.json](config/tip065-legacy-overlay.json), including old/derived adapter hashes, all five payload hashes and both schema baselines, so canonical candidate manifest/ZIP retains the overlay provenance. The live installed tree remains mixed: pre-existing legacy modules, staged f25 additions and this bounded overlay when deployed. The overlay adapter is a separately verified two-addition legacy variant, **not the full candidate MCP adapter**; four helper/observer/CLI app files match exact candidate source. This report does not claim the live overlay has been installed.

The retained old-live MCP SHA is `d50d2896fb80837af113a985ddc65cbc12bffa8ffa26e57b7257726911a9de99`; overlay SHA is `520a757513230276bca92150e533b934a09dfaa8838cc4ac5d226b9dc1463a57`. Removing precisely one observer import and one server_info field returns its exact original AST. Text adds only those two lines. Existing live comments/behavior are preserved.

The two schema baselines are deliberately distinct:

| Catalog/input schema set | SHA-256 |
|---|---|
| Retained old live, 85 ordered tools | dd6a0e5b8dc61ee832054b6c0e5f889ef8c362b85f062e1d122a5fae03fd771e |
| Prepared old-live overlay, same 85 ordered tools | dd6a0e5b8dc61ee832054b6c0e5f889ef8c362b85f062e1d122a5fae03fd771e |
| Full TIP-065 source, identical to f25 Fleet source schemas | 64337437115a20a8555cc1214706a503b985195dbdbd219de2adfa35e2c8134d |

Proof and full input schema maps are retained in overlay-schema-proof.json and overlay/*.schemas.json. Schema proof uses isolated source fixtures and does not certify current live loading. Payload SHA is `0efadd3d855b602e6bd8d58cd7033f092395026b633bceb28629e75fe4003182`.

OPEN: actual Windows candidate verification; new exact-head 8/8 CI/full manifests/JUnit/proofs; bounded live overlay/hash/READY/idle/preflight receipts; actual ownership migration, Fleet configuration/process/connector registration and private VM/MT5/SDK/load qualification. Original intermittent owner-grant and later CI causes stay preserved/open; this observer is not their functional fix. No UNKNOWN/evidence/history/journals were cleared or replayed.
