# Fleet v1 — Vibecode Kit v6 Blueprint checkpoint

Date: 2026-10-01, Asia/Saigon. Status: **PROPOSED — OWNER APPROVAL PENDING**.

This package turns the fleet brainstorm and its source-based review into a reviewable contract. It defines the entire big-update direction while making only the first implementation task dispatchable after approval. No fleet capability is implemented or qualified by this documentation PR.

## Read order and authority

1. [Blueprint](blueprint.md): scope, architecture, target/identity and lifecycle contracts.
2. [Requirements and decisions](requirements-and-decisions.md): REQ mapping, proposed choices, decision ownership and open gates.
3. [Task graph](task-graph.md): revised TIP dependencies and capability unlocks.
4. [TIP-055A](TIP-055A.md): first bounded Builder task, with Gherkin acceptance.
5. [Verification and release](verification-and-release.md): output evidence, migration, fault qualification and stop conditions.

[Original brainstorm](reference/2026-10-01-brainstorm.md) and [plan review](reference/2026-10-01-plan-review.md) are historical inputs. On approval, this package supersedes their conflicting implementation order. Runtime evidence continues to outrank design assumptions. Existing TIP-053/054 evidence remains retained and is not fleet acceptance.

Baseline repository commit: `64a62906b4e62274732f0cbc375bfb3687af9e42`. Runtime observations referenced by the review were TIP-053 / 0.2.42, fixed MT5-2 and serialized native execution. This documentation checkpoint makes no fresh runtime certification claim.

## Methodology for the entire update

Use SCAN → RRI → VISION → BLUEPRINT → TASK GRAPH → BUILD → VERIFY → REFINE. Reuse the completed audit where authority has not changed; scan only relevant drift. Requirements here are synthesized from the supplied plan and discussion, not invented interview answers. Owner approval is recorded explicitly. Builder implements a TIP and returns a Completion Report; Contractor verifies outputs against REQ/AC evidence.

The proposed graph is supplied with the Blueprint so the owner can assess the resulting work. It is a planning artifact until approval. Only TIP-055A has an executable specification in this package; later TIPs require their own concrete specifications and readiness gates before dispatch.

Every implementation TIP records three answers: why it must exist, what existing capability can be reused, and the shortest sufficient change. Small tasks use a shortened workflow; changes to architecture or product policy return to Blueprint review.

## Approval scope

Proposed approval: big-update direction and constraints; M0/M1 scope; proposed M0/M1 decisions; permission to dispatch TIP-055A. This does not authorize deployment, native tester actions, live-terminal handoff, pairing an unidentified VPS, multi-agent writes, or merging an implementation before its evidence gate.

Later deployment and physical qualification follow the owner's authorized scope and exact reviewed revision. Actual pilot machines, public gateway endpoint/provider and Windows worker readiness are OPEN execution gates, not fictional inventory.

To approve, the owner may state: `APPROVED Fleet v1 Blueprint; proceed TIP-055A`, or approve with clearly identified amendments. A review/merge action alone must not be silently interpreted as permission to operate MT5. Record the owner statement, exact Blueprint commit and amendments in the next checkpoint; never retrospectively mark this draft approved.
