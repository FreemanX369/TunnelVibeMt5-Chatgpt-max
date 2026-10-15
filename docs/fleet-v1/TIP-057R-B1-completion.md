# TIP-057R-B1 — Isolated read-worker research build report

Date: 2026-10-03, Asia/Saigon. **DONE / RESEARCH BUILD PASS**, within the dispatched source/harmless-stub scope. Builder follows [the B1 TIP](TIP-057R-B1-build.md) from PR #62 `82d85fa43ee9670f66f158011c408b624500477b`. The owner deferred private VM testing at 00:12:01+07:00 and authorized source/tests first. This changes the build/test order, while Q2, real SDK/no-start, producer integration, migration and activation remain OPEN. Actual Windows source and documentation heads are verified in [Draft PR #63](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/pull/63); the Contractor confirms all seven workflows completed successfully at documentation head `047f45061ba50883ffa45cfc360a29cff3c9c8f2`.

## YAGNI-3 and output

1. A concrete worker and process adapter are needed to test the approved isolated SDK-worker architecture after the source build.
2. Reuse `LiveTerminal.state()` without changing its bytes, G03-A lease/authority/CAS/retained OS observations, and the frozen Q1 Windows boundary. Runtime never imports this proof package.
3. Build one state/account observation, a capped file protocol and a narrow fixed harmless-stub argv adapter. No generic launcher, scheduler, extra dependency, terminal transfer or product activation.

The worker's prepared private observation path validates before import, observes an exact retained process, performs one exact executable initialize, checks SDK installation/data roots before account/count access, reuses existing conversions, and attempts shutdown even after false/raised initialize. Budget/error handling preserves the earlier failure, discards late values, and separates shutdown uncertainty. Its CLI always returns `LIVE_ATTACH_ONLY_UNPROVEN` for a valid request, without SDK import. There is no real SDK effect runner in this build.

Protocol request/result are capped at 32 KiB; reads use cap+1 bytes. Exact fields/versions, state-only operation, nonce/request SHA256, absolute bindings, numeric budgets and typed output reject duplicate keys, nonfinite numbers, surrogate paths, invalid counts, unhashable malformed enums and raw login. Existing <=4-digit login corner receives one leading `*` in this research protocol; legacy source/output remains unchanged. `cleanup.status=RETURNED` means only SDK shutdown returned; it is **not** IPC/descendant/ownership qualification.

The new Windows adapter reuses Q1 declarations/profile/ACL/Process code without changing those files. It uses zero capabilities, child-process restriction, inherited console and no inherited handles; creates suspended; reads token/MIC/child policy from the actual handle; compares the full OS creation identity through independent G03-A observation; durably binds before resume. Creation-handle cleanup remains exact even if image/restriction readback fails. The native C stub performs only file/token/policy/Sleep operations. Its source SHA256 is pinned to `5ba0f5a8267555275e7428d45ca13b9a8d256d2b3e00297e83be25ee6056da45`; only compilation of that fixed source mints the fixture artifact, whose actual binary SHA256 is rechecked before creation and positive fixture closure.

Every attempted/uncertain controller path retains shared ACTIVE after lease release and denies successor native admission. SDK worker exit, shutdown return, caller result label and positive fixture receipt never provide production descendant qualification. Only a separately labeled, known harmless C leaf proof with matching bytes and actual restrictions can demonstrate fixture closure. The SDK disposition function always retains ACTIVE/activation unavailable.

## Changed files

Created proof files: `tests/proofs/tip057rb1/read_protocol.py`, `sdk_worker.py`, `controller.py`, `windows_adapter.py`, `fixture_stub.c`, `test_portable.py`, `test_controller.py`, `run_proof.py`. Created workflow `.github/workflows/verify-tip057rb1.yml`, this report and linked B1 TIP. Append-only continuation notes update Q2-P manifest/readiness, approval, task graph and fleet index; no historical decisions or unknown environment slots are relabeled.

All product `app/*`, old proof/tests/workflows, dependency/public schema/catalog/hash sources and historical Q1/G03-A evidence remain unchanged. This checkout retains earlier #62 documentation additions; those are parent bytes, not new B1 product changes. The Contractor verifies the actual parent/tree at publication; local Git HEAD is a synthetic work baseline and is not remote authority.

## Verification and acceptance map

Local invocation `python tests/proofs/tip057rb1/run_proof.py --portable --output <scratch>`: **39/39 PASS**, zero failure/error/skip. This is 31 synthetic protocol/worker tests plus eight synthetic controller faults using actual G03-A authority APIs. The Linux required-Windows invocation returns exit 2, `BLOCKED_REAL_WINDOWS_REQUIRED_NO_SKIP`, zero executed/skipped cases. Compileall and whitespace checks pass. Contractor independently reports retained Q1 portable 8/8 and G03-A 58/58 PASS; these counts are different retained suites, not new SDK tests.

Actual Windows Server 2025 build 26100 / Python 3.12.10 receipts now show **portable 39/39 and native stub 10/10 PASS**, with zero failure/error/skip, at both source head `41546a7d542f10f843edacb7f9f240b8c428ccbc` and documentation head `047f45061ba50883ffa45cfc360a29cff3c9c8f2`. Builder independently reopened both original downloaded ZIPs and verified bytes/digests, exact recorded heads and per-suite results. The Windows summaries contain 13 records spanning all ten unique actual native cases. These are synthetic SDK-domain tests and actual harmless C-process boundary tests, not real SDK/MT5 observations.

