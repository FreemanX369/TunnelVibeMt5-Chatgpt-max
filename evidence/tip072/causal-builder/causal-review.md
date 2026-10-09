# TIP-072 bounded causal review — no implementation

Exact source: `e9f668a049288eb899c580a6b8147e5caedae585`, tree `29426b4fa2fdf0aefbcc4e0273b1f465d5b554c3`; worktree `tip071-builder` remains clean. Only owned scratch probe/evidence files were written.

## Finding and limits

The original Windows attempt proves that waiter B aborted in `_publish_owner()` at `os.open(O_CREAT|O_EXCL|O_WRONLY)` with `PermissionError: [Errno 13]` for its native `.active.lock`. The original FIFO assertion saw `['C']` instead of `['B', 'C']`. Its traceback contains no owner payload, observed live identity, or `winerror` at the failing call. **Whether the denied publication had a valid live owner is UNKNOWN. The Windows physical cause is UNKNOWN.**

The bounded probe proves a separate, conditional admission defect: if this exact observed error result occurs while a valid native owner is independently confirmed live, current source aborts the queued waiter and deletes its ticket, although the owner still prevents admission. This is reproducible with real source, native owner publication, FIFO tickets, ownership authority and OS process observation, with **only the observed errno13 boundary result injected**. It is not a physical Windows reproduction and does not establish that this verified-owner condition held in the original CI failure.

The ordinary existing-file control uses real `FileExistsError`, returns `False` and preserves the owner. In the modeled errno13 case, B's ticket exists at denial, live identity matches the real HOLD owner, owner bytes are unchanged, the original exception object escapes, B's ticket is removed, and C later wins after HOLD release. Authority remains CLOSED. The probe completed with exit 0 in 0.064 seconds; raw traceback and receipt are preserved.

Eight negative qualification controls—missing owner, corrupt JSON, foreign namespace, wrong live identity, blank token, denied owner read, wrong error filename and non-native lease—are UNQUALIFIED. All preserve the exact original error object and owner bytes or absence. These controls exercise a **read-only proposal model**, not a production patch. No path is reclaimed or deleted by that model and it never grants a lease.

## Exact source references

- `app/vibemql5/core/concurrency.py:164–175`: owner payload records schema, namespace, token, pid and native identity.
- `concurrency.py:261–284`: `_remove_dead_owner()` returns `False` for both a live owner and invalid/unreadable evidence. Its return value cannot qualify this denial as live contention.
- `concurrency.py:286–300`: native authority transaction remains CLOSED; publication only catches `FileExistsError`; errno13 escapes.
- `concurrency.py:317–350`: existing FIFO deadline/poll is bypassed by the escaping exception; cleanup removes B's owned ticket.
- `concurrency.py:352–389`: token release behavior is separate and unchanged.
- `app/vibemql5/core/jobs.py:78–97`: `_read_json_object(attempts=1)` reads once and propagates denied or invalid evidence.
- `app/vibemql5/core/native_ownership.py:33–38,42–158`: `_identity_valid` plus `ObservedProcess.identity()` verifies process lifetime and independently observed image, with a retained OS handle.
- `tests/unit/test_tip024_multiclient_concurrency.py:152–169`: original HOLD/B/C fixture and original FIFO assertion remain unchanged.

Source SHA256 (identical before/after probe):

| File | SHA256 |
| --- | --- |
| `app/vibemql5/core/concurrency.py` | `af7fb5cc3817a460491d8710d77deacae66d0ba2c93e249d738b602fe1a264da` |
| `app/vibemql5/core/jobs.py` | `096d32b968dd54cbaeb5374f17a1855d1fdd523ff54b256a3083d0bae634bcd4` |
| `app/vibemql5/core/native_ownership.py` | `73183b02324d9e29b72c60f2e7b8b1e1c5e1e07fd6f5742dc3c3690857273514` |

## Smallest safe correction proposal — pending TIP-072 contract

YAGNI-3:

1. **Need:** keep a queued native waiter eligible when denied publication nevertheless has affirmative, independently verified live-owner evidence. Errno13 alone supplies no such evidence.
2. **Reuse:** existing owner JSON read with `attempts=1`, `_identity_valid`, `ObservedProcess`, native authority transaction and FIFO deadline/poll. Do not reuse ambiguous `_remove_dead_owner() == False` as affirmative proof.
3. **Shortest:** one narrow `PermissionError` branch in `_publish_owner()` and a private read-only qualification predicate. Return `False` (NOT_ADMITTED) only if errno is EACCES, error filename exactly matches this root's native `runs/.active.lock`, path is an ordinary file without symlink/reparse indirection, owner schema/namespace/token/pid/identity are valid and distinct from this attempted token, and actual live process identity equals the recorded identity. Otherwise re-raise the original denial. Read/parse/identity failure is unqualified. Do not remove/reclaim/grant from this branch.

Qualification after denial can race owner release; returning `False` only causes another existing poll and cannot admit a lease. All actual admission remains the existing exclusive publication under CLOSED authority. No budget, TTL, wait interval, assertion, authority, schema, namespace cleanup or producer/release behavior changes are proposed.

Suggested meaningful acceptance: original-source negative proof for modeled denied publication with actual verified owner; fixed-source FIFO B then C with no effects before owner release; both ordinary FileExists and qualified denial retain B's ticket; all eight unqualified controls preserve original denial; actual bad path/permission denial without qualified owner never becomes waiting; no deletion/reclamation on the new branch; original native authority blocking still rejects; successful publication/release and existing ownership/concurrency compatibility still pass. Windows integrated CI is a later gate, not proof available from this Linux probe.

## Windows primary documentation

Microsoft `_open` documents multiple meanings for EACCES and a distinct EEXIST result for exclusive creation of an existing file: <https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/open-wopen?view=msvc-170>. Microsoft `DeleteFile` documents access-denied creation during delete-pending state: <https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-deletefile>. These semantics make errno13 ambiguous; they do not identify the original failure's mechanism.

The separate Deep capacity-normal pump expiration, earlier capacity guard timeout and live MCP outage remain UNKNOWN. This proposal makes no claim about any of them. Original CI failures and attempt 1 are preserved. No source/test edit, commit, publication, CI rerun, full suite or VPS action occurred in this review.
