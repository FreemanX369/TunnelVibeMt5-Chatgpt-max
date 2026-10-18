# TIP-057R-G03-A Contractor verification

Status: **DONE FOR G03-A / FOUNDATION PASS / PRODUCER OPEN**. This is the bounded source/test amendment approved by the owner at 2026-10-02T21:21:49+07:00, based on Draft PR #61 head `0ee42c9cdc677926e3f27d02592c1ad9fc498c8d`. Reviewed implementation head: `bc9167969d67d288c37a4ce9aa5854a0bf2db14d`, tree `e9bd991b173d3c05581ac4c9aad3dd2e2eebd745`, Draft PR #62. It does not qualify deployment or full G03.

Contractor reviewed the Builder's source, meaningful tests, retained failures and [Completion Report](TIP-057R-G03A-completion.md), plus the independent read-only SCAN. Builder owns all product/proof/test changes. Contractor owns approval records, publication and output verification. The synthetic local baseline is never treated as a remote parent or exact-head receipt.

## Reviewed boundary

Only three product paths change: `core/native_ownership.py`, `core/concurrency.py` and `core/jobs.py`. Native admission and stale deletion share the short ownership transaction; central cancel restoration obtains a real native lease. Ordinary release never closes durable ownership. Runtime does not import a proof, install a root, reset missing state or expose a force-clear API. Public entry/catalog/hash/dependency sources and worker/facade/backend implementation remain unchanged.

Independent live process observation, owned-token/parent checks and exact snapshot CAS constrain the internal producer interface. Fresh already-dead identity refuses qualification. Positive descendant-verifier strings in harmless fixtures are interface evidence only; no production verifier or existing producer integration is supplied. ACTIVE and invalid roots deny existing native effects. A valid explicitly installed CLOSED root retains historical admission; uninstalled guard-capable source deliberately denies it, so this source must not be rolled out before a controlled installation/version/rollback design.

Reviewed refinements normalize guard/process/verifier failures, preserve same-object release behavior, keep restore pending on queue/lease failures and clean exact newly created ticket/owner paths when admission fails before returning a lease. FIFO waits, process waits, SDK effects and descendant callbacks are outside the authority transaction. Multiprocess tests propagate child failures and assert capacity/order.

## Local evidence and publication gate

The final affected suite reports **121 PASS, 2 existing platform skips, zero failures/errors**; its 60 new G03-A portable cases have no skips. Final Q1 portable reports **8/8**, zero skips, and remains Windows-unqualified. Required Windows invocation on Linux correctly reports **BLOCKED / REAL_WINDOWS_REQUIRED_NO_SKIP**, zero executed cases. The earlier full suite's **396 PASS / 26 skips** predates the final acquisition cleanup and native-only contention refinements and is not a final-source full receipt. Initial Q1 portable failure (7 INSTALL_MISSING errors) is preserved without relabeling.

Raw local receipts and frozen SHA256 values are under `evidence/tip057rg03a`. All 27 historical Q1 receipt files must remain byte-identical to the approved parent. Contractor checks every local file's Git blob/mode against the published tree before moving the branch. The separate Draft PR targets main to trigger the five retained workflows plus the dedicated eight-case Windows G03-A workflow; its body declares the #61 dependency and links the approved-parent delta. Neither PR is merged by this step.

A08/A14 are now verified for the approved foundation. Contractor downloaded original exact-head Windows artifacts and validated ZIP/file/source/blob hashes, per-case results and raw logs. All six workflows independently report the actual candidate head above and completed/success. No source refinement was needed after publication. The evidence binds immutable source head results; final docs-only head CI is recorded separately in the PR body without a recursive evidence commit.

## Actual Windows and AC output verification

Platform: Windows Server 2025, build 10.0.26100; CPython 3.12.10 x64. [Source CI metadata](../../evidence/tip057rg03a/ci-source-bc916796.json) records six actual run heads, job outcomes, artifact digests, source hashes, raw-file hashes and unique case names. Original ZIPs, summaries, proof/compiler logs and decoded job logs are retained under `evidence/tip057rg03a`, alongside the local failures. All 27 original Q1 evidence files remain unchanged.

| Source-head workflow | Verified outcome |
|---|---|
| [G03-A Windows 37025462023](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025462023) | 8/8 PASS, zero failures/errors/skips; 11 scenario records across eight unique cases; elapsed 1,390 ms; G03A_WINDOWS_FOUNDATION_PASS_PRODUCER_OPEN |
| [Q1 Windows 37025462247](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025462247) | 16/16 PASS, zero failures/errors/skips; full suite attempted; elapsed 15,250 ms; FIXTURE_PASS_Q03_OPEN |
| [TIP-053 37025462241](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025462241) | Full Windows unit suite: 424 PASS, 4 existing platform/environment skips, 36.46 s |
| [TIP-034 37025462208](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025462208) | Fresh Windows import/catalog/bootstrap and full unit suite: 424 PASS, 4 existing skips, 40.49 s |
| [TIP-027 37025462009](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025462009) | Continuity regressions: 20 PASS; ordered catalog PASS |
| [TIP-028 37025461890](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37025461890) | Binding contract and compilation PASS |

