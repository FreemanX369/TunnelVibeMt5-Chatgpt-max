# TIP-058A independent verification

Date: 2026-10-03. Status: Linux source verification PASS; Windows source CI remains to be recorded by Contractor. This is a code/fixture checkpoint and does not qualify MT5, a private VM, SDK attachment, production TLS deployment, physical clone uniqueness or live dispatch.

Vibecode Kit v6 was used for SCAN → focused acceptance tests → VERIFY → REFINE. YAGNI-3: durable authority needs substantive fault/replay tests; reuse pytest, stdlib SQLite and real cooperative subprocesses; add focused acceptance cases rather than a second control implementation. QA changed only its assigned test/report/evidence files; the product Builder applied source refinements.

## Actual result and source identity

Final local run: **306 passed, 3 existing platform skips in 8.83 seconds**, exit 0. The assigned gateway suite contributes **120 passing cases, no Linux skips**; the retained C1/G03A/M0 identity/release suites contribute 186 passes and their three existing platform skips.

The final record is [focused.log](evidence/tip058a/linux-source-v4/focused.log), [JUnit](evidence/tip058a/linux-source-v4/focused.junit.xml) and [source manifest](evidence/tip058a/linux-source-v4/source-manifest.json). Before/after SHA-256 values match for all eight captured source/test paths. Prior raw runs are retained in `linux-source`, `linux-source-v2`, and `linux-source-v3`; v4 is the latest acceptance record.

| File | SHA-256 | Git blob |
|---|---|---|
| `app/vibemql5/fleet/gateway_control.py` | `21d0dd452fbce40cf6eee8e30aedd6f77e17b96bd1b062c47e1e075566789939` | `08d4e5cd088b94ea892e2690ef81fb843a7a6881` |
| `tests/unit/test_tip058a_gateway_control.py` | `42fb7cdd29a94e29ef79e0b2a03773cb541a37d30f29bd5ac94c0b2352e303f4` | `a8ef9c43963a1bf762e3e780ed85e2289a03580c` |

Run from the repository root with Python 3.12 and the retained locked test dependencies:

```sh
python -m pytest tests/unit/test_tip058a_gateway_control.py tests/unit/test_tip057rc1.py tests/unit/test_tip057rg03a_native_ownership.py tests/unit/test_tip055a_runtime_forensics_identity.py tests/unit/test_tip055b_runtime_forensics_release.py -q --tb=short --junitxml=focused.junit.xml
```

## Acceptance coverage

| AC | Linux evidence |
|---|---|
| A01 | Explicit initialize/open-existing/closed behavior; canonical/symlink/hardlink handling; actual spawned cooperative writer denial and OS release after deliberate process exit; wrong-thread snapshot/close keeps authority locked; bounded SQLite contention. |
| A02 | WAL/versioned schema; missing/corrupt/unknown version, column or trigger rejected; strict primitive inputs; current device/grant/receipt relational corruption rejected; no gateway-owned terminal generation. |
| A03 | Required policy, bool/nonfinite/missing/invalid relationship rejection, practical mechanism ceilings, mismatched reopen refusal. Every fixture chooses its profile explicitly. |
| A04 | Initial-only secret return; no plaintext in persisted files/snapshot/public receipt; wrong device/key/secret/expiry/used/original-route CAS refusal; all-or-none consume. |
| A05 | Durable identical replay after reopen with original CAS; changed request conflict; operation capacity does not evict receipts; secret cannot be recovered from digest. |
| A06 | Pair → revoke → re-pair → rotation increments the gateway route generation; stale key/route admission fails; query/reopen retains authority. |
| A07 | Durable nonce replay separate from logical replay; stale/future/rollback/invalid times fail; ±clock-skew boundaries accepted with complete retention; exhausted capacity refuses eviction; key+route checked at nonce insertion. |
| A08 | Before/after commit exception faults for grant, pair and nonce; actual process interruption on grant/pair commit boundaries; initialize/restore publication faults; sanitized bounded errors and original-or-committed state. |
| A09 | SQLite backup consistency; corrupt/policy-mismatched source refusal; supported restore publishes durable `RECONCILIATION_REQUIRED` before admission, including after publication uncertainty; no unconditional ready/clear API. |
| A10 | Current 85 actual MCP schemas/catalog remain at C1 baseline; retained C1/G03A/M0 regressions pass; no network, MT5, SDK, VPS or provisioning performed by this suite. Windows CI must run the same source before final handover. |

The concrete B control hook is also verified directly as a trusted internal fixture: signed-route-zero is confined to `PAIR`, current-route admission still requires generation ≥1, grant/route/nonce/logical receipt share one commit, fresh-nonce logical retry after reopen returns the original receipt, repeated nonce refuses, reserved `nodepair:` namespace cannot be used by administrative APIs, and revoked/rotated/re-paired authority cannot be repainted. These hook tests do not stand in for B's real Ed25519/HTTPS tests.

## Refinements verified

Independent tests first exposed accepted unknown schema definitions and invalid PAIR receipts. Product refinements now enforce exact schema objects, operation-specific receipt fields/states, canonical receipt JSON and cross-record authority consistency. Review also found the administrative/pair namespace collision and wrong-thread close risk; reserved namespace checks and owning-thread enforcement are covered. Every original failing corruption case now passes alongside ordinary reopen/replay.

This consistency checking detects accidental or partial record corruption. It cannot authenticate a coherently rewritten SQLite database, detect an out-of-band old valid backup using SQLite alone, prove cryptographic enrollment from a public-key reference, or reconcile independent node journals by itself. Those capabilities remain governed by their later TIPs and physical qualification records. The Contractor continues the already-authorized source plan without a per-TIP approval stop.

## First Windows checkpoint and test refinement

Draft #65 source `df0e0c1d62fe22704e51a3c46a8caab1ddbb0368` passes five retained workflows. The two Windows full-unit workflows each report 604 passes, one failure and five skips. The failure is the secrecy test reading the mandatory-locked owner byte while the store is open; it is not a plaintext-secret observation. [Decoded logs and receipt](evidence/tip058a/windows-source-df0e0c1/receipt.json) are retained, including both failed job logs. The five skips comprise four retained baseline skips and one intentional POSIX symlink-spelling case on Windows.

QA refined the test to inspect DB/WAL files during the open store, then inspect the owner lock only after actual close. No PermissionError suppression or secrecy skip was added. Amended test SHA-256 `88f050931b50ab6924e15a728cc60f5eea8dae8a1d53add787cc2edbf40ab3a5`, blob `a80f78ad6611069a5d78ad74fa3b19fddd15ad85`; the frozen A product blob remains `08d4e5cd088b94ea892e2690ef81fb843a7a6881` in this isolated refinement checkpoint. Windows acceptance requires the new exact-head rerun; later 060C control extensions have their own source identity and do not retroactively change this A receipt.
