# TIP-037 — Existing Chat GitHub Event Pilot

Status: historical PoC runbook, merged into `main` on 2026-09-23. GitHub event wakeup remains BLOCKED; the merge is not a cross-account acceptance.

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

This test demonstrates scheduled Chat B retrieving work left on the shared VPS and returning a durable receipt. Coordinator verification via `get_continuity` and `verify_continuity` follows the B run. It does **not** prove a GitHub event wakes B, identify the real sender account, wake an originating Chat, or establish symmetric A/B/C messaging. **Creation checkpoint: ASSIGNED / B ONE-SHOT ENABLED, RUN PENDING AT CREATION; see the BLOCKED outcome below.** B reports creating a new one-shot in the same existing conversation with an expected run **2026-09-23 18:06:52 UTC+7 (11:06:52 UTC)**. The saved instruction is scoped to this continuity assignment, validates recipient/state/integrity, performs CAS on at most `DELEGATION_STARTED` and `DELEGATION_COMPLETED`, and returns to the same B chat. At **11:02:41 UTC**, independent `get_continuity` still showed `ASSIGNED` at manifest revision 1; no B start or completion receipt existed yet. Creation/enabled status is B's report; execution and receipts remain pending. At roughly **11:07–11:09 UTC**, the coordinator's first post-schedule `get_continuity` call failed with `HTTP 504: MCP request timed out`. A separate coordinator `health` call also failed with the same HTTP 504 at **11:11 UTC**. These are transport failures of the coordinator's read-only checks, not evidence of the B task outcome. The next checks are B's actual task answer and a later continuity read when MCP connectivity returns.

## B timer handoff outcome — BLOCKED on 2026-09-23

B reports its one-shot ran but the platform rejected the first attempted tool call, `TunnelVibemq5.get_continuity(project_id="TIP037-CHAT-B-PROBE-20260923")`, with the exact message: `This tool call was blocked by OpenAI's safety checks. Please double check what you are sending.` B stopped at the first guard. It reports **0/2 continuity writes**, no `DELEGATION_STARTED` or `DELEGATION_COMPLETED`, no `server_info` or `health`, and no other mutation. The delegation thus has no B receipt. The exact trigger for the platform block was not supplied; do not label it a backend validation or CAS failure and do not claim an account-to-account handoff PASS.

The coordinator's `get_continuity` at **11:14 UTC** also failed, this time with `tunnel_client_not_connected` (`Tunnel-client did not poll after this request was enqueued`). This transport error is separate from B's safety-check rejection. A post-run manifest read remains outstanding, so the reported zero writes cannot yet be independently verified from this connection. Keep the same delegation ID, leave the task one-shot, and resume only after normal tunnel connectivity and the platform's tool block are diagnosed through supported settings/support; do not invent a different task payload to evade the check.

## 2026-09-23 tunnel disconnection investigation — local snapshot

The operator's interactive Administrator VPS snapshot at approximately **20:28 UTC+7** showed A/B/C with one exact-profile tunnel process each: A PID 5872, B PID 1124, C PID 3040. Each process owned its respective loopback port 8080/8081/8082 and both `/healthz` and `/readyz` returned 200. Supervisors reported `READY / interactive`, zero restarts in the last hour and no last exit code; watchdogs reported `HEALTHY / NONE`, interactive desired. Interactive tasks were Running; background tasks were Ready following the approximately 14:30 local handoff. The last recorded local `Tunnel ready` for each was approximately 07:31 UTC, before the approximately 11:06–11:14 UTC remote 504/404 window. No restart is visible in the supplied supervisor log excerpts around that remote failure window.

The previous diagnostic's negative `HeartbeatAgeSec` values (roughly -25190 seconds) are an arithmetic bug: `[datetime]::Parse()` converts a `Z` timestamp to VPS local UTC+7, then the script subtracted it from `UtcNow`. Recompute with `[DateTimeOffset]::Parse(value).UtcDateTime`; do not infer clock drift from those negatives. Task result 267009 is `0x41301` (running); background 267014 is `0x41306` (previous task terminated), consistent with the supervisor handoff script stopping background on interactive logon.

At **13:30:34 UTC** the coordinator's `server_info` still received `tunnel_client_not_seen` (client unseen for 300 seconds) despite the reported local READY snapshot. **Root cause remains unproven.** Next read-only discriminator: identify which A/B/C profile tunnel ID matches the failed connector (compare locally, report only instance), then inspect each loopback `/health/control-plane` and `/health/response-delivery` or `/ui` for last successful poll, failure category, and timestamps. Local 200/200 does not prove successful remote polling. The installed tunnel-client version may return 404 for newer component-health endpoints; use `/ui` if so. Do not restart all instances based on local health alone.

