# TIP083 — Positive diagnostic-fault signed grant profile

Parent: `bc75b9369b6bc284ca84fdad93df1b45d0690428` (TIP082).

The parent original Bootstrap attempt failed only the publish variant of
`test_long_broken_observation_keeps_original_worker_unknown_and_restores_step`.
The original verifier raised `NATIVE_AUTHORIZATION_EXPIRED`; execute handled
that error and returned UNKNOWN before the injected begin_effect fault was
observed. The unchanged three-second worker return barrier consequently
supplied a timeout as the primary error, followed by the diagnostic error,
instead of the intended callback fault followed by the diagnostic error.
The captured whole-execute duration is not grant age or a physical phase
measurement; the historical physical latency owner remains UNKNOWN.

This contract deliberately changes only the two mark/publish positive
diagnostic-fault cases to an explicit structured profile with signed
authorization_ms=2000 and positive_transport=True. Two seconds was not their
previous contract. The existing maximum signed TTL remains 2000; the profile
retains the original positive HTTP/heartbeat 5000 allowance. The callback
fault occurs before this fixture's later intentional-expiry assertion.

On the exact parent, external seven-control research passed once (JUnit
13.690s, process14.027911s, cap120s, retries0). Independent Contractor research
passed seven controls once (JUnit13.744s, process14.024912s, cap120s, retries0).
Both preserved all229 published source entries. A genuine signed start-grant
response held1.05s before original verification reproduces expiry for1000
and reaches the intended fault/diagnostic union for2000. The expired instance
is bound through handled_signal.error_index and its original require frame;
signed TTL arithmetic, original delegates, real clock reads and closed
worker/resource owners are checked. No grant was renewed, no extra require
was added and no authority clock was replaced by the external research.
The existing signed-expiry1000 negative still runs its original assertions.

All other LONG_FIXTURE_PROFILE callers and1000 expiry negatives are unchanged.
Worker return3, composed startup10/stop3, generic lifecycle defaults,
production authorization/verifier logic and clocks, maximumTTL2 seconds,
durable FULL/WAL work, full-suite cap600 and proof cap120 remain unchanged.
There are no retries, new skips/xfails, application/workflow/dependency changes
or regular cases added/deleted. A genuine expiry beyond this positive
allowance still fails; this is an explicit fixture contract change rather
than a proven physical latency correction.

Exactly two profile case identities change truthfully:

| Parent identity suffix | Candidate identity suffix |
| --- | --- |
| `[mark-1000]` | `[mark-positive-2000]` |
| `[publish-1000]` | `[publish-positive-2000]` |

The other1583 identities retain their full order, and total cases remain1585.
Both case bodies, fault injection, error identity/notes and cleanup assertions
remain byte-for-byte unchanged. Contractor independent candidate validation,
one reviewed publication and all eight fresh original-attempt CI gates are
required before source acceptance. Physical Fleet installation/activation,
private VM/SDK qualification and pilot remain deferred OPEN.
