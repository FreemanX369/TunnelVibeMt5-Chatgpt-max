# TIP-057R-B1 — Contractor verification

Date: 2026-10-03, Asia/Saigon. Result: **B1 RESEARCH BUILD PASS / REAL SDK Q2 DEFERRED**. Owner approved source-first build at 00:12:01+07:00. This certifies the [bounded B1 TIP](TIP-057R-B1-build.md) and [Builder report](TIP-057R-B1-completion.md), not full G03-B producer integration or usable targeted IPC.

## Verified source and scope

Source head `41546a7d542f10f843edacb7f9f240b8c428ccbc`, tree `4a61742322ee3b1b812188776a8e1973d028bf29`; documentation head `047f45061ba50883ffa45cfc360a29cff3c9c8f2`, tree `af7487dc48ebe2131bd9c7a8d25d481312258861`. Both descend from #62 `82d85fa43ee9670f66f158011c408b624500477b`. All 16 B1 delta contents were fetched from GitHub and matched the frozen candidate. GitHub comparison reports exactly these 16 paths, no unexpected change. App, dependencies, legacy schemas/signatures and historical Q1/G03-A bytes are inherited unchanged. Independent read-only source/AC review is CLEAR after bounded corrections to protocol typing, primary-error precedence, full process identity, fixture artifact provenance and crash cleanup.

Contractor independently ran 39/39 B1 portable/controller cases, retained Q1 portable 8/8 and G03-A 58/58. Initial G03-A harness invocation lacked pytest; the actual 58-case check used the existing cached dependency environment. This setup error is separate from source results. Linux required-Windows refusal remains BLOCKED, never a skipped PASS.

## Actual Windows receipts

| Head | Run / job | Original ZIP bytes / SHA256 |
|---|---|---|
| `41546a7` | [37042074019](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37042074019) / 110954365603 | 8062 / `1977ec1bb582f6a38feaa4482c5947fb704682fd24a4969600debf9707f45859` |
| `047f450` | [37042233179](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37042233179) / 110954902581 | 8065 / `06498e6d363f7f654d7ed74d8c38f3b468f4e32a33bc8ba901acd38148e2295a` |

Both actual Windows executions: **39 portable + 10 harmless native cases PASS, zero failures/errors/skips**, 13 scenario records spanning all ten unique Windows cases. Exact-head requirement was active. Every executed source byte length, SHA256 and Git blob matches frozen local source; original proof-log bytes/digests match summary metadata without truncation. Original textual archive members are retained byte-for-byte under [source receipts](../../evidence/tip057rb1/source-41546a7) and [documentation-head receipts](../../evidence/tip057rb1/docs-047f450). ZIP digest/size also matches GitHub artifact metadata (11242364217 and 11241664297).

S01–S04 establish protocol/private synthetic SDK behavior; S05–S06 use actual suspended restriction/identity/bind/resume, timeout, publication and parent-crash receipts; S07 establishes only qualified known C leaf closure and keeps SDK ownership ACTIVE; S08 CLI denies real effects; S09 has the exact 39/10 counts with no skipped gate; S10 preserves prior source and workflows. The C source is pinned; per-run binaries have different hashes and no reproducible-build inference is made. SDK shutdown RETURNED is a call outcome, not ownership proof.

All seven workflows at documentation head `047f450` were independently read as completed/success: TIP-027 (37042233174), TIP-028 (37042233215), TIP-034 (37042233178), TIP-053 (37042233222), Q1 (37042233272), G03-A (37042233188) and B1 (37042233179). This final verification/evidence commit changes documentation only; subsequent final-head CI is recorded in PR #63 to avoid recursive evidence commits.

## Remaining gates

Real Python/AppContainer/DLL IPC, pinned SDK/two clean bindings, stopped/race zero-birth trace, broker/escape, production descendant reconciliation, producer integration and physical migration remain OPEN. Source build precedes private VM testing as the owner requested. No product activation, VPS/MT5 operation, account/credential/AutoTrading change, merge or deployment occurred. TIP-056 remains after TIP-060/M4.
