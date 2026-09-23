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
3. Verify that the task is enabled and visible in B's task list. Record an internal task ID only if the UI exposes one. Confirm the completed result appears in the same B chat with the plugin calls executed. If creation is unavailable or the destination is standalone, record BLOCKED.
4. Only after this capability is demonstrated, run a separate cross-account A/C→B continuity-assignment test; do not enable recurring polling before its cadence and empty-run behavior are reviewed.

## One-time timer checkpoint — creation on 2026-09-23

Account B reports that it created and enabled the one-time task in its existing Chat. The planned run is **2026-09-23 17:08:23 UTC+7 (10:08:23 UTC)**. Its saved instruction uses only `TunnelVibemq5.server_info` and `TunnelVibemq5.health` and returns the result to that same conversation; no GitHub event, VPS, tunnel, or MT5 mutation is involved. The product response did not disclose an internal `task_id`, so its absence is not a failure condition. Backend read-only health at this checkpoint was READY with an empty queue and no active job or locks. **Status: SCHEDULED / RUN PENDING.** A successful completed B answer with tool outputs and same-chat placement is still required to pass this separate timer probe. GitHub Gate 1 remains **BLOCKED** and no PR marker has been posted.

## One-time timer checkpoint — completed on 2026-09-23

B reports the task ran **around 17:08 UTC+7** and returned its answer in **the same ordinary Chat conversation**. The reported tool calls were limited to `TunnelVibemq5.server_info` and `TunnelVibemq5.health`. Output: Bridge **0.2.34 / TIP-033**, fixed **MT5-2**; service and health **READY**, queue **0**, active job **null**, valid terminals **5/5**, free disk **13.06 GB**, free RAM **1549.3 / 2047.5 MB**. No GitHub call or VPS, tunnel, or MT5 mutation was reported. Evidence includes B's run report and a screenshot showing the completed “Tunnel health check” answer below the scheduled-task chip in the same B conversation; the screenshot menu shows about **17:11 UTC+7** for the answer. The screenshot shows the answer, not a raw MCP tool receipt. The internal `task_id` was not exposed. **Separate one-time timer probe: PASS on reported execution and same-chat return.** This does not change GitHub Gate 1 (**BLOCKED**) or measure GitHub event latency. Next test must use a new, explicit one-time B task that reads a dedicated continuity assignment; this completed health task has no instruction to do that.

## Separate timer handoff pilot — prepared on 2026-09-23

A dedicated continuity project now holds one minimal B assignment: `project_id=TIP037-CHAT-B-PROBE-20260923`, `delegation_id=TIP037-B-READ-20260923-01`, assignment operation `TIP037/ASSIGN/B/20260923/01`. At creation, manifest `CM-000001` had SHA-256 `4bf7b6885b9610dd5871bc1c2c513ef6ad3408272b31ef38f4a4b21de3152a94`. Subsequent `get_continuity` and `verify_continuity` both returned `VERIFIED` and `resume_safe=true`; state is `ASSIGNED`. The assignment was written by this coordinator connection; `origin` is an untrusted label, and the current bridge exposes no authenticated ChatGPT account identity. Do not claim an A→B or C→B account identity from this entry alone.

A **new one-time scheduled task in B's existing ordinary Chat** must read the exact project/assignment, verify continuity, append `DELEGATION_STARTED` with CAS using the live manifest head, run only `server_info` and `health`, then append `DELEGATION_COMPLETED` with a second live CAS using a stable operation ID and a short non-sensitive report. It should report results in that same B chat. If a scheduled run cannot call `append_continuity_event`, report the exact rejection and leave the assignment for inspection; no retries that create unrelated entries. The earlier completed health task cannot perform this work because its saved prompt does not mention the assignment.

This test demonstrates scheduled Chat B retrieving work left on the shared VPS and returning a durable receipt. Coordinator verification via `get_continuity` and `verify_continuity` follows the B run. It does **not** prove a GitHub event wakes B, identify the real sender account, wake an originating Chat, or establish symmetric A/B/C messaging. **Status: ASSIGNED / B ONE-SHOT ENABLED, RUN PENDING.** B reports creating a new one-shot in the same existing conversation with an expected run **2026-09-23 18:06:52 UTC+7 (11:06:52 UTC)**. The saved instruction is scoped to this continuity assignment, validates recipient/state/integrity, performs CAS on at most `DELEGATION_STARTED` and `DELEGATION_COMPLETED`, and returns to the same B chat. At **11:02:41 UTC**, independent `get_continuity` still showed `ASSIGNED` at manifest revision 1; no B start or completion receipt existed yet. Creation/enabled status is B's report; execution and receipts remain pending. At roughly **11:07–11:09 UTC**, the coordinator's first post-schedule `get_continuity` call failed with `HTTP 504: MCP request timed out`. This is not evidence of the B task outcome; the next checks are B's actual task answer and a later continuity read.

## Gate 2: durable handoff (only after Gate 1 PASS)

Use the existing continuity `DELEGATION_ASSIGNED`, `DELEGATION_STARTED`, and `DELEGATION_COMPLETED` lifecycle with project-level CAS and stable operation IDs. Keep complete briefs and evidence on the VPS. A GitHub PR comment carries only the delegation ID; the event task reads the inbox and processes every pending delegation addressed to its receiver. Completion is written to backend continuity and verified by the originator before it is treated as accepted.

No security-grade ChatGPT account identity exists in current MCP request metadata. Any future attribution or access decision must be bound to the server-side per-tunnel instance, never to an account label supplied in a prompt.

## Gate 3: symmetric A/B/C (only after Gate 2 PASS)

Set up one dedicated PR and one event-triggered task in the original ordinary Chat conversation of each recipient. Validate all six directed paths: A→B, A→C, B→A, B→C, C→A, C→B; then validate one request to both other peers, duplicate comment handling, combined events, and receipt return to the originator. Keep native MT5 and source-mutation serialization unchanged.

## References

- https://learn.chatgpt.com/docs/automations
- https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/blob/main/app/vibemql5/core/continuity.py