| Exact head / receipt | Original retained artifact | Compiled harmless binary SHA256 |
|---|---|---|
| Source `41546a7…`, [run 37042074019 / job 110954365603](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37042074019/job/110954365603) | Artifact `11242364217`, 8,062 bytes; SHA256 `1977ec1bb582f6a38feaa4482c5947fb704682fd24a4969600debf9707f45859` | `9a24ab3d70f096cd9366665b8182b3a7fb55591e74d590a0d58c899723474f79` |
| Documentation `047f450…`, [run 37042233179 / job 110954902581](https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/actions/runs/37042233179/job/110954902581) | Artifact `11241664297`, 8,065 bytes; SHA256 `06498e6d363f7f654d7ed74d8c38f3b468f4e32a33bc8ba901acd38148e2295a` | `7feab9b9e784ad9add9bc81063a71ed75c76ddedbfeb74623e1e86ea72a6ed42` |

Both receipts pin the same C source SHA256 `5ba0f5a8267555275e7428d45ca13b9a8d256d2b3e00297e83be25ee6056da45`; binary identities are reported per compilation without asserting reproducible PE bytes. The Contractor retains original artifacts and source/blob verification separately.

| AC | Source / local evidence | Actual Windows / SDK disposition |
|---|---|---|
| S01 | Strict validation before private loader; CLI SDK sentinel import remains absent; controller imports no SDK | Real SDK NOT RUN |
| S02 | Version/operation/exact fields/cap/budget/type/hash/nonce/path/Unicode/result tests PASS | Actual Windows portable 39/39 PASS at both verified heads |
| S03 | Exact initialize; root-before-account; masked/null conversion; false/raised init shutdown-once tests PASS with synthetic SDK | Real SDK lifecycle OPEN |
| S04 | Initialize/observation/shutdown faults, overrun, cleanup precedence, late result rejection PASS synthetic | Real SDK interruption/termination OPEN |
| S05 | Adapter source uses preventive attributes, OS readback, full lifetime check, suspended bind/resume | Actual Windows W01/W02/W06/W07/W10 PASS, known harmless C stub only |
| S06 | Arm/attempt/bind publication/refusal and interruptions across fresh authority deny successor PASS synthetic | Actual Windows publication/resume/timeout/crash W03/W05/W06/W09/W10 PASS in the harmless-stub scope |
| S07 | SDK-label rejection, stale CAS, explicit synthetic verifier refusal, `SDK_DESCENDANTS_UNQUALIFIED` PASS | Actual Windows fixture-only positive closure/tamper refusal W02/W08 PASS; production verifier ABSENT |
| S08 | No product entry/import, no real effect command, SDK CLI always denies | Q2/private VM deferred |
| S09 | 39 required portable cases PASS without skips; ten required native Windows cases implemented | Actual Windows 10/10 PASS at both verified heads; missing Windows remains BLOCKED, not skipped PASS |
| S10 | Existing product/public/dependency/Q1 sources untouched; retained checks PASS | Exact candidate B1 Windows PASS; Contractor confirms 7/7 workflows PASS at verified documentation head `047f450…` |

Ten required Windows cases cover matched working unrestricted control, restricted protocol/order/fixture closure, stuck worker exact termination, missing/wrong-nonce response, bind publication faults before/after, failed restriction readback cleanup, wrong creation identity, artifact tamper, actual parent crash and successor denial, and resume uncertainty before/after the effect. Each uses only the harmless native stub. Case counts are fixed, no skips may pass. Compiler waits cap45s, parent harness55s, exact cleanup5–10s; output/log/summary limits cannot yield truncated PASS. The workflow checks actual PR-head Git blobs with autocrlf disabled and retains raw source/platform/binary/OS identity/marker evidence.

## Issues, deviations and next checks

No known correctness blocker remains within this research build. Actual harmless Windows execution is now verified on CI, while this local checkout is Linux. Python-in-AppContainer, wheel/DLL staging, IPC compatibility, deterministic SDK no-start race, broker/escape paths, real SDK shutdown/recovery and physical maintenance are explicitly **NOT RUN / Q2 OPEN**. A compiled harmless leaf cannot qualify them. No real SDK install/import, MT5/VPS/account/credential/AutoTrading action, migration, merge or deployment occurred.

Sequencing deviation is owner-authorized: source build precedes private VM qualification. The research short-login mask and `RETURNED` cleanup label prevent misleading evidence without modifying the legacy converter. The fixed native fixture artifact provenance is proof-only; no production signing or descendant-verifier framework is introduced.

Next verification commands on CI: `python tests/proofs/tip057rb1/run_proof.py --portable --output tip057rb1-portable` and `python tests/proofs/tip057rb1/run_proof.py --require-windows --output tip057rb1-windows`. The worker CLI takes request/result paths but always denies real effects. After the owner supplies the actual Q2 manifest, a separately reviewed VM harness must qualify this prepared private observation path on exact SDK/roots/session/broker traces; there is intentionally no current real SDK effect command.
