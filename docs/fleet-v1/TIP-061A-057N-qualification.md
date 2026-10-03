# TIP-061A / 057N — Deferred native qualification procedure

Status: prepared source procedure; physical MT5/VM qualification is deferred. No installed trust, operator key, REAL_MT5 receipt or production approval is shipped. Harmless OS fixtures and synthetic signatures cannot activate the product factory.

## Fixed trust and qualification selection

The node uses only `config/fleet-native-trust.json`, exactly `{"schema":"fleet.native.trust/1","operator_public_key":"<lowercase 64 hex>"}`. Installed trust, target approval and shared runtime files must be protected owner-controlled regular files: POSIX current-owner mode0600, or Windows protected owner/SYSTEM-only ACL verified on the retained file handle. Symlinks, reparse paths, extra hard links, changed metadata and untrusted permissions deny activation. The configured public key authenticates operator approval of physical evidence. Signing keys never belong in the receipt, repository or wire command.

Without an installed scoped marker, the qualifier reads only `state/fleet/native-qualification.json`. With `state/fleet/scoped-install.json` present, it reads only `state/fleet/native-qualifications/<terminal_id>-g<terminal_generation>.json` and fixed `state/fleet/native-runtime.json`. The validated frozen terminal identity determines that filename. Missing target approval never falls back to the singleton or another target; malformed markers also block legacy native ownership admission.

Use the exact final deployed product on the physical node. `native_qualification.source_manifest()` returns the same full Python/pyproject/lock manifest as the SDK/capacity source gate; `candidate_sha256` is SHA256 of its canonical JSON. A source checkpoint's test receipt cannot stand in for this final installed candidate. Any source, dependency, runtime, binary, target generation, root or session drift requires renewed exact approval.

## Physical controls to record later

Operate dedicated test terminals in the actual interactive Windows session with preventive controls excluding existing terminal/broker escape and unowned descendants. Test the real producer at each control below. Preserve original failed and successful evidence; a PASS label is an operator assertion, not independent proof that the physical event occurred.

| Control | Required physical observation |
| --- | --- |
| COMPILE_PASS | Exact pinned EA/includes compile and produce the captured EX5 digest. |
| COMPILE_FAIL | A known compile error reports failure and cannot start the tester. |
| TEST_FULL_PERIOD | Native selected dates and executed coverage match the effective frozen period. |
| WRONG_ROOT | A different installation/data/include/agent root is denied before copies/create. |
| STALE_TARGET | Changed terminal generation or route denies new effects without target fallback. |
| CHILD_CONTAINMENT | Actual compiler/tester descendants remain inside the held no-breakaway Job Object. |
| PARENT_CRASH | Parent death contains the real worker; durable ACTIVE ownership remains blocked. |
| EXACT_CLEANUP | The retained exact worker exited and held Job Object ActiveProcesses is zero before CLOSED. |
| NO_BROKER_ESCAPE | No existing terminal/broker session is adopted or used for a handoff. |
| INTERACTIVE_SESSION | Actual nonzero logged-in Windows session and terminal/compiler FileVersion builds match. |

Each control receipt lives under `state/fleet/native-qualification-evidence/`, has bounded JSON bytes and contains at least `schema: fleet.native.control/1`, its exact case, `evidence: REAL_MT5`, `result: PASS`, the full frozen target including positive route generation, and `payload_sha256` of the installed source manifest. Link richer process/descendant/source/test evidence in that retained receipt. The approval hashes every control file; it cannot use fixture evidence labels. Controls must support the dedicated synchronous lifecycle; persistent SDK/IPC/live terminal handoffs remain unsupported.

## Approval envelope

The Ed25519 envelope is exactly `{body,signature}`, with a lowercase 128-hex signature over `b"fleet.native.operator-approval/1\0" + canonical(body)`. `body` has exactly:

- `schema: fleet.native.operator-approval/1`, `scope: DEDICATED_TESTER_SYNC_OWNED`;
- integer `approved_at_ms` and future `expires_at_ms`, and the complete installed `payload` manifest;
- `installation`, `controls` and explicit `policy`.

