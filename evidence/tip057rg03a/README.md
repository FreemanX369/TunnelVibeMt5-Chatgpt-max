# TIP-057R-G03-A local receipts

The `local-*` receipts are LOCAL / source-only / Windows-unqualified. Their local HEAD is a synthetic baseline, not a published candidate. See `local-source-manifest.json` for their final file hashes and validation basis. Actual source-head Windows receipts are separately retained below.

- `local-interim-q1-portable-failure*`: retained initial 8-case portable Q1 attempt, 7 INSTALL_MISSING errors before explicit disposable-root fixture migration. This failure is historical and is not relabeled as PASS.
- `local-final-scoped.log`: final refined source, 121 passed and 2 existing Windows-only platform skips. New G03-A portable cases have no skips.
- `local-before-queue-refinement-full.log`: 396 passed and 26 existing platform skips, before the final ticket/owner cleanup refinements and native-only contention additions. The final changed paths were rerun in the scoped suite; an exact-head full Windows run is pending.
- `local-final-q1-portable*`: final refined source, 8 portable cases, zero failures/errors/skips. This is not a Windows preventive qualification.
- `local-final-windows-required-negative*`: required-Windows runner invoked on Linux, exits 1 with REAL_WINDOWS_REQUIRED_NO_SKIP, zero executed cases and zero skips. This is BLOCKED, not PASS.

The seven original Q1 CI metadata receipts and their retained logs/artifacts under `docs/fleet-v1/evidence/tip057rq` remain byte-identical (27 files verified). No terminal, SDK, account, credential, AutoTrading, VPS or production migration action ran here.

## Actual source-head Windows receipts

`ci-source-bc916796.json` binds actual workflow heads/outcomes, jobs, original artifact ZIP digests, per-file/source/blob hashes and unique test case names to `bc9167969d67d288c37a4ce9aa5854a0bf2db14d` in Draft PR #62. Contractor downloaded and verified original bytes before marking the foundation PASS.

- `windows-source-bc916796/`: G03-A required Windows run 37025462023, 8/8, zero errors/failures/skips. Original artifact ZIP, summary and proof log retained unchanged; decoded job log retained separately. Status G03A_WINDOWS_FOUNDATION_PASS_PRODUCER_OPEN.
- `q1-source-bc916796/`: retained Q1 run 37025462247, 16/16, zero errors/failures/skips. Original ZIP, summary/compiler/proof bytes plus decoded job log. Status FIXTURE_PASS_Q03_OPEN.
- `baseline-source-bc916796/`: decoded original job logs for the four retained workflows. TIP-053/TIP-034 full Windows suites each report 424 PASS/4 existing skips. The baseline PR merge checkout `12f6b67d7a10af0aca1e2bd2bc5709457da8c8fd` has exactly candidate tree `e9bd991b173d3c05581ac4c9aad3dd2e2eebd745`; dedicated G03-A/Q1 use the exact candidate HEAD.

Final documentation-head CI links/digests are recorded in PR metadata, preserving this immutable source evidence without a recursive evidence commit. Producer/SDK qualification and physical migration remain OPEN.
