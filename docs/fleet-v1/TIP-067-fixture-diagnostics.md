# TIP-067 — Preserve source fixture callback and authorization diagnostics

Contractor dispatch, 2026-10-06, within approved continuous source refinement.
Parent candidate `7ebff6b6d3dcfa47a0696b0f571826276bbbda88`, tree
`31bda92fa74f91598cb54234fba4f30cfe800b4d`, is NOT ACCEPTED: original
attempt1 workflows five success, three failure. Accepted ancestor remains
`fe6ef1baa359ea2acbba7e3e0f78ae872ed1c55f`. Draft PR65 stays open/unmerged;
main remains `70e2112da9fe8eaa6262f2ba896b55bf3e078260`.

## YAGNI-3 and observed gaps

1. Needed: integrated Windows capacity-normal retains one UNKNOWN job and
   ARMED/ACQUIRED scope but loses the callback exception. Deep update retains
   native authorization expiry plus worker return timeout without safe grant
   timing. Bootstrap retains main/cleanup HTTPS timeouts sampled at reserve_nonce
   COMMIT. These observations do not establish their storage/scheduling cause.
2. Reuse: original callbacks, signed grants, verifier clock invocation, long
   fixture worker-failure capture and post-cleanup identity union, existing
   bounded owner drain, original exception objects and durable uncertainty.
3. Smallest scope: test_tip064_capacity_https.py and test_tip064_integration.py
   only, plus bounded controlled diagnostic regressions and reports/evidence.
   No production, dependency, policy, signed TTL or fixture budget changes.

## Implementation and acceptance contract

Capture exact original capacity reserve/start callback exceptions before the
native journal converts them to UNKNOWN. Keep their identity, cause and notes;
observe them before/after completion predicates and retain the identity-deduplicated
union of observation, callback and cleanup errors after actual bounded cleanup.
Preserve UNKNOWN results, ARMED scopes, pending/uncertain resources and all old
capacity positive assertions. Do not convert uncertainty into success or add retries.

Record at most32 finite safe timing rows around existing long callback BEGIN and
REQUIRE boundaries. Issued/expires fields may come from existing proof/grant;
current_ms must be the value returned by the existing verifier clock call, with
exactly its original call count. Preserve the original return/error and restore
any fixture-local instrumentation. No global clock/require patches, additional
authority clock calls, request replay, body/secret/path/identifier dumps or cache.
Diagnostic failure must not mask the original callback/authorization error.

Meaningful controls prove exact callback identity and notes, durable UNKNOWN with
ARMED retained, primary/late-callback/cleanup union, unchanged success and callback
counts, real signed expiry denial with finite observed timing, and safe omission
of malformed/sensitive fields. Keep the existing negative/positive profiles and
all their phase, nonce, owner, target and deadline assertions.

Builder implements and tests after this dispatch. Contractor independently reviews
the frozen diff and verifies selected integration and diagnostic controls. Any
published candidate requires its own eight original exact-head attempt1 workflow
successes, all five ZIP identities/manifests/JUnit and nine harmless proof receipts;
failed original parent evidence remains authoritative and retained externally.
No docs-only successor to repair stale headers. PR/external receipts decide status.

## Deferred runtime and physical gates

Fresh server_info/health at21:30 ICT still return raw MCP -32603. READY/PIDs/
queue/locks, old synchronous unit outcome and current IPC/login remain UNKNOWN.
Async start/get test APIs remain absent from this session's78 callable names.
No VPS test rerun, restart, deployment, ownership initialization, package/service
or native demo is permitted by missing current guards. The two failed old demo
jobs remain FAILED/NOT_RUN and FIFO overlap remains NOT_EXERCISED. Full Fleet
physical qualification, real SDK/private VM/two-node and production merge OPEN.