## Gate 2: durable handoff (only after Gate 1 PASS)

Use the existing continuity `DELEGATION_ASSIGNED`, `DELEGATION_STARTED`, and `DELEGATION_COMPLETED` lifecycle with project-level CAS and stable operation IDs. Keep complete briefs and evidence on the VPS. A GitHub PR comment carries only the delegation ID; the event task reads the inbox and processes every pending delegation addressed to its receiver. Completion is written to backend continuity and verified by the originator before it is treated as accepted.

No security-grade ChatGPT account identity exists in current MCP request metadata. Any future attribution or access decision must be bound to the server-side per-tunnel instance, never to an account label supplied in a prompt.

## Gate 3: symmetric A/B/C (only after Gate 2 PASS)

Set up one dedicated PR and one event-triggered task in the original ordinary Chat conversation of each recipient. Validate all six directed paths: A→B, A→C, B→A, B→C, C→A, C→B; then validate one request to both other peers, duplicate comment handling, combined events, and receipt return to the originator. Keep native MT5 and source-mutation serialization unchanged.

## Post-merge checkpoint and ordinary-Chat receiver gate — 2026-09-23

PR #17 (this historical runbook) and PR #18 (read-only A/B/C poll diagnostics) are merged into `main`. The tunnel diagnostic code was deployed and passed 407 VPS unit tests. After a simultaneous DNS poll outage, A/B/C recovered; all three local instances had one process and 200/200 health/ready. These checks do not establish that any ChatGPT account can wake or authenticate another account's chat.

From the coordinator's currently connected chat, `get_continuity(project_id="TIP037-CHAT-B-PROBE-20260923")` returned the unchanged `CM-000001` manifest at revision 1, SHA-256 `4bf7b6885b9610dd5871bc1c2c513ef6ad3408272b31ef38f4a4b21de3152a94`. The only active delegation is `TIP037-B-READ-20260923-01` for recipient label B in `ASSIGNED`. `verify_continuity` returned `integrity=VERIFIED`, `semantic_integrity=VERIFIED`, `resume_safe=true`, and one event. Thus B's earlier scheduled safety-check rejection produced no continuity writes. This is a read through the coordinator's connector, not an independently authenticated account-B result.

Next, run these **read-only** receiver checks inside the existing ordinary Chat conversations of B and C, each with its own installed TunnelVibemq5 connector:

1. Call `get_continuity(project_id="TIP037-CHAT-B-PROBE-20260923")` and `verify_continuity` with the same project ID. Report the exact tool result, integrity, revision, SHA and delegation state. C is only testing visibility of the shared manifest; C must not claim or complete B's assignment.
2. In B, if both direct calls pass and the live manifest still addresses B in `ASSIGNED`, run the already scoped B handoff with one `DELEGATION_STARTED`, then `server_info` and `health`, then one `DELEGATION_COMPLETED`. Each write must use the revision and SHA from the **immediately preceding** read/receipt plus a stable, distinct operation ID. Report both receipts in B's original chat. If any guard fails, stop without a substitute write.
3. Re-read and verify the manifest from the coordinator connector. Accept the handoff only if the two B receipts appear with valid CAS and the resulting delegation awaits parent verification. Because the current MCP transport has no authenticated ChatGPT account identity, the `recipient` or `origin` labels alone cannot prove which ChatGPT login wrote an event.
4. Only after direct B handoff works, create a fresh one-time receiver task **in B's original ordinary Chat** for a new assignment. First test `get_continuity` alone: the earlier scheduled run was blocked by platform safety checks before the Bridge received the call. If it is blocked again, retain the error and do not schedule recurrent polling or claim automatic handoff. Repeat the same receiver gate for A and C before attempting six directed routes.

Event-triggered GitHub tasks currently require ChatGPT Work; a task created in a Work chat does not prove that a B/C **ordinary Chat** can receive the event. Ordinary-Chat timer tasks have independently returned to B's same chat once, but a time-based task does not wake on demand. No coordinator in one account can create a scheduled task inside another account's existing chat using this connector. Keep a timer-based pilot separate from GitHub Gate 1 and document the measured delivery delay before selecting it.

### Ordinary-Chat read checkpoint and B direct CAS gate

The user reports that B's **direct ordinary Chat** call to `get_continuity` succeeded: revision 1, the same SHA above, `recipient=B`, and `state=ASSIGNED`. B's `verify_continuity` also returned verified integrity, `resume_safe=true`, no issues, and unchanged read-only proof. In the other reported receiver chat (presumed C from the order of the report), `get_continuity` was blocked by OpenAI safety checks, while `verify_continuity` succeeded against `CM-000001` with the same SHA and no mutation. The exact reason for the platform block is unknown. These are user-reported results; the coordinator cannot independently authenticate which ChatGPT account originated a tunnel request.