The four full-suite skips are two absent deployed MT5/VPS-root cases and two POSIX path fixtures; none is a new G03-A or required Windows proof case. Dedicated G03-A/Q1 check out the exact candidate head. Retained baselines use GitHub PR merge checkout `12f6b67d7a10af0aca1e2bd2bc5709457da8c8fd`; Contractor fetched that actual merge commit and verified its tree is exactly candidate tree `e9bd991b173d3c05581ac4c9aad3dd2e2eebd745`. Both full-suite runs therefore exercise the same final product/test bytes, without claiming their literal checkout HEAD was the candidate. Fixture elapsed times are observations, not production deadlines.

| AC | Contractor conclusion for the bounded TIP |
|---|---|
| A01 | PASS: real multiprocess FIFO/capacity/order plus retained successful-output/dead-owner CLOSED regressions; full Windows baseline PASS |
| A02 | PASS: actual product entry paths deny ACTIVE before all mocked native effect callbacks, with callback counts zero |
| A03 | PASS: central cancel/get_job/startup path holds real lease for restore or returns durable pending; read/registration remain usable |
| A04 | PASS: actual Windows live PID with schema-valid mismatching creation retains ACTIVE lock; CLOSED recovery remains compatible |
| A05 | PASS within approved snapshot boundary: invalid installation/publication windows deny; real Windows bind/close faults retain ACTIVE on writable storage |
| A06 | PASS for internal interface: actual suspended create, durable bind before resume and exact retained-handle exit; interrupted creation stays unknown; descendant callback remains unqualified for production |
| A07 | PASS: multiprocess recovery/acquire and stale-CAS tests; independent Windows live observation and successor generation protection |
| A08 | PASS: fresh already-dead Windows observation refuses despite expected journal image; independently retained live handle proves exit separately |
| A09 | PASS within epoch/snapshot contract: MIGRATING/interrupted/old-epoch publication remains blocked; physical rollback, mixed versions and same-epoch valid CLOSED replay remain OPEN |
| A10 | PASS: only three product paths change; public contract/dependency/worker/facade/backend sources unchanged; no helper/installer/public recovery API |
| A11 | PASS: exact job stop stays separate from pending ownership restoration; historical complete receipt does not close authority |
| A12 | PASS: ordinary release/unlink and failed unlink preserve ACTIVE; successor denial and legacy release/retry regressions retained |
| A13 | PASS: short-guard/lock-order source review plus real contention/effect reentrancy; no hard production deadline claim |
| A14 | PASS: all six exact-head workflows, eight mandatory Windows cases without skips, source/blob/original artifact/raw log validation and retained historical receipts |

G03-A artifact `11234742196`: 2,317-byte ZIP, SHA256 `170d84f95b4ed29716835ebef4f6a883a8f4facf6ac9c1e1a3929d3112ec3b24`. Raw proof log: 1,437 bytes, SHA256 `fcb041a3e1c169d731be0d1e334b15904b29e8eb97ea5ac09d3226f0e47f87fb`. All eight source hashes match both Git blobs and frozen reviewed bytes.

Q1 artifact `11234907133`: 8,870-byte ZIP, SHA256 `b6b5719cad63b25f3495a2d9398777e0021b9370d6faca987593a90d3d2720fd`. Original proof log: 2,272 bytes, untruncated, SHA256 `784a696a9cd7cd2d0527504f18185d2aeabaa2c6b446e8489e57fa0e9a5385a2`. Four proof-source hashes match frozen reviewed bytes and Git blobs. The unchanged Q03 limitations remain in force.

## Remaining capability gates

No production helper/SDK, target/live_read, full producer/cleanup integration, qualified descendants, late-dead recovery liveness, physical migration/version fencing/rollback, G04, Q2 or M1 capability is closed here. Valid same-epoch old CLOSED replay, mixed old binaries and power-loss/administrator tamper resistance are not fenced by this JSON foundation. Close-write/readback fault tests prove best-effort prior-ACTIVE restoration on writable storage; simultaneous rollback/storage failure cannot guarantee persisted ACTIVE. No production state, MT5/VPS/account/credential or AutoTrading action is authorized or performed by this source task. TIP-056 retains its TIP-060/M4 dependency.
