# TIP-037 — Existing Chat GitHub Event Pilot

Status: draft PoC. This branch is a test carrier, not a production rollout.

## Goal

Prove that a GitHub pull-request conversation comment can trigger a scheduled task **inside the existing ordinary Chat conversation** of ChatGPT account B, and that the run can call the existing TunnelVibemq5 MCP connection. A, B, and C are intended to be symmetric peers; B is only the first receiver tested.

## Baseline and constraints

- Shared backend: VibeMQL5 Bridge 0.2.34 / TIP-033; 72 server-side tools, fixed MT5-2.
- The first gate is read-only: `server_info` and `health`. No source edit, tester launch, MT5/account/AutoTrading change, tunnel restart, or task payload in GitHub.
- The repository is public. Comments contain only an opaque probe marker. No secrets, source, customer data, or ChatGPT transcript.
- All three ChatGPT accounts connect to the same GitHub identity; GitHub comment author does not distinguish A/B/C. Future routing uses a dedicated PR per *recipient* and backend-side receipts, not `author_login`.
- GitHub event delivery latency has no documented SLA. Matching events may be combined. A task must read all pending assignments and deduplicate by operation ID in the later delegation phase.

## Gate 1: B chat wakeup

1. Create this draft PR and record its repository, number, and URL.
2. In B's **existing ordinary Chat conversation**, create an event-triggered scheduled task scoped to **new PR conversation comments** on this PR number. Choose destination **this same chat**. Do not select a time-based schedule.
3. Confirm the GitHub event task is enabled for B and TunnelVibemq5 is available in that conversation. Record task ID and the destination chat, without sharing tokens.
4. Only after step 3, post **one** conversation comment on this PR with the exact marker `TIP037-B-WAKE-20260923-01`. Do not put the task text in the comment.
5. The B task ignores unrelated comments. On seeing the marker it calls `server_info` and `health`, then reports the marker, bridge version/build, fixed terminal, GitHub comment timestamp, task-run timestamp if available, and whether the result appeared in B's original chat.
6. Compare the GitHub comment timestamp with the first observed B run and the completed B answer. Repeat with a different marker only if the first run is inconclusive; keep every probe identifiable.
7. Pause the B event task when the pilot ends.

Gate 1 PASS requires the run to be triggered by the comment, use the connected TunnelVibemq5 tool, and return to the original ordinary Chat conversation of B. If the account does not offer the trigger, the run starts standalone, plugin access fails, or no run occurs, record the exact observed condition as BLOCKED. Do not infer delivery speed from a single run.

## Gate 1 diagnostic checkpoint — 2026-09-23

Account B completed read-only preflight: GitHub repository read access and `pull=true` were verified; `TunnelVibemq5.server_info` reported Bridge 0.2.34 / TIP-033 on MT5-2. The ordinary Chat B automation interface did not expose the `discover_webhook_schema` / GitHub webhook trigger capability needed to create the PR #17 comment task. No task ID was returned; no task was enabled; no destination chat was registered. PR #17 has no probe comments. Gate 1 is **BLOCKED at event-task creation**, so latency and same-chat return have not been measured.

Next diagnostic is in **account B on ChatGPT web**, in its existing Chat: inspect Scheduled for the GitHub PR-event option. If B is a managed workspace, check the workspace's Allow event-triggered scheduled tasks permission. A connected GitHub app and `pull=true` alone do not establish scheduled-event availability. If the event option remains unavailable, stop the event pilot for B. A time-based poll is a separate experiment and must not be substituted for this gate without an explicit change of scope.

## Separate one-time timer probe in B's existing Chat

This is a different experiment from GitHub Gate 1 and does not claim that PR events work. It tests the previously requested scheduled-task mechanism without creating a recurring poll.

1. In account B's original ordinary Chat conversation, create a **one-time** scheduled task five minutes from now, returning to **this chat**.
2. The saved prompt calls only `TunnelVibemq5.server_info` and `TunnelVibemq5.health`, and reports version/build, MT5-2, health and the actual run timestamp. It makes no writes.
3. Verify that the task ID exists and the completed result appears in the same B chat with the plugin calls executed. If creation is unavailable or the destination is standalone, record BLOCKED.
4. Only after this capability is demonstrated, run a separate cross-account A/C→B continuity-assignment test; do not enable recurring polling before its cadence and empty-run behavior are reviewed.

## Gate 2: durable handoff (only after Gate 1 PASS)

Use the existing continuity `DELEGATION_ASSIGNED`, `DELEGATION_STARTED`, and `DELEGATION_COMPLETED` lifecycle with project-level CAS and stable operation IDs. Keep complete briefs and evidence on the VPS. A GitHub PR comment carries only the delegation ID; the event task reads the inbox and processes every pending delegation addressed to its receiver. Completion is written to backend continuity and verified by the originator before it is treated as accepted.

No security-grade ChatGPT account identity exists in current MCP request metadata. Any future attribution or access decision must be bound to the server-side per-tunnel instance, never to an account label supplied in a prompt.

## Gate 3: symmetric A/B/C (only after Gate 2 PASS)

Set up one dedicated PR and one event-triggered task in the original ordinary Chat conversation of each recipient. Validate all six directed paths: A→B, A→C, B→A, B→C, C→A, C→B; then validate one request to both other peers, duplicate comment handling, combined events, and receipt return to the originator. Keep native MT5 and source-mutation serialization unchanged.

## References

- https://learn.chatgpt.com/docs/automations
- https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/blob/main/app/vibemql5/core/continuity.py
