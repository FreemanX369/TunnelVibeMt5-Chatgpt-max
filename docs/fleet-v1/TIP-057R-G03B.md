# TIP-057R-G03-B — Producer lifecycle and migration decision contract

Date: 2026-10-02, Asia/Saigon. Status: **DESIGN REVIEW / PRODUCT BUILD NOT DISPATCHED**. Owner continuation “Duyệt bước tiếp theo”, 2026-10-02T22:56:16+07:00, approves the next step stated after G03-A: prepare this producer/cleanup and migration contract. Reviewed source authority is Draft PR #62 head `08835894837c54f35381c797fa27ace6cd92a2b1`, tree `0aeddc861501c2be6f5482becfbd060f2b0bb766`; main remains `70e2112da9fe8eaa6262f2ba896b55bf3e078260`. This planning addition changes no product, test, dependency, workflow or retained evidence bytes.

Dependencies: [G03-A output verification](TIP-057R-G03A-verification.md), [Builder producer scan](TIP-057R-G03B-source-scan.md), [feasibility review](TIP-057R-G03B-feasibility.md), approved [boundary amendment](TIP-057R-boundary-amendment.md) and [Q2 readiness](TIP-057R-Q2-readiness.md). Maps REQ-F04/F10/F11/F14/F15. Contractor owns this decision contract; Builder supplies source facts and later implements an approved bounded TIP.

## Finding and selected recommendation

G03-A protects common admission and restoration when authority is unresolved. It deliberately does not create durable intent around existing effects. Its only positive closures are ARMED with proven zero attempts, or a BOUND independently observed worker that has actually exited with qualified descendants. Existing LiveTerminal/MT5Preflight calls initialize in a controller or native-job worker that must remain alive. After an initialize attempt, neither closure describes that process. Calling arm around those callbacks without a new lifetime boundary leaves ACTIVE; calling close_zero_attempt after an attempt is false evidence.

**Recommended direction: isolate SDK work in an owned worker, qualify actual SDK compatibility before broad producer integration, and preserve strict no-start.** Reuse Q1/G03-A harmless boundary fixtures for the smallest qualification; do not build a general process framework or migrate all producers merely because the interface exists. This is a proposed architectural direction, not a claim that an SDK helper currently works. Actual Q2 execution requires the separate exact disposable-environment/effect manifest.

| Option | Assessment |
|---|---|
| Mechanical arm/finally wrapper over current callbacks | Rejected: no worker exit to qualify; initialize failure can have attempted effects; finally and shutdown-return values cannot supply missing lifetime/descendant evidence |
| New in-process session closure | Not selected: would require a distinct reviewed authority/cleanup contract, crash recovery and a preventive SDK boundary; current source and receipts do not qualify these facts |
| Owned isolated SDK worker, compatibility first | Recommended candidate: the process lifetime fits the current authority; exact SDK IPC and escape/no-start compatibility remain falsifiable Q2 questions |
| Rewrite every native producer and migrate now | Not ready: intentionally persistent restoration, multiple effect phases, GUI restoration and privileged/external paths need different qualified dispositions |

The five-persona RRI is compressed from existing requirements: the user needs usable legacy behavior after successful operations; QA needs actual lifetime and failure evidence; the developer needs one common authority without recursive leases; the operator needs coordinated participants and a recoverable maintenance window; the business needs incremental read-fleet value without a speculative native rewrite. No new interview answers or physical environment are invented.

YAGNI-3 before future code:

1. Required: producer death or uncertain cleanup must not permit another native owner; admission-only protection cannot establish the old effect's end.
2. Reuse: G03-A authority/lease/CAS, Q1's tested Windows restriction/identity fixtures, existing job cancellation/provenance, identity registry and receipt helpers. Runtime must never import a proof module.
3. Shortest useful next work: pin the proposed disposable SDK qualification manifest and reuse a narrow proof before writing product integration. An unused launcher abstraction does not solve SDK compatibility or persistent-terminal transfer.

## Producer output contract

The scan is the exhaustive source index. The classes below are distinct closure problems, not new execution capabilities.

| Class | Required qualified outcome before activation |
|---|---|
| Live state/account/market IPC, including rates after chart capture | Durable intent before the first attempted SDK effect; owned lifetime through initialization, observation, shutdown and exact cleanup; stopped/race attempts produce zero terminal births under the qualified preventive boundary |
| Job orchestration and sequential compiler/tester work | Identify which process owns the native lease. A controller cannot hold/arm it and then wait for a worker to acquire the same lease. Each created effect and the whole phase chain need exact authority; job reservation is not native ownership |
| Restore/restart and terminal handoff | Preserve the intended running terminal without claiming all owned children exited. A separately reviewed persistent-session disposition/transfer must bind actual process identity, roots, intent and proof; reconnect, login comparison or restart_pid alone cannot close uncertainty |
| GUI navigation/capture and capture subprocess | Account for parent-process UI changes/restoration plus the independently observed capture child and any later SDK access. Child exit alone does not prove the complete lifecycle |
| Arbitrary PowerShell, task/broker/WMI or administrative restart | Admission is cooperative exclusion, not arbitrary administrator tamper/escape containment. Preserve the explicit trust boundary; unsupported effect classes cannot acquire a fabricated descendant-PASS disposition |
| Inventory/status and bounded auxiliary probes | Classify by actual effect. Do not arm every utility subprocess or add native leases around active-job forensics and introduce deadlocks |

