# TIP077 — reviewed source correction

2026-10-11. Implementation and independent local verification **PASS**; fresh exact-head CI and release acceptance remain pending. Parent `4757afbdd5c8fa399b41ff897c5baaa7a2ed1dfd` remains historically rejected at 6/8 workflows. The [contract](TIP-077-capacity-entry-watchdog.md) supplies the approved boundary and classification.

One initial capacity fixture call now explicitly uses the existing ten-second pump budget. Two actual-TLS regressions prove the positive callback/release assertion survives a finite component schedule and that the original three-second helper still fails boundedly with its exact prerequisite/CALLBACK/SCOPE_RELEASE union. Original names and assertions are unchanged. This is an intentional positive test watchdog correction, not a production latency fix.

## Verification

| Check | Result | Time / process cap |
| --- | --- | --- |
| Original three-case TLS proof, Builder | 3 PASS | 8.359 s JUnit / 90 s |
| Same frozen proof, independent Contractor | 3 PASS | 8.340 s JUnit / 90 s |
| Final new positive control against untouched parent | Expected RED at original callback-union assertion | 4.582 s process / 60 s |
| Final new candidate controls, Builder | 2 PASS | 8.289 s process / 60 s |
| Compatible eight modules, earlier new-control bytes | 190 PASS / 3 original Windows skips | 67.859 s process / 300 s |
| Final frozen controls, independent Contractor | 2 PASS | 8.241 s process / 60 s |
| Final frozen full unit suite, independent Contractor | 1,529 PASS / 41 original environment skips, 1,570 cases | 124.623 s JUnit, 126.280 s process / 600 s |

All processes completed without timeout; retries zero. The earlier 190-case result is retained under its earlier new-test digest, before the final unexpected-transport-error preservation loop. The final two controls and full suite verify the final digest. The actual parent import path was separate and unchanged; no copied candidate fixture was substituted into the parent.

All 225 source hashes remained exact before/after independent verification. Of the parent's 224 entries, 223 remain identical; only the existing capacity test caller changes. All 89 application entries, dependencies, workflows, deployment-overlay mapping, HTTP/control policies, signed TTLs, one-second SQLite/FIFO boundary, FULL/WAL/checkpoint, guard through file close, cleanup and full-process budgets remain unchanged. Source freeze:

- `tests/unit/test_tip064_capacity_https.py`: SHA256 `9eaf5a317a54720b6e95f5bbfadeeabb5720483954a50ea7828936d9d053c917`.
- `tests/unit/test_tip077_capacity_entry_watchdog.py`: SHA256 `3abe4f2c8b54feea4658fc5458ca594d08c7e8c71ca7a34159ade05382078abf`.

Contractor checked all 22 Builder evidence-manifest payload hashes. Raw logs, complete JUnit, before/after source manifests, immutable prior control receipts and standalone proof evidence are retained in the dated external evidence package; they are not regular-unit file-writing behavior.

## Publication and acceptance boundary

Publish these two test files plus this completion and the contract as one reviewed tree to draft PR65 with expected-parent CAS and force=false. Require eight fresh exact-head original-attempt workflows and independently verified official source/proof artifacts. Local Linux passes do not qualify Windows ownership behavior. Do not rerun the old failures or call the candidate accepted from the retained parent's six successful workflows.

The original Windows v7 research completed FAILURE, not timeout. No previous Builder was active when the owner resumed after approximately 22 hours; the previous turn had ended BLOCKED. ChatGPT UI stall cause is unobserved. Current runtime remains healthy legacy TIP053/0.2.42, not the full Fleet source candidate.

Separate historical FIFO-release one-second, long-observation ten-second and integrated six-hundred-second failures remain unresolved. No physical I/O owner is established and no guard/authority/UNKNOWN behavior changes. Existing authorized legacy overlays and direct live observations remain their own receipts; full Fleet activation, connector visibility and private VM/MT5/real SDK qualification remain OPEN. No runtime write, restart, native operation, credential/account/AutoTrading change or main merge occurs in TIP077.
