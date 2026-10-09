# TIP-065 — Long phase fixture independent completion

The [bounded contract](TIP-065-long-fixture-observation.md) is implemented in one
existing test file. Final file SHA256 is
`9db3aac856ec9f97a54d8582f024fb7f21edf6d2a68f9a33285f814bc076cb1b`
(70,547 bytes). The original test calls a shared actual TLS helper with a finite
ten-second positive aggregate observation. All individual HTTP, authorization,
control-round, SQLite, producer, delayed-return and cleanup bounds stay unchanged.
The producer callback is AST-identical to the rejected parent. Every original
success assertion remains, including expiry, distinct newer phase grant,
terminal ACK before future return, synthetic evidence and complete owner drain.

Original callback and wrapper BaseException objects are retained and raised on
the test owner thread; primary and cleanup errors remain grouped. Checks surround
the predicate and follow the pump. Seven controls exercise the actual shared
fixture: old five-second versus corrected ten-second bounded valid schedule,
callback exception identity/notes with and without cleanup failure, and wrapper
RuntimeError, pytest failure and false-wait assertion after terminal ACK. The
intentional cleanup-error control disposes already-idle journals before injecting
its error; it does not clear authority or close active worker journals.

Builder focused verification passed **65/0 skips** before that final control-only
resource-disposal refinement; its two affected controls then passed independently.
Contractor reviewed the final diff and ran a different, broader matrix on frozen
final bytes: **139 PASS/3 platform skips**, zero failures/errors, 142 JUnit cases,
40.534 seconds. It covers integration, gateway cleanup, transport deadlines and
native authorization. The final 211-entry source manifest is identical before
and after verification. Exactly one source entry differs from parent; all other
210 entries and all 89 app files are unchanged. Full commands, environment,
JUnit, logs, diff and manifests are retained under
[long-fixture-fix](evidence/tip065/long-fixture-fix/).

These are source/fixture results, not final candidate CI acceptance or physical
qualification. The original Bootstrap cause remains UNKNOWN; the controlled
experiments prove harness defects, not historical storage or scheduling latency.
Parent 30bcc584 remains rejected at 7/8 with its original receipt intact. The new
published head must independently pass all eight workflows and artifact checks.
No workflow rerun, product/dependency change, UNKNOWN reset, main commit, live
write or restart was performed. The byte-frozen five-file legacy overlay remains
gated; full Fleet activation and private VM/MT5/SDK acceptance stay OPEN/NOT_RUN.
