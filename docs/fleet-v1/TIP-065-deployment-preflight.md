# TIP-065 — Read-only deployment preflight

Contractor contract, 2026-10-05. Continue the approved [Blueprint](blueprint.md),
[continuous source plan](continuous-build-2026-10-03.md) and ownership boundary.
The owner's 2026-10-05 instruction authorizes tests and deployment; this contract
does not add per-TIP approval. Physical migration and qualification remain separate.

## Concrete trigger and YAGNI-3

PR #65 source head `f25ec99e174a662928b05db5c21f92c5ef47a0cc` passed all eight
workflows. Thirty-one new modules were staged with create-only CAS on the VPS.
The live adapter remains TIP-053/0.2.42 with 85 tools. Its existing observations do
not expose ownership installation state or cryptography package metadata.

1. Needed now: bounded, sanitized observations of those two activation blockers.
2. Reuse: existing ownership validation, SHA-256 implementation, `server_info`,
   and finite operator CLI. Preserve all authority/admission semantics.
3. Smallest implementation: one observer module, pure shared helpers, one additive
   `server_info` result field and one read-only CLI command. No new MCP tool, public
   recovery operation, installer, process manager or migration architecture.

## Builder boundary

Extract pure marker/snapshot validation from `OwnershipAuthority.load`, preserving
its existing read/error priority, accepted shapes and guard behavior. `status()`
must not be called: it takes a filesystem guard. Share a pure byte-digest helper
with provenance rather than reopening an already checked snapshot to hash it.

Observe only root-fixed native ownership marker/state and scoped-install presence.
Limit each authority file to 64 KiB, reject unsafe/nonregular paths, bound parsing,
and compare two observations for concurrent/incomplete reads. This is an unlocked,
non-atomic observation, never a retained admission proof. Return finite reasons
for missing, invalid, migrating, mismatched, active, closed and unreadable states.
Do not emit epochs, tokens, operations, process identities/images or raw contents.
No missing/invalid/UNKNOWN state may become CLOSED or READY by fallback.

Package facts use standard-library metadata only, without importing MCP,
cryptography, SDK or MT5/native execution libraries. Read-only Windows OS file
metadata queries through standard-library ctypes are permitted solely to compare
retained/fresh file handles without fd/path stat aliases; they confer no process,
admission or physical qualification. Query/reparse/identity failures remain incomplete.
Evaluate ordinary release versions against
Python >=3.12,<3.13; MCP >=2.1,<3; cryptography >=50,<51. Missing, malformed or
unsupported version syntax must remain explicitly unevaluated. Metadata matching
does not establish binary loading, wheel/DLL compatibility or physical qualification.

Optional identity hashes are bounded to fixed observer/validator/provenance/adapter
source files (1 MiB each). Describe them as on-disk bytes, not loaded-module identity.
No arbitrary viewer or config/credential/journal collection is introduced.

The CLI command must bypass facade/concurrency construction and all configuration
loading. It may print a completed observation but must not report activation success.
Every output explicitly leaves physical qualification NOT_RUN and activation
NOT_QUALIFIED, including an observed matching CLOSED snapshot.

The [Builder completion report](TIP-065-completion.md) records frozen source,
focused verification, retained initial fixture failure and prepared overlay. Contractor
independently verified 606 old/new validator and read-fault outcomes, 115 focused
passes/two Windows skips, a cold CLI import/observation audit with no effects or
execution package loading, and the exact two-addition overlay with all legacy schemas
retained. These local checks precede the new canonical candidate's eight-workflow gate.

## Independent acceptance

Builder tests meaningful absent/fault/concurrent snapshots, no filesystem mutations,
network/process/package loading, malformed/out-of-range metadata, CLI isolation and
unchanged 85-tool catalog/input schemas. Contractor reviews extraction equivalence,
safe bounded reads and failure sanitization, then independently runs appropriate
tests and full source proofs. Every new candidate requires its own 8/8 CI and exact
head/tree, original ZIP digests, source manifests, JUnit and proof verification.

## Deployment slice

Prepare a separate overlay against the retained live MCP bytes. Only the observer
import and additive result field may change that adapter. Deliver verified observer
and shared helper dependencies with checkpoint/CAS. Retain old concurrency/facade,
compiler/jobs/tester behavior, 85 tools and all backend allowlists. Independently
compare overlay schemas and run the finite live test suites before restarting only
the supported MCP runtime. Read back hashes, READY/idle state and preflight facts.

The [deployment manifest](config/tip065-legacy-overlay.json) binds all five target
file hashes, the retained/derived adapter identities and distinct schema baselines
into the canonical source manifest and integrated ZIPs. Four deployed files match
candidate Git blobs; the MCP adapter is explicitly the independently reviewed
two-addition legacy variant. A mixed installed tree is never called the complete
candidate installation. Empty expected SHA on the new observer is server-enforced
create-only CAS; an INVALID_ARGUMENT preflight result is not absence evidence.

Do not activate the entire source adapter, install packages, initialize ownership,
start Fleet gateway/node/client services, select credentials/accounts, change
AutoTrading, clear UNKNOWN/evidence or merge/commit directly to main. Any missing
physical migration/configuration/service/connector qualification stays OPEN. Existing
failed CI receipts and the original masked owner-grant cause remain preserved.

## Baseline verification

At contract creation, PR #65 remained open/draft at the exact source head above;
main remained `70e2112da9fe8eaa6262f2ba896b55bf3e078260`. All eight current
workflow runs concluded success. This baseline gate does not qualify TIP-065.
