# TIP-057R — Targeted local read readiness

Status: REFINEMENT ONLY; not dispatched or capability-qualified. Direction derives from approved Blueprint section 6 and REQ-F04/F10/F14/F15. Current M0 runtime has five UNENROLLED/UNQUALIFIED rows; real identity acceptance remains a build dependency. TIP-055B is corrective maintenance for the existing global lease, not implementation of this TIP.

## Smallest next slice

Proposed first slice: exact local terminal state/account reads through the existing get_terminal_live_state and get_account_snapshot domain methods. Keep existing no-target MT5-2 behavior; explicit local fleet.target/1 supplies device_id, terminal_id and terminal_generation, with no fabricated route_generation. Exclude charts/capture, rates/ticks, remote transport, source changes and native compile/test routing from this first slice.

YAGNI-3: this must exist to inspect a selected registered terminal without alias ambiguity; reuse IdentityRegistry/local target validation, TerminalInventory, LiveTerminal.state, facade and the existing per-node global native lease; add only target resolution/attribution and the required additive signatures/contracts. No gateway or new dispatcher is needed for local proof.

Current reuse facts:
- LiveTerminal already accepts an inventory alias and explicitly initializes its executable.
- state() requires a running installation, validates reported installation directory and data root, avoids login, masks account login and shuts down in finally.
- Facade currently serializes the entire LiveTerminal call under native_execution with wait_seconds=2, then always chooses fixed MT5-2.
- M0 local validator is inventory-only. Accepting live_read must be an explicit later contract, not a bypass by relabelling a live call inventory.
- Existing live state uses a 2,000ms initialize timeout. That does not prove a total wall-clock deadline for later native-library calls.

## Required contract before dispatch

| Requirement | Proposed output / evidence |
|---|---|
| Explicit target | Resolve exact local IDs/generation and reject unknown/disabled/stale/unqualified/wrong-device/remote references without alias/fixed fallback |
| Legacy request | With no explicit target, retain fixed MT5-2 path and old output authority; no enrolled IDs invented |
| Lifecycle | One shared per-node lease across validate/initialize/observe/shutdown; existing A/B/C/native paths share ownership, not a separate IPC lock namespace |
| Binding | Validate enrolled executable/data root against running process/IPC observations before account access; a wrong installation cannot produce an attributed success |
| Drift | Revalidate under lease before IPC, retain frozen IDs/generation, and detect changes during observation before returning a qualified target receipt |
| Attribution | Requested/resolved/observed binding, source, observed_at, identity generation/revision and explicit failure; disconnected financial fields stay null/unavailable |
| Account policy | No login, credential, account, AutoTrading, terminal start/restart or chart navigation; initialize must not silently start a stopped installation |
| Tool surface | Additive optional target only on the selected read methods; exact schema/client exposure and unchanged legacy native signatures required |
| Resource use | One observation per request; no images/heavy market data, fleet totals or background polling |
| Deadline | Separate lease wait, IPC initialize and overall caller budget; no success claim from initialize timeout alone; unfinished IPC must retain ownership until shutdown/reconciliation |
| Failure | Keep wrong binding, unavailable terminal, stale identity, IPC failure and timeout distinguishable; cancellation cannot release a lease while IPC still runs |
| Regression | Mixed A/B requests across at least two IDs, denied binding, disabled/replaced roots, concurrent identity change, initialize/observation/shutdown exceptions and original fixed-native behavior |

The Builder must first check lifecycle failure cleanup: current state() enters its shutdown finally only after initialize succeeds. The new request cannot leave ambiguous process-wide IPC attachment after a failed initialize and then observe another target. Reuse/harden cleanup within the selected read scope rather than duplicate account conversion.

A hard deadline for an uninterruptible native-library call may require a separately reviewed helper boundary; approved direction allows proposing helper processes after Windows binding evidence. Do not silently insert a thread timeout that releases the shared lease while a native call continues, or expand architecture based on assumed cancellation semantics. This is an explicit readiness question, not a reason to claim implementation impossible.

## Evidence needed to turn this into a dispatchable TIP

1. Real M0 bootstrap/show receipts, stable IDs across fresh process, verified complete registry backup and at least two physically independent QUALIFIED bindings.
2. CLOSED for release recovery: [TIP-055B runtime checkpoint](TIP-055B-runtime-qualification.md) binds exact reviewed/deployed source, four passing CI workflows, actual Windows handles and guarded VPS qualification. Initial issue #56 failure remains retained. This closes no identity or targeted IPC gate.
3. Source/schema delta and exact state/account output shape frozen; chosen actual pilot target IDs recorded. No illustrative labels substituted.
4. Numeric caller/lease/IPC deadline contract and honest non-cancellable-call recovery policy selected before build.
5. Gherkin ACs bound to the selected schema/error codes, fixture map and planned actual client/Windows proof.

This refinement does not unlock M1 or assert any actual account/IPC observation. A source/fixture implementation may be prepared only when its applicable approved dependency gates are satisfied. Gateway endpoint/provider, Ed25519 enrollment and two-node read acceptance remain TIP-058/059 gates.
