# Research refinement: primary failure and capacity entry attribution

TIP scope: source qualification only. Input parent is immutable
`9c7b2fd4fc346e8efccec7751b05d406be4b9d58`, tree
`e5b482bfb4e895f4d2d463c201acdfba105f1a3a`.

## Evidence and hypotheses

Run38695553482 attempt1 is terminal FAILURE. Linux full suite:1615PASS/18SKIP;
Windows:1619PASS/2FAIL/12SKIP,0ERROR,1633cases,614.266s, no900s timeout.
Both source manifests234 and APP89 match exact Git bytes before/after.
All1611original case identities/order are preserved. Windows12skip identities
match the partial baseline Windows log; that baseline has no terminal JUnit,
so exact historical Windows skip-message equality is NOT_ATTESTED.

1. CONFIRMED: the guarded-source case immediately closes a dispatcher with
   active work after an HTTPS_UNAVAILABLE error. DOMAIN_WORKERS_ACTIVE is
   raised during cleanup. The TLS diagnostic sampled the gateway in SQLite
   commit; accumulated transaction-exit times and TLS latency were high.
   Storage/scheduling latency is a hypothesis, not proof of a defective disk,
   antivirus cause, deadlock, or a product authorization bug.
2. CONFIRMED: TIP077 positive failed because an unchanged finite pump did not
   reach its predicate; its failure is retained together with CALLBACK and
   SCOPE_RELEASE. Entry-pump state exists but was not published, so the
   failing pump phase cannot be conclusively attributed from the short JUnit.
3. NOT_REPRODUCED: prior six-phase authorization observation. Current positive
   and negative each have FIRST/SECOND reserve/start only, observation errors0,
   rows dropped0. No filtering or changed exact-four assertion is justified.

## Change and acceptance criteria

YAGNI: preserve the primary exception and existing bounded cleanup; reuse
preserve_fixture_failure and close_dispatcher_fixture. Add only an opt-in
summary of already collected entry state; no additional HTTP/SQL/predicate
calls, worker gates or verifier clock reads.

- AC1: guarded-source cleanup uses the existing drain with seconds3 and
  preserves primary identity, cause, notes and primary/cleanup union.
- AC2: two real composed-fixture controls inject WireError or pytest Failed
  at the original pump and verify real owner closure and exception identity.
- AC3: entry summary states whether the original first pump failed, its
  existing duration/budget, predicate count and first/last values, and the
  two scheduled component durations. No IDs, user paths or exception text.
- AC4: two controls prove summary failure cannot mask an active primary or
  mutate the source observation state. Process interrupts still propagate.
- AC5: a new exact-head focused14 attempt precedes full context on each
  ephemeral CI VM, cap120, retries0; full suite remains cap900. Any focused
  failure blocks full dispatch. Both receipts and JUnit are always uploaded.
- AC6: full inventory should be1637=1611original+26controls, source234/APP89.
  Original assertions, skips, HTTP1000/5000, TTLs, joins, worker holds and
  entry10/negative3 budgets are unchanged. No APP/dependency changes.

BUILD and VERIFY are separate phases of one AI; this patch is not independently
agent-reviewed. CI supplies execution evidence, not an independent human review.
Passing a fresh run does not identify the cause of the earlier TLS/pump latency.
Keep the previous failure artifacts, TIP088-44 UNKNOWN and local e7 UNKNOWN.
Do not rerun/reset those attempts. No source promotion or physical release claim.

Rollback is the parent research commit. Main, PR65, runtime, SDK/MT5 installation,
accounts, credentials, AutoTrading and authority markers are outside this patch.