Keep native capacity one, mutation→native order, short authority transactions, legacy request hashes/job states and successful public shapes. Intent publication precedes the actual effect; creation uncertainty never guesses an identity. Process waits, SDK calls and verifier work stay outside the authority transaction. No PID death/TTL/normal finally/worker unlink/terminal restart resets authority. Cancel intent and exact old-job stop remain separate from restoration and ownership closure.

No production descendant verifier is qualified. A recognized fixture callback string does not become a SDK/broker/administrator proof. A new phase-chain or persistent-session state/schema requires a concrete amendment; do not repurpose BOUND or CLOSED to carry an unapproved meaning.

## Smallest delivery sequence and build readiness

| Step | Concrete output | Gate and scope |
|---|---|---|
| B0, this continuation | Source map, feasibility, proposed architecture, output ACs and logical migration contract | Documentation only; complete for review after Contractor verifies the reports |
| Q2-P preparation | Exact disposable host/session, pinned Python/SDK/wheel/DLL and terminal sources, two clean bindings, allowed operations, controls and trace/teardown contract | Prepare a concrete manifest; unknown values block execution, not documentation. Current VPS and historical MT5 builds are not substituted |
| Q2 bounded qualification | Matching unrestricted controls and restricted load/attach/stopped/race/escape/ownership receipts | Separately reviewed exact manifest and effect authorization; not executed by B0. Can use isolated fixtures before product integration, avoiding a G03-B↔Q2 dependency cycle |
| B1 product integration | Only explicitly supported producer classes integrated into the qualified boundary; new targeted/unqualified activation remains gated | Approved bounded implementation TIP after compatible proof and closure/transfer decisions. Any added denial/removal of an existing legacy producer requires a concrete compatibility/policy decision; no helper framework merely to move the blocker |
| B2 migration qualification | Exact payload/participant and state/rollback evidence on the chosen physical scope | Separate maintenance/execution decision; source CI cannot qualify old-binary fencing |

If restricted SDK IPC fails or a launch/escape path is unqualified, retain the result and keep targeted IPC disabled. No privilege broadening or no-start relaxation is implied. A small owned-worker source prototype may be proposed later if it has an independent proven producer need; it is not automatically the next build from this document.

Existing targetless callbacks retain their historical source behavior in a valid CLOSED installation; that behavior is not strict attach-only evidence. B0 neither disables legacy live/native/admin tools nor authorizes silently replacing their successful behavior with new denials. Unresolved authority already denies them under the approved G03-A contract. New targeted IPC remains unavailable until qualified; any further legacy safety/compatibility change is presented as a separate concrete policy decision.

## Planned acceptance criteria

These are **PLANNED / NOT RUN** for future bounded TIPs, not claims that G03-B code exists. Split the matrix into the TIP being approved; do not require unrelated future capabilities for a small proof.

| AC | Given / when / then | Required output evidence |
|---|---|---|
| B01 | Given every mapped cooperative native entry, when classified, then producer, lifetime owner, lease owner, effect/cleanup and unsupported paths are explicit | Source path/symbol map; SDK, capture+rates, sequential job phases and restore included |
| B02 | Given an in-process initialize attempt, when designing closure, then zero-attempt or own-process-exited evidence is never fabricated | Negative contract cases and exact lifetime boundary decision |
| B03 | Given an owned isolated worker, when launched, then intent/attempt, restriction, suspended creation and actual bind precede execution | Required actual Windows ordering/readback receipt; no no-console promotion from Q1's failed control |
| B04 | Given pinned real SDK/two clean roots, when tested, then matching controls qualify IPC and preventive no-start, or retain a truthful failure | Exact Q2 manifest, wheel/DLL/root hashes, process-birth/race/escape evidence; no mocked SDK PASS |
| B05 | Given false/raised initialize, observation error, stuck call or parent crash, when cleanup is unresolved, then shared authority remains ACTIVE and successor effects stay zero | Publication/crash/failure windows, A/B/C-style shared-root restart and native contention |
| B06 | Given exact exited worker, when closing, then qualified actual descendants plus exact epoch/generation/token/parent/worker CAS are required | Positive and stale/reused/unknown negative controls; fresh-dead refusal retained |
| B07 | Given sequential effects/long native job, when ownership moves across phases, then no unproved phase or recursive lease is hidden by CLOSED | Actual phase-chain/lease-owner tests and explicit schema/contract decision |
| B08 | Given intended persistent terminal restoration, when operation completes, then known running session is distinguished from exited descendants | Reviewed transfer/disposition contract and actual identity/binding/cleanup proof; not a reconnect flag |
| B09 | Given GUI capture plus SDK continuation, when restoration or child cleanup fails, then no partial child-PASS clears the whole operation | Actual full-chain fixture/fault receipts; terminal/profile side effects stay within approved physical scope |
| B10 | Given administrative/broker/external paths, when qualifying coverage, then unsupported or absent authority remains explicit | Effect/trust/source inventory and qualified exclusions; no all-tool guarantee from generic PowerShell exit |
| B11 | Given installed CLOSED supported source, when old successful cases run, then shapes, hashes, cancellation/provenance and FIFO remain compatible | Named baseline/Q1/G03-A regressions and actual selected client proof at activation |
| B12 | Given migration interruption, drift, mixed source or old backup, when restarting/rolling back, then native work remains blocked until exact reconciliation | All-participant physical payload/launcher/state manifests and negative restart/rollback receipts |