The coordinator re-read the project after these reports: revision 1, identical SHA, B assignment still `ASSIGNED`, no start/completion event; Bridge health READY, queue 0 and no active job. B may now perform the **direct** handoff in its own original ordinary Chat, with no scheduled task or GitHub action:

1. Re-read and verify the manifest immediately before writing. Require `VERIFIED`, `resume_safe=true`, delegation ID `TIP037-B-READ-20260923-01`, `recipient=B`, `state=ASSIGNED`. Use the live revision and SHA from that read, not a pasted stale checkpoint.
2. Append `DELEGATION_STARTED` with payload `{"delegation_id":"TIP037-B-READ-20260923-01","summary":"B direct Chat accepted read-only health probe"}` and operation ID `TIP037/DIRECT/B/START/20260923/01`. Require its receipt to advance the manifest and show `STARTED`; stop on tool block, CAS failure or unexpected state.
3. Call only `server_info` and `health`; require a normal response before completing. Do not run an MT5 test or change source, tunnel, account or AutoTrading.
4. Append `DELEGATION_COMPLETED` with payload `{"delegation_id":"TIP037-B-READ-20260923-01","report":{"status":"DONE","checks":["server_info","health"]}}` and operation ID `TIP037/DIRECT/B/COMPLETE/20260923/01`. Use the new manifest revision and SHA from the STARTED receipt. Require `AWAITING_PARENT_VERIFICATION`; otherwise report BLOCKED with the exact error and leave the observed state for coordinator inspection.
5. Return both receipts to the original B Chat. The coordinator then performs a fresh read/verify; only after matching receipts will it write `DELEGATION_PARENT_VERIFIED` using a fresh CAS. This proves a durable direct Chat handoff with reported B provenance; it does not yet prove automatic wakeup or security-grade account identity.

### B direct handoff verified; C direct assignment prepared

B reported `DELEGATION_STARTED` as `EV-00000002` with operation `TIP037/DIRECT/B/START/20260923/01`, revision 2, SHA `7a950f5f1b8adbf72e091d4214e5fa591a04e21499f56e6c0be3357c6837aca9`. It then reported successful `server_info` (Bridge 0.2.34 / TIP-033, fixed MT5-2) and `health` (READY, queue 0, no active job), followed by `DELEGATION_COMPLETED` as `EV-00000003` with operation `TIP037/DIRECT/B/COMPLETE/20260923/01`, revision 3, SHA `b76be803f08aa2405c320d4d13dc7332643737ed855f999e4d70a9f81b6145ba`. The coordinator independently read the immutable events and verified the manifest and semantic chains; both B receipts had the same request-scoped `client_key`, distinct from the original assignment. This is request attribution, **not** authenticated ChatGPT identity or independent proof of B's `server_info`/`health` calls.

The coordinator used exact revision-3 CAS to append `DELEGATION_PARENT_VERIFIED` as `EV-00000004`, operation `TIP037/PARENT/B/VERIFY/20260923/01`. Its verification payload explicitly records `authenticated_chatgpt_identity=false`. Final B manifest is revision 4, SHA `9fcb563153d6a205efd1239f046ba571462f995f39d858d0d660b171599d3b9a`; both delegation lists are empty. Fresh `get_continuity` and `verify_continuity` returned VERIFIED, `resume_safe=true`, four events and no issues. **B direct durable handoff: PASS on receipts and user-reported B conversation. Automatic wakeup and symmetric A/B/C: not yet tested.**

For C, the coordinator created a separate assignment through `DELEGATION_ASSIGNED` operation `TIP037/ASSIGN/C/20260923/01` in project `TIP037-CHAT-C-PROBE-20260923`. Delegation `TIP037-C-READ-20260923-01` has `recipient=C`, `state=ASSIGNED`; initial manifest revision 1, SHA `4519c6f8d13d99b3ad713ac47590ef7dd2f5b3e4c06ef7a36e18d73ff607a8de`. Independent read and verify returned VERIFIED with no issues. The next receiver gate belongs in C's **own existing ordinary Chat**: read and verify this C-specific project, then, only if the live head and recipient match, run `DELEGATION_STARTED` with operation `TIP037/DIRECT/C/START/20260923/01`, call only `server_info` and `health`, and complete with fresh CAS using operation `TIP037/DIRECT/C/COMPLETE/20260923/01`. A safety-check rejection or CAS mismatch stops the run without a substitute event. C's previously blocked read concerned the **B-specific** project and does not establish the outcome for its own C assignment.

