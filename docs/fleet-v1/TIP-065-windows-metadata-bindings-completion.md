# TIP-065 — Windows metadata ABI reuse completion

Contractor review under the continuous authorization, 2026-10-05. This is a
bounded source optimization at frozen parent 81d458ff, not a historical timeout
root-cause fix. The [contract](TIP-065-windows-metadata-bindings.md) records the
actual 6/8 parent failure; [original receipts](evidence/tip065/ci-81d458f/metadata/verification-receipt.json)
preserve every failed result alongside the passed proofs. No CI rerun occurred.

## Concrete change

Only app/vibemql5/fleet/scoped_resources.py and one new semantic test file change
source. A lazy maxsize-one helper reuses constant FileId/Basic/Standard definitions,
the typed GetFileInformationByHandleEx binding and its owning kernel32 reference.
Each observation still converts the current fd, allocates independent buffers,
performs information classes 18/0/1 and evaluates identical success/error, size and
attribute checks. The identity tuple, POSIX branch, retained path reopen/read/hash,
both manifest verification passes, TLS, signatures, authority, FULL/WAL durable
commits and every existing budget remain unchanged. Cached metadata/data/authority/
rosters/decisions are not introduced. Concurrent cold pure binding duplication is
harmless; mutable output buffers are never shared.

## Evidence and independent review

Before any product edit, original 81d versus proposed prototype passed 16 controlled
equivalence cases: tuples, error types/args, class order, field types/sizes/offsets,
handle conversion, last_error/WinError and warm changed-handle/error sequences.
The product bytes remained exact 81d during that proof. The transplanted helper and
metadata function have the verified prototype's exact AST; retained-file open has
the original AST. Those tests are explicitly synthetic ABI evidence.

Builder focused verification: **93 PASS/4 explicit platform skips**, no errors or
failures. It included both original actual-TLS capacity modes, the original
blocked-native/lost-ACK fixture, scoped/gateway admission, ordinary restore and
deployment observations, with 211 source entries unchanged during the run.

Contractor independently reviewed exact old/new AST and every source byte. All
other product AST, all ctypes class definitions, the POSIX branch, 88 other app
files and 209 other parent source entries remain unchanged; one new test adds the
211th manifest entry. Independent focused verification: **141 PASS/7 explicit
platform skips**, no errors/failures, 7.587s. Complete commands, logs, JUnit and
before/after manifests are [retained](evidence/tip065/windows-metadata-bindings-v1/contractor-receipt.json).
These overlapping focused counts are not added into a unique full-suite total.

Fourteen new permanent cases require fresh OS facts, changed observations,
current errors, denial of invalid metadata, current handle conversion, distinct
concurrent buffers and retained DLL ownership. Twelve controlled cases run
portably; two actual Win32 file cases require Windows CI. Existing actual harmless
Windows retained-handle/replacement/write-denial and FIFO checks remain required.
No Windows platform skip is described as a passed real API observation.

Frozen product: 40595 bytes,
SHA256 66b37c4ed06ec896e2c4792cf9d2e72db3a9867eeadcd09cba1e921d04d19f9e.
New tests: 9218 bytes,
SHA256 0f6a465abac076a0543ed657b25fb7e7f11929c98fd50ebe226196b52c361fe6.
The five-file legacy overlay stays 97991 bytes,
SHA256 0efadd3d855b602e6bd8d58cd7033f092395026b633bceb28629e75fe4003182.

## Remaining gate

Removal of repeated pure ABI setup is proven; performance effect is UNMEASURED.
Historical owner-grant/result/backup/COMMIT/storage/scheduling causes remain
OPEN/UNKNOWN. The new candidate requires its own 8/8 workflows and complete exact
head/tree/digest/manifests/JUnit/proof verification. No green candidate can identify
those historical causes by itself.

The already-authorized deployment remains only five selected files plus the
qualified retained legacy MCP variant. Its installed tree must be reported MIXED,
not a complete Fleet candidate deployment. At this pre-CI checkpoint no TIP-065
checkpoint, write or restart has occurred; actual runtime stays TIP-053/0.2.42,
85 tools, fixed MT5-2, READY/idle. Final PR description and external receipt record
the delivered exact head and any later authorized overlay rollout. Full Fleet
configuration/connector registration, ownership migration and actual VM/MT5/SDK/
load/session qualification remain OPEN/NOT_RUN.
