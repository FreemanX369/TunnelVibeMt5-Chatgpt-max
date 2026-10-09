# TIP-066 — Independent Contractor verification

Status: FOCUSED_SOURCE_PASS; new exact-head CI/artifact gate remains required.
Parent source is accepted fe6ef1baa359ea2acbba7e3e0f78ae872ed1c55f, tree
e0881d89cca4663805af8de22e8ca7649a0f95f5. PR #65 stays Draft/open/unmerged;
main remains 70e2112da9fe8eaa6262f2ba896b55bf3e078260.

## Review and independently executed evidence

The production diff is one SDK ToolError import and 12 guarded lines at existing
_invoke. Both operation and complete error message must match the selected finite
sets. Rethrown expected errors retain their original exception as cause; every
other exception is re-raised unchanged. Actor scope still surrounds the facade
call and restores on every outcome. No facade, LiveTerminal, input/output signature,
catalog, backend runner, native lease, ownership, dependency, SDK driver or policy
implementation changes.

Independent real SDK and regression run: **167 PASS, 2 platform skips, zero
failure/error, 8.35s**. Command selects test_tip066_live_diagnostics,
test_tip040_live_terminal, test_tip043_chart_delivery, test_tip057rc1 and
test_tip065_deployment_preflight with current worktree/app on PYTHONPATH.
Original verbose summary/JUnit and the exact constrained environment are retained
under evidence/tip066/focused-final* and environment.lock.txt. Earlier independent
run 164/2, before the three added protocol-result cases, remains under
contractor-focused-v1*. Counts overlap and are not added.

The 47 new cases include actual SDK dispatch of all 15 operation/code combinations,
unexpected error masking and original identity/cause retention, native/ownership
denial pass-through, out-of-scope code handling, argument validation, unchanged
success payloads, actor restoration, routed target denial and complete schema
identity. Actual SDK protocol handler returns is_error=True for anticipated,
unexpected and invalid-input outcomes; only the safe known code is exposed.
This verifies the source SDK result contract, not the external connector's mapping.

All 85 input/output schemas match accepted parent digest
3e17166f81acf897aa3de3c55964e117923897c5658391de37d528c40d234f06.
MCP source SHA256 eb00f70d74b60d955e6eecc565b601652886366ac06009cc60ae4d659c1f4c9d.
The new test file is separately bound by the final candidate's source manifest.
Diff whitespace check PASS; only the MCP adapter changes among production app files.
The frozen TIP-065 overlay manifest and all four source-matching deployed files
remain unchanged. This full-source MCP is not the installed legacy variant.

## Environment and acceptance limits

The old saved interpreter and native dependency files were observed unusable before
tests. Their setup failures remain in Builder receipts. Tests use a fresh local
Python3.12.14 environment with existing requirements-bootstrap.lock constraints,
MCP2.1.1, pytest9.1.1 and cryptography50.0.1. No source dependency or VPS package
was changed. Fresh SDK tools/base.py and func_metadata.py hashes match the inspected
saved pure Python bytes; synchronous tool dispatch already uses anyio threads.

The new candidate needs eight original exact-head workflow successes plus exact
Git tree/manifests, five ZIP digests/sizes, complete JUnit and nine harmless proofs.
The PR description and external final receipt identify that outcome without a
docs-only successor commit. This focused report grants no deployment/physical status.

Fresh typed runtime observations preserve MCP -32603 envelopes under
evidence/tip066/runtime-observations. READY/PIDs/queue/locks, old synchronous unit
outcome, current IPC/login and external INVALID_ARGUMENT mapping remain UNKNOWN.
No restart, rerun, ownership initialization, full source replacement or native demo
ran. The two failed old jobs and unavailable feed remain failed/unavailable.
Full Fleet physical qualification and production merge remain OPEN/NOT_RUN.
