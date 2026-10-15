# TIP-057R-B1 — Isolated SDK read-worker source build

Date: 2026-10-03, Asia/Saigon. Status: DISPATCHED / REAL SDK QUALIFICATION DEFERRED. Parent PR #62 source `82d85fa43ee9670f66f158011c408b624500477b`.

Owner direction at 00:12:01+07:00: defer private VM testing, continue building the plan, test the real environment after build. This supersedes the Q2-before-source order for this bounded candidate. The isolated SDK-worker architecture remains selected. Real SDK compatibility, preventive no-start, production descendants, migration and activation are still unqualified. No further permission is needed for this authorized source/test build.

## Scope and YAGNI-3

Required output: a concrete SDK state/account read worker and a narrow Windows process adapter inside the research proof package. This makes the selected architecture testable after build without replacing existing live/native producers. Reuse LiveTerminal conversions, G03-A authority/lease/CAS/OS identity, and the frozen Q1 launcher via a narrow proof subclass; runtime never imports proof modules. The shortest implementation supports one state observation only, bounded file protocol, suspended create/bind/resume and exact cleanup. No product source change, generic launcher framework, persistent session transfer or broad producer migration.

Builder chooses files/patterns and submits Completion Report. Contractor verifies source, faults, Windows stub evidence and unchanged legacy behavior. This TIP deliberately reports SOURCE/RESEARCH BUILD status separately from SDK/Q2 qualification.

## Acceptance criteria

| AC | Required output |
|---|---|
| S01 | Controller imports no MetaTrader5 and worker imports SDK only after validating an exact bounded request; no credentials/login/trading/market/admin operation. |
| S02 | Request and result enforce fixed version/operation, safe absolute bindings, numeric budgets, byte caps and exact fields; invalid/extra/oversized inputs cause zero SDK import. No arbitrary exception text or secret/raw login in evidence. |
| S03 | Worker performs one exact-path initialize, verifies terminal roots before account/count access, uses existing masked/null conversion semantics, and performs shutdown even when initialize is false/raises. No retry/fallback. |
| S04 | Initialization/observation/shutdown faults and expiry preserve the primary failure, disclose cleanup uncertainty, and forbid successful account output. Monotonic timing and soft-budget overruns are truthful. |
| S05 | Windows adapter applies zero-capability AppContainer and child restriction at creation, excludes inherited handles, creates suspended, reads actual identity/restriction, and permits resume only after G03-A bind publication succeeds. Selected console mode; no no-console inference from Q1. |
| S06 | Harness durably arms/create-attempts before launch; publication/bind/resume/timeout/parent-recovery uncertainty retains ACTIVE and denies successor native admission. Waits and effects remain outside authority transactions. Exact process termination, never broad PID kill. |
| S07 | Worker exit or a result field never supplies production descendant qualification. SDK attempts keep authority ACTIVE/recovery-required until a qualified verifier exists. Only a separately labeled harmless synthetic leaf proof may demonstrate positive closure. No public force-clear. |
| S08 | Research execution is explicit, Windows fixture tests invoke only a harmless stub. Real SDK effect runner is not supplied in this build; the worker source is prepared for the later exact-environment qualification harness. No CLI flag masquerades as qualification. Product activation remains unavailable. |
| S09 | Portable tests exercise protocol/SDK faults/binding-before-account/null/masking/budget and ownership publication/cleanup order with clearly labeled synthetic adapters. Actual Windows harmless stub tests prove new adapter order, control viability, identity/termination and denial/retention; missing platform is not PASS. |
| S10 | Existing public facade/MCP/catalog/request hashes/dependencies/Q1 evidence remain byte-compatible. Q1/G03-A and relevant regressions PASS; real Python/AppContainer/DLL IPC and SDK no-start are explicitly NOT RUN/Q2 OPEN. |

## Delivery

Separate Draft source/test PR stacked on #62; no merge, deployment, VPS/MT5 action, SDK install/import on current environment, migration or activation. Document changed files, per-AC evidence, issues/deviations, exact candidate source hashes and next real-environment test commands. Any new producer phase/terminal transfer schema returns to Contractor before implementation.
