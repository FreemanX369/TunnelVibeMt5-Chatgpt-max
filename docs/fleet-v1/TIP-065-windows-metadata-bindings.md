# TIP-065 — Reuse constant Windows retained-metadata ABI bindings

Continuous Contractor contract, 2026-10-05. Frozen parent
81d458ffce7a856a94aae3fb2166d0a9943fba7e, tree
e1ed18128f047baab88f0c5efa2bc0159289de83, completed 6/8 on original attempt 1.
Deep run 37293992261/job 111710798184 passed 1205, failed one, skipped 12. Its
capacity delayed-release fixture timed out while still observing held work, at
the original poll's 1000-ms cap. The sampled server was resolving a ctypes
function symbol inside retained_file_metadata, reached through fresh source
manifest verification. Cleanup independently timed out at a job-result COMMIT.
Integrated Windows passed 1205, had one setup error and 12 skips: ordinary
control backup exceeded its existing 1000-ms progress deadline. Linux passed
1202/16 skips. The [failed-candidate receipt](evidence/tip065/ci-81d458f/metadata/verification-receipt.json)
binds original decoded logs with retained BOM/CRLF, five official ZIP sizes/digests,
unchanged 210-entry exact Git source manifests, both complete JUnit sets and nine
harmless proof receipts. All 29 earlier required Windows controls passed; this
does not replace the failed eight-workflow gate.

## YAGNI-3 before code

1. Necessary: retained_file_metadata recreates three constant ctypes Structure
   classes, a kernel32 wrapper and function prototype on every fresh metadata
   observation. A bounded source-manifest read performs three observations per
   file. Actual Deep sampled precisely this repeated binding path.
2. Reuse: memoize only the immutable Windows ABI definitions and typed function
   binding. Every call still allocates independent result buffers and performs
   the same three OS queries using its current retained file handle.
3. Smallest scope: one existing product file and one focused test file. Preserve
   every fresh metadata/path/hash/source/authority observation and budget. No
   file-data, authority, signature, roster or decision cache is introduced.

Builder may modify only app/vibemql5/fleet/scoped_resources.py and add
tests/unit/test_tip065_windows_metadata_bindings.py. Use a small lazy helper
for reusable ctypes ABI definitions and GetFileInformationByHandleEx binding.
Keep Linux behavior and all handle conversion, information-class order 18/0/1,
success/error checks, identity tuple layout, buffer types, size/attribute checks,
retained-path reopen and fresh bounded read/hash behavior unchanged. Keep
_open_retained_read unchanged. Retain the binding's owning library reference.
Concurrent calls must own distinct output buffers; cold first-call duplication
of pure ABI setup is harmless, but no shared mutable observation is permitted.

Meaningful controlled tests must demonstrate reuse of library/function setup
across different handles; three fresh OS queries and distinct buffers per call;
changed metadata actually changes the next observation; an OS-query failure
raises rather than serving prior metadata; invalid reparse/directory/deleted/
negative-size metadata still fails. A concurrent-call control must demonstrate
distinct buffers and handle-specific observations. Keep controlled tests
portable with a fake Windows ABI boundary and label them synthetic. Existing
actual harmless Windows retained-handle positive/negative cases stay mandatory
in candidate CI. Do not describe a fake ABI result as physical qualification.

Run focused scoped/signed-roster/capacity/preflight tests once, retain complete
before/after source manifests, exact command/environment/log/JUnit, and freeze a
Builder completion report. Contractor reviews the implementation and runs its
own meaningful verification before publishing a new candidate. Root owns Git,
receipt preservation, reports, PR update and deployment.

This removes proven repeated pure ABI setup; its timing effect and the underlying
COMMIT/backup/storage/scheduling causes remain unproven. No fixed-speed assertion
or claim that old failures are repaired is allowed. No timeout change, authority
relaxation, missing-check elimination, reduced durability, retry, CI rerun,
UNKNOWN/evidence reset, main commit, account/credentials/AutoTrading action or
generic PowerShell. The five-file legacy observation overlay remains byte-frozen
and is deployable only after the delivered head's own 8/8 and complete artifact
gate. Full Fleet activation and physical VM/MT5/SDK qualification remain OPEN.
