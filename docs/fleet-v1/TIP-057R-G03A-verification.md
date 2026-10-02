# TIP-057R-G03-A Contractor verification

Status: **LOCAL FOUNDATION PASS / ACTUAL WINDOWS PENDING**. This is the bounded source/test amendment approved by the owner at 2026-10-02T21:21:49+07:00, based on Draft PR #61 head `0ee42c9cdc677926e3f27d02592c1ad9fc498c8d`. It does not qualify deployment or full G03.

Contractor reviewed the Builder's source, meaningful tests, retained failures and [Completion Report](TIP-057R-G03A-completion.md), plus the independent read-only SCAN. Builder owns all product/proof/test changes. Contractor owns approval records, publication and output verification. The synthetic local baseline is never treated as a remote parent or exact-head receipt.

## Reviewed boundary

Only three product paths change: `core/native_ownership.py`, `core/concurrency.py` and `core/jobs.py`. Native admission and stale deletion share the short ownership transaction; central cancel restoration obtains a real native lease. Ordinary release never closes durable ownership. Runtime does not import a proof, install a root, reset missing state or expose a force-clear API. Public entry/catalog/hash/dependency sources and worker/facade/backend implementation remain unchanged.

Independent live process observation, owned-token/parent checks and exact snapshot CAS constrain the internal producer interface. Fresh already-dead identity refuses qualification. Positive descendant-verifier strings in harmless fixtures are interface evidence only; no production verifier or existing producer integration is supplied. ACTIVE and invalid roots deny existing native effects. A valid explicitly installed CLOSED root retains historical admission; uninstalled guard-capable source deliberately denies it, so this source must not be rolled out before a controlled installation/version/rollback design.

Reviewed refinements normalize guard/process/verifier failures, preserve same-object release behavior, keep restore pending on queue/lease failures and clean exact newly created ticket/owner paths when admission fails before returning a lease. FIFO waits, process waits, SDK effects and descendant callbacks are outside the authority transaction. Multiprocess tests propagate child failures and assert capacity/order.

## Local evidence and publication gate

The final affected suite reports **121 PASS, 2 existing platform skips, zero failures/errors**; its 60 new G03-A portable cases have no skips. Final Q1 portable reports **8/8**, zero skips, and remains Windows-unqualified. Required Windows invocation on Linux correctly reports **BLOCKED / REAL_WINDOWS_REQUIRED_NO_SKIP**, zero executed cases. The earlier full suite's **396 PASS / 26 skips** predates the final acquisition cleanup and native-only contention refinements and is not a final-source full receipt. Initial Q1 portable failure (7 INSTALL_MISSING errors) is preserved without relabeling.

Raw local receipts and frozen SHA256 values are under `evidence/tip057rg03a`. All 27 historical Q1 receipt files must remain byte-identical to the approved parent. Contractor checks every local file's Git blob/mode against the published tree before moving the branch. The separate Draft PR targets main to trigger the five retained workflows plus the dedicated eight-case Windows G03-A workflow; its body declares the #61 dependency and links the approved-parent delta. Neither PR is merged by this step.

A08/A14 remain pending until Contractor downloads original exact-head Windows artifacts, validates ZIP/file/source/blob hashes, per-case results and raw logs, and verifies all six workflows on the candidate. Any CI refinement stays within this approved source/test slice and retains unsuccessful receipts. The final report must bind observed results to immutable source heads; docs-only follow-up CI is separately identified.

## Remaining capability gates

No production helper/SDK, target/live_read, full producer/cleanup integration, qualified descendants, late-dead recovery liveness, physical migration/version fencing/rollback, G04, Q2 or M1 capability is closed here. Valid same-epoch old CLOSED replay, mixed old binaries and power-loss/administrator tamper resistance are not fenced by this JSON foundation. Close-write/readback fault tests prove best-effort prior-ACTIVE restoration on writable storage; simultaneous rollback/storage failure cannot guarantee persisted ACTIVE. No production state, MT5/VPS/account/credential or AutoTrading action is authorized or performed by this source task. TIP-056 retains its TIP-060/M4 dependency.