### C direct handoff verified; next peer route C to B

C reported `DELEGATION_STARTED` as `EV-00000002`, revision 2, SHA `24e121e526352d79bef801f504aa65b22eb52ff5fe163c85ede9c59cfd06e8ea`, then `server_info` and `health` READY, then `DELEGATION_COMPLETED` as `EV-00000003`, revision 3, SHA `aff3a6520d9412fd2dcd14daec6492fdd6f6e9b6248969b7c1bdf242ff20910a`. The coordinator independently read these events, verified both chains and used revision-3 CAS to append `DELEGATION_PARENT_VERIFIED` as `EV-00000004`, operation `TIP037/PARENT/C/VERIFY/20260923/01`. Final manifest revision 4, SHA `b522964cecfc3a7572955f5aac3b774294aae978c8fde39bfaf004d786067c08`, integrity VERIFIED, zero active/awaiting delegations and no issues. **C direct durable handoff: PASS on receipts and user-reported C conversation.**

The B and C STARTED/COMPLETED events have the *same* `actor_provenance.client_key`; this field does not distinguish ChatGPT accounts. The backend sets `security_identity=false`. Future tests may distinguish workstreams by project, operation ID and user-reported chat receipt, but must not treat `client_key`, `origin` or `recipient` text as authenticated account identity.

Next experiment must have C, in its original ordinary Chat, create a **new** `DELEGATION_ASSIGNED` in project `TIP037-PEER-C-TO-B-20260923` with recipient B and unique ID `TIP037-C-TO-B-20260923-01`; use expected revision 0/SHA empty and stable operation `TIP037/PEER/C/ASSIGN/B/20260923/01`. B then reads and verifies that project in its own ordinary Chat, performs a read-only health handoff with two fresh CAS receipts, and C (the originator) reads/verifies and writes parent verification. Only then record the route C→B as a user-observed direct-chat pilot. No automatic cross-chat notification or authenticated login identity is established by this sequence; do not create a timer or GitHub event task on its behalf.

### C to B direct peer route — completed

The user reported that C's ordinary Chat created assignment `EV-00000001` in `TIP037-PEER-C-TO-B-20260923`, revision 1, SHA `a6c9612abae77419e0f5dc8e8d5e61d45e952a73618a8d0c46a3d47703478374`. The coordinator independently verified that one assignment and its event operation `TIP037/PEER/C/ASSIGN/B/20260923/01`, recipient B, integrity VERIFIED. B reported accepting it as `DELEGATION_STARTED` (`EV-00000002`, revision 2, SHA `7c376577c99fc0238c0f32f938967d7743235a6a48a3145824494b9e4246a6e2`), calling only `server_info` and `health`, then writing `DELEGATION_COMPLETED` (`EV-00000003`, revision 3, SHA `4d721208a15ff6eab2fee3a88329c5983f9d090e15cf53b27499d2af3339036b`). The coordinator verified event types, operation IDs, manifest SHA, report DONE and `AWAITING_PARENT_VERIFICATION`; it did not accept the receipt on C's behalf.

C reported its own `DELEGATION_PARENT_VERIFIED` (`EV-00000004`, operation `TIP037/PEER/C/PARENT/VERIFY/20260923/01`). Independent coordinator read/verify confirmed final revision 4, SHA `44cea7700520463161667ce92777b565f9937a948c01c0c8cae923464b9d0ac3`, event head SHA `e7d122cb37516246aa10e4cd32ab79b5170ac9681ae5e5a76715dbc1fb13416e`, integrity and semantic integrity VERIFIED, no issues, and both delegation lists empty. **C→B manual direct-chat route: PASS by user-reported chats and verified durable receipts.** All four events share the same request-scoped `client_key`, so the Bridge does not independently authenticate C/B account identities. The saved B report does not independently prove which account made the two read-only tool calls.

Next route: B creates a fresh C-addressed assignment from B's original ordinary Chat, then C reads and completes it, then B verifies and accepts it. Do not call this an automatic ping: each Chat turn has been initiated by the user. The earlier B one-shot scheduled task returned to its own chat for a read-only health probe, but its scheduled `get_continuity` attempt was blocked by platform safety checks. Automatic handoff remains unproven; event-triggered tasks require Work and are outside the ordinary-Chat pilot. A's original ordinary Chat must be tested separately; a request in the coordinator's Work chat is not evidence that an A ordinary Chat received a task.

## References

- https://learn.chatgpt.com/docs/automations
- https://github.com/FreemanX369/TunnelVibeMt5-Chatgpt-max/blob/main/app/vibemql5/core/continuity.py
