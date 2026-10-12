# TIP084 — Scoped implementation and validation contract

Parent: `4760e95f0f8ec869bb15a3184b824cdd26430337`.

The candidate implements the independently qualified Group C negative
observation contract in exactly three source entries:

- `tests/unit/test_tip064_integration.py`: optional phase observer with exact
  handled-error binding, original worker-return failure and pre-anchor failure
  propagation.
- `tests/unit/test_tip079_fixture_failure_isolation.py`: explicit opt-in only
  for the controlled pre-callback case, matching the original recovery context.
- `tests/unit/test_tip080_startup_readiness_and_handled_error.py`: explicit
  opt-in for controlled verifier failure and genuine signed start expiry.

Together with these two TIP084 documents, the intended staged diff is five
paths. The source footprint remains 229 entries: three fixture entries differ,
226 are unchanged, including all 89 application entries, eight workflows and
dependencies. All 1585 regular identities and order remain unchanged.

The new negative bound is prerequisite observation 10 plus terminal
observation 10, up to 20 seconds. Original worker 3, cleanup 3, signed TTL 1000,
maximum TTL 2000, positive aggregate 5/10 and full-suite cap 600 remain unchanged.
The positive callback/ACK/drain path and existing assertions are preserved.

External evidence comprises 13/13 Builder controls and 13/13 independent
Contractor controls on the exact parent. Builder candidate validation is
recorded in the accompanying frozen `CompletionReport.json`, focused receipt
and full-unit receipt: focused cap 300, full cap 600, retries 0, PID and ten-second
heartbeats, terminal child closure and unchanged source/payload attestation.
Validation must preserve all original 1585 identities/order and the 41 original
local platform skips; focused validation preserves the 169 parent cases.

These implementation and local receipts do not assert remote source
acceptance. Contractor review, independent candidate testing, one reviewed
publication and eight original exact-head CI gates are still required.

No Group A TTL feasibility fix is included. Genuine grant expiry remains
denied, original uncertainty is preserved, and the existing 6/8 TIP083 source
gate is not waived. No application/runtime change, restart, installation,
account/trade action, physical qualification, commit, push or deployment is
performed by the Builder validation.
