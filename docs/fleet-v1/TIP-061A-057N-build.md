# TIP-061A / 057N — Frozen project placement and routed native boundary

Status: DISPATCHED, source build under continuous authorization. Dependencies 055A/058 for 061A, 057R/061A for 057N; prepare disjoint source in parallel, accept integration after dependencies. Preserve historical v1 request/session/job behavior. Physical tester/SDK qualification deferred.

YAGNI-3: managed jobs need immutable placement and environment equivalence; reuse project revision/checkpoint/CAS, baseline validation, native ownership and job reservation; implement versioned fleet contracts with a narrow routed adapter rather than rewriting legacy history.

## 061A acceptance

* A node-owned fleet project contract records project ID, owner device, source/checkpoint/revision SHA/bytes, optional default exact fleet.target/1 and STRICT baseline reference. Require same-node source/executor. Bind an iteration/job before reservation by explicit target or project default, then freeze target/generations, source/checkpoint, session revision and writer identity. Explicit conflict with an existing frozen target is rejected. Default changes apply only to new work; no alias/fallback re-resolution after freeze.
* Reuse immutable revisions and CAS/operation recovery; do not duplicate mutable project history at gateway. Old projects/jobs remain unverified/unbound without fabricated historical target identity; expose explicit migration/qualification source action and stable legacy replay adapter. Return distinct offline/revoked/binding drift/missing artifact/unresolved execution status.
* STRICT comparison covers exact target/root/generations, observed terminal/compiler builds, tester model/config/effective period, set/include/input hashes, broker/server when relevant and available history evidence. Missing fields yield UNVERIFIED, mismatch is INCOMPATIBLE with bounded field reasons. Candidate source SHA differs normally and is retained as evidence, not equality prerequisite. Cross-target comparison never auto-promotes.

## 057N acceptance

* Separate `fleet.native/1` canonical request/journal namespace from legacy request hashing/index; include frozen target, input identity, normalized logical config and build policy. Preserve legacy replay bytes and fixed MT5-2 behavior.
* Exact identity/binding/session/dedicated-tester qualification before reservation, compiler deployment and process creation; revalidate before deploy/start/test/capture/cancel/result promotion. Compiler copies are effects and cannot precede admission. Never use caller qualification flags or alias fallback. Qualification factory defaults to denied unless installed trusted physical evidence bound to exact candidate/runtime/roots is verified; source/fixture success cannot certify physical MT5.
* Common native ownership/lease remains exclusion authority through M3; capture/cancel validate exact job/process creation identity/executable. Integrate existing producer ownership protocol where possible; uncertain process/descendant/persistent handoff cannot close authority or grant new work. No force-clear/TTL/PID guessing.
* Source runtime exposes a useful routed orchestration adapter with safe production denial and explicit test adapter separation, not an unused target dictionary. SDK positive capability remains unqualified until user tests; provide exact manifest/qualification run instructions. All source failures preserve provenance and bounded errors.
* Tests: frozen defaults/conflicts/reopen/CAS, STRICT matrix including missing historical identity and candidate source difference, same-node violation, legacy hash invariance, every effect boundary zero calls on stale/unqualified target, interrupted reservation/start/result and exact cancellation. No real MT5/session mutation.

Report per TIP and coordinate transport/journal interfaces. Do not modify another Builder's fleet modules. Root coordinates facade/MCP/CLI integration after interfaces stabilize.
