# TIP-057R-G03-A local receipts

These receipts are LOCAL / source-only / Windows-unqualified. The local HEAD is a synthetic baseline, not a published candidate. See `local-source-manifest.json` for the final file hashes and validation basis.

- `local-interim-q1-portable-failure*`: retained initial 8-case portable Q1 attempt, 7 INSTALL_MISSING errors before explicit disposable-root fixture migration. This failure is historical and is not relabeled as PASS.
- `local-final-scoped.log`: final refined source, 121 passed and 2 existing Windows-only platform skips. New G03-A portable cases have no skips.
- `local-before-queue-refinement-full.log`: 396 passed and 26 existing platform skips, before the final ticket/owner cleanup refinements and native-only contention additions. The final changed paths were rerun in the scoped suite; an exact-head full Windows run is pending.
- `local-final-q1-portable*`: final refined source, 8 portable cases, zero failures/errors/skips. This is not a Windows preventive qualification.
- `local-final-windows-required-negative*`: required-Windows runner invoked on Linux, exits 1 with REAL_WINDOWS_REQUIRED_NO_SKIP, zero executed cases and zero skips. This is BLOCKED, not PASS.

The seven original Q1 CI metadata receipts and their retained logs/artifacts under `docs/fleet-v1/evidence/tip057rq` remain byte-identical (27 files verified). Actual candidate-head Windows execution and source/blob receipts must be collected after Contractor publication. No terminal, SDK, account, credential, AutoTrading, VPS or production migration action ran here.