## Logical migration and rollback contract

This is an output contract, not a command runbook or authorization to alter the current VPS. Actual participant PIDs, roots, launcher inventory, external bootstrap files, payload hashes, SDK/session versions, backup bytes/digests and maintenance/rollback owner are **not collected or selected by B0**. The scan identifies referenced-but-absent deployment sources; physical review must obtain their real bytes before relying on them.

1. Inventory A/B/C adapters, controllers, native workers, tasks/services/startup and other permitted launchers against the same canonical root/epoch. Verify exact payload and dependency identities, not server_info/version labels alone.
2. Establish a coordinated maintenance fence that actually prevents old binaries/launchers from admitting effects. An old binary ignores MIGRATING; a momentarily empty queue/PID snapshot is insufficient.
3. Reconcile existing jobs/effects with exact owned-process evidence and approved cancellation/restoration scope. ACTIVE, invalid or unknown ownership is retained; do not initialize a new CLOSED epoch over it.
4. Back up exact state/payload/launcher evidence and verify bytes/digests/readback. Backend checkpoint allowlists stay unchanged; generic file restore is not ownership migration.
5. Install/read back the reviewed guard-capable participant set while the independent maintenance fence holds. Only a proven clean initial installation may use the approved MIGRATING → matching CLOSED initial authority → validated READY sequence. Every interrupted step remains blocked.
6. Verify common authority, denial/fault cases, selected supported producers and actual physical/client readiness before releasing the maintenance fence. Old scheduled/controller copies must remain fenced.
7. On drift/failure, retain maintenance and uncertainty. Rollback may restore a reviewed compatible barrier-aware payload while retaining actual ownership state; it may not restore an old CLOSED snapshot/downgrade to unguarded code to escape ACTIVE. Same-epoch backup replay and mixed binaries remain unprotected by JSON alone.

No broad kill, terminal restart, credential/account/AutoTrading change, installer/CLI execution, deployment, merge or new public force-clear is part of this planning task. Physical migration and persistence/tamper/rollback qualification remain separate from atomic-file fixtures.

## Primary facts and decision requested

Primary references reopened 2026-10-02: [MetaQuotes initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py) documents possible terminal launch and no attach-only parameter in its signature; [shutdown](https://www.mql5.com/en/docs/python_metatrader5/mt5shutdown_py) documents connection closure and returns None. [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) documents membership, breakaway and WMI exceptions; a job notification or job handle alone is not all-path prevention. **Inference:** the actual SDK may need IPC resources denied by the candidate restriction; only matched Q2 evidence resolves that compatibility question. Source findings and approved policy are separate from these API facts.

Requested new strategic decision: adopt the **owned isolated SDK-worker candidate with compatibility-first qualification**, and continue to the exact Q2 preparation manifest before broad G03-B product build. This authorizes a design/preparation direction only; no unknown physical environment or SDK effect is implicitly approved. A chosen actual Q2 execution manifest or new producer/transfer schema is presented concretely before its affected build/effect step. Keep full G03/G04/Q2/M1 OPEN and TIP-056 after TIP-060/M4.

## B0 output review

Contractor checked source anchors, the Builder's P01–P20 classifications, proposed AC coverage and migration/compatibility scope. Independent read-only review at 2026-10-02T16:15:50Z reports **PASS FOR B0 DOCUMENTATION/DESIGN ONLY**. Its reachability correction is retained: read_artifact can reach restoration through get_job; read_result only reads result.json. The contract explicitly preserves targetless valid-CLOSED source behavior and requires a concrete policy decision for further legacy denial/removal. No material design/source finding remains in this preparation package; the architecture choice, actual SDK compatibility, producer closure/transfer and physical gates remain open.

All parent product/test/proof/workflow/dependency/evidence bytes must match the verified 253-blob source snapshot at publication. Only the three B0 documents and six linked planning/index/approval documents change. Link/hash/diff checks qualify the package; no product/native/SDK test or physical operation ran as part of B0. Existing PR workflows may rerun automatically on the documentation head; their unchanged foundation proof does not execute these planned G03-B/Q2 ACs.
