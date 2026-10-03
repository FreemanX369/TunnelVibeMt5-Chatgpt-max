# TIP-057R-SDK completion — product isolated state/account source

Status: SOURCE_COMPLETE / PHYSICAL_SDK_QUALIFICATION_DEFERRED. No actual SDK, private VM, operator installation/key, profile provisioning, production ACL change, remote publish, merge or deployment occurred in this work.

## Source-to-acceptance result

| Acceptance | Delivered source and evidence |
| --- | --- |
| Narrow real observation | Product worker prepares late SDK import, actual initialize/state/account/shutdown, exact retained terminal identity before/after, bounded timeout, legacy projection and masked/null login. Synthetic injected adapters always return SYNTHETIC_SDK_ONLY. |
| Exact operator qualification | Sealed installation verifies domain-separated Ed25519 approval, exact installed package/dependency/runtime hashes, complete twelve-case REAL_Q2 evidence approval, actual Windows build/session and conservative read-only source/runtime/authority ACL observations. Signature authenticates operator evidence approval; it does not prove physical events from PASS labels. |
| Restricted owned creation | Product Win32 source fixes Python/worker/argv, suspended AppContainer/zero-capabilities/no-child attributes, retained creation handles, actual token/mitigation readback and independent full process observation before durable bind/resume. No proof module runtime imports or generic command launcher. |
| Ownership and cleanup | One common or verified scoped lease spans lifecycle. Arm/create-attempt/bind/resume ordering is explicit. Exact ARMED zero-attempt may close; unknown create/publication retains exclusion. Qualified preventive boundary plus exact retained exited worker is required after launch. Shutdown return and fixture strings cannot open public production qualification. |
| Scoped authority | Signed SDK scope approval pins installed capacity profile/key/candidate/runtime. Sealed scoped lease/reference and exact BOUND worker record use the same authority. Worker checks bounded stable checkpointed SQLite bytes in memory, without control guard/DB writes. Missing/malformed/mismatched scoped marker never falls back globally. IPC stays serialized per device. |
| Local/node integration | Trusted local installation path preserves C1 default denial and targetless legacy behavior. Local route-positive calls deny. Node adapter requires sealed one-use current TLS-delivered READ admission and fresh gateway checks before arm/create/resume/promotion. Full routed attribution remains frozen. Absolute command deadline supplies one remaining monotonic budget, capped at ten seconds. |
| Two-binding pilot selection | One adapter accepts singleton compatibility or one-to-sixteen sealed installations, exact device/terminal/generation selection and same root/device/session/Python-SDK/profile/scope family. Unknown/duplicate/stale targets do not fall back to another installation. Read-only typed catalog fixtures demonstrate two selections with zero SDK effects. |
| Truthful failure receipt | Failure discards all live payloads. Admission loss after proved closure and actual lease release preserves CLOSED/PROVEN. Pre-launch denial reports NOT_ATTEMPTED cleanup. Actual release failure reports UNPROVEN and preserves the earlier SDK/admission error as primary. |
| Deferred activation | No real Q2/PASS sample or production approval is shipped. Later operator handbook describes the complete physical matrix, exact resource/profile preparation, signing/validation and known unsupported persistent handoffs/phase chains. |

## Verification

Focused product SDK suite: **57 passed, 1 skipped**. The skip is actual Win32 API/structure construction on Linux; no Windows or SDK qualification is implied. The focused suite covers malformed/bounded protocol data, frozen request mutation, masking and field/count limits, false/raised initialization and shutdown, binding/deadline failures, categorical synthetic/signature rejection, SDK import-origin pins, ACL write rejection, owned lifecycle fault windows, real disposable scoped SQLite zero-attempt/UNKNOWN restart exclusion, read-only BOUND snapshot I/O, two-binding catalog selection, first-error retention and actual common lease release.

Final retained/integration checkpoint: **216 passed, 1 skipped, 97 subtests passed**, using:

```bash
PYTHONPATH=/workspace/scratch/250985b4823e/audit/tunnel-venv/lib/python3.12/site-packages:app:tests/unit python -m pytest tests/unit/test_tip057r_sdk.py tests/unit/test_tip057rc1.py tests/unit/test_tip056_scoped.py tests/unit/test_tip059_read_broker.py tests/unit/test_tip064_integration.py tests/proofs/tip057rb1/test_portable.py tests/proofs/tip057rb1/test_controller.py -q
```

Python compileall for the five source files and focused suite passed. `git diff --check` passed. Frozen proof source was reused by extraction only; this Builder did not edit proof files. Portable fixtures and memory snapshots grant no operator/physical capability. A later shared scoped-store provenance refinement required the focused test to explicitly reject synthetic BOUND records and label the positive read-only signed-protocol claim fixture. The five SDK product sources and operator handbook were unchanged; the updated focused and retained suites above passed.

## API handoff

- `QualifiedSdkInstallation.from_operator_manifest(path, trusted_operator_public_key, expected_payload_manifest)` is the local configured trust entry. Validation/signing CLI and the later operator procedure are in `TIP-057R-SDK-qualification.md`.
- `read_local(root, concurrency, operation, target, installation, budget_ms=10000)` supports only local un-routed state/account under exact installed capability.
- `observe_under_owned_lease(root, lease, request, installation, node_admission=None, command=None)` does not reacquire a lease; scoped dispatch uses the actual sealed lease authority.
- `QualifiedReadAdapter(root, concurrency, singleton_or_tuple_list).read(command, admission)` selects an exact local signed installation while preserving fresh node route/session authority.
- Worker request/result are at most 32 KiB. Approval/resource/control metadata is at most 256 KiB, resource/hash maps at most 512 entries. Source/runtime files use bounded stable-handle hashing. Observations share at most ten seconds; lease/probe/initialize are capped at two seconds within that budget. Exact cleanup wait is separately bounded at five seconds and may exceed the soft observation budget.

## Source checkpoint

Bundle SHA256 (canonical relative-path-to-hash map below): `773b3201489dff7327a4065956f40428ff0d052bad8349044efcba6e9a212e12`. This is a source checkpoint, not a physical qualification or an installation candidate approval. Other Builders may change shared product sources before the Contractor's final whole-build checkpoint; every real installation must bind the final complete deployed payload.

| File | SHA256 |
| --- | --- |
| `app/vibemql5/fleet/sdk_protocol.py` | `e64d4f06aa031425b3a816062ad46746d4b551c0a0faf43dd6f06cb031588f52` |
| `app/vibemql5/fleet/sdk_worker.py` | `08d226bc8e805654560d6ea0fd7df1f8750f9a21bbc372b75a0d7a14869bbc18` |
| `app/vibemql5/fleet/sdk_qualification.py` | `b79885bb1daf9ba08b1adf3b15c7dffefa54123516b99442d445434b0a622bdf` |
| `app/vibemql5/fleet/sdk_controller.py` | `debcb7a3bc057935a7f11f4a70b1da00e52195f5ad6d2adb0223921005d932ce` |
| `app/vibemql5/core/isolated_sdk.py` | `471f4760161d019c8c83032a2207a1be06f08b2823b14d624e43bbf32b2ee46c` |
| `tests/unit/test_tip057r_sdk.py` | `f22656b96610348cca90d63a8736fd1c22c604cdc661e313941b2612ace9d14d` |
| `docs/fleet-v1/TIP-057R-SDK-qualification.md` | `d9c5636b80798b7b6fb720a4d404da4f8a49f4ec3f819608b2ebb9d0e1be7451` |