`installation` has exact canonical absolute `authority_root`, full frozen `target`, `binding: {executable,data_root}`, `metaeditor`, positive observed `terminal_build`, `compiler_build`, `windows_build` and nonzero `session_id`, exact `binary_hashes` for the terminal and compiler, actual `python` and `python_sha256`, `gateway_public_key`, exact HTTPS `gateway_audience`, `include_root` equal to the target data-root MQL5/Include, and observed `agent_root`. Canonicalization uses the existing identity `normalize_path` function. The audience is the configured gateway HTTPS origin; an unrelated signer or audience cannot authorize this installation.

`controls` maps exactly the ten case names to `{path,sha256}`. `policy` contains positive integers `compile_timeout_seconds`, `test_timeout_seconds`, `resource_max_records`, `resource_wait_ms`. These are explicit signed operational limits, not silent numerical production defaults. The factory rechecks actual Windows session, Python bytes, OS build and terminal/compiler FileVersion builds; a signed metadata fixture cannot bypass those checks.

Portable `validate_approval(envelope, operator_public_key, expected_payload=..., now_ms=...)` validates provenance and metadata. Only `load_installation(root, native_request)` creates the internally sealed production installation after actual runtime checks. Neither function signs evidence or installs trust automatically.

## Qualified scoped parallel terminals

Each target has its own exact approval above. The common runtime envelope signs `b"fleet.native.runtime/1\0" + canonical(body)`. Its body has exactly `schema: fleet.native.runtime/1`, `authority_root`, `candidate_sha256`, `payload`, actual `python`, `python_sha256`, `windows_build`, `session_id` and `terminals` (two to sixteen rows).

Every row has exact `terminal_id`, positive `terminal_generation`, `binding`, `metaeditor`, `binary_hashes`, observed `terminal_build`, `compiler_build`, `include_root`, `agent_root`. Reject duplicate terminal identities, aliased physical bindings, overlapping resources, changed bytes and cross-target approval. Per-target approval must equal its common row and common root/Python/Windows/session. `runtime_sha256` is the SHA256 of this verified common body, shared by native, capacity and any approved SDK scoped-runtime reference.

The separately signed capacity profile must bind that candidate/runtime, exact physical resources, conflict matrix, maximum capacity and measured load/closure receipts. Verify the operator and real two-terminal load/descendant/closure controls before installing it. Source fixtures exercise concurrent producer composition through private test factories; they provide no installation approval. No caller-supplied root, namespace or parallel flag grants scoped ownership.

## Effect and recovery behavior

Gateway phase admission and each actual effect step use exact Ed25519 authorization bound to target/route/request/global job/node operation/local job/session/challenge/sequence/event/audience. Cancel/terminate additionally bind the exact active process digest already acknowledged at the gateway. Node journal persists intent and consumption before returning the sealed proof; the producer checks it immediately before mutation/CreateProcess, including after durable create-attempt I/O.

An action begun while its proof is valid may return after expiry and record that truth. Its next distinct action requires a new signed step and exact predecessor completion. Lost, unconsumed expired, interrupted or UNKNOWN steps cannot advance, silently renew or repeat. Expiry by itself never kills a running worker. Final result promotion is an explicit completed step, with no automatic baseline promotion.

The source guard captures immutable inputs/session under the same mutation resource as managed writers. Scoped producers release that global guard after atomic snapshot publication, then consume only the pinned candidate. Later source revisions do not relabel running results; public resume/new admission of an old placement remains stale. Captured and deployed EX5 bytes are checked before every tester boundary. Exact process handles and the held Job Object are retained until verified closure. After normal exact phase closure and outer lease return, `terminal_closure(job,request)` can return a bounded historical closure receipt for journal recovery. It never acquires current ownership or opens a new native effect. A crash/uncertain attempt requires explicit later reconciliation; clocks, PID reuse guesses and fixture strings never clear ownership.

## Source and harmless Windows checks

Run the focused M2 tests in the deployed checkout using its locked dependencies. On Windows the four `test_tip057n_windows_owned_process.py` cases use only the current fixed Python executable: actual suspended creation/bind/resume, no-breakaway child containment and actual zero-active closure; pre-resume fault retention; parent-crash containment with durable blocked ownership; and expired post-create-attempt admission before any actual process creation. They are labeled `HARMLESS_WINDOWS_JOB_OBJECT_ONLY`, not REAL_MT5. The integrated exact-checkout workflow runs these as part of the full unit suite and retains JUnit/source manifests.

Physical MT5 activation, private VM provisioning, signing/installing approvals, target/account/provider selection and production deployment remain later operator work under the owner's deferred physical test plan.
