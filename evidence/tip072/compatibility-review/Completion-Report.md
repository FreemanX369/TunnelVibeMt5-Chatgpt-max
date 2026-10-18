# TIP072 bounded compatibility causal review

STATUS: DIAGNOSIS DONE; existing compatibility remains FAIL. No production/test edit, commit, CI rerun, or VPS action performed.

The original TIP072 compatibility failure is pre-existing on exact parent `e9f668a049288eb899c580a6b8147e5caedae585`. TIP024's local fake SDK creates `mcp.server.mcpserver` as a non-package module and does not provide `mcp.server.mcpserver.exceptions.ToolError`. The unchanged production adapter imports that symbol, raises ModuleNotFoundError, and preserves its strict SDK-required RuntimeError. This is a fake-fixture import-order defect; no evidence here attributes it to the TIP072 concurrency change.

| Probe | Cases | Result | Wall seconds | Source entries unchanged |
|---|---:|---|---:|---:|
| Prior frozen current compatibility |230|228 PASS / 1 SKIP / 1 FAIL|10.864|217|
| Parent bounded runtime/test subset |230|228 PASS / 1 SKIP / 1 FAIL|8.943|186|
| Parent complete exact source manifest |230|228 PASS / 1 SKIP / 1 FAIL|8.945|216|
| Parent isolated TIP024 registration test |1|FAIL|0.472|186|
| Current isolated same test |1|FAIL|0.474|217|
| Parent same test plus collected TIP066 actual SDK module |48|48 PASS|8.094|186|

The same failing test and RuntimeError occur on parent/current. These suites overlap and do not represent additive coverage. The first parent archive extracted app/tests/workflows/pyproject paths only; the complete-parent probe additionally materialized every remaining tracked frozen config/operator/dependency path from exact Git blobs before running the same command. The initial subset evidence is retained and clearly labeled. `scope-complete.json` verifies every complete parent path against Git, 216 paths total; current has 217 paths, unchanged before/after, and differs only at the two authorized TIP072 paths.

Source hashes remain:

- `app/vibemql5/core/concurrency.py`: `0bf1db9cf1a97c36714bcc87f6229922f8d666b38d904ab0534a7c4aff474db4`.
- `tests/unit/test_tip072_native_denied_publication.py`: `8e238ed853dea1d1283c07ac12bde9c2166e339fb14178edd1e74de573494d81`.
- Unchanged adapter: `eb00f70d74b60d955e6eecc565b601652886366ac06009cc60ae4d659c1f4c9d`.

The SDK-collected control demonstrates why the defect can be masked: collection imports the real `mcp.server.mcpserver.exceptions` child module before execution of the old fake test, which replaces its ancestor modules but leaves the child cached in sys.modules. `create_server` can then import cached ToolError. This is observed import-order dependence, not evidence of physical SDK/Fleet acceptance. The real SDK controls remain real SDK tests; the TIP024 test remains a fake registration/catalog/context test.

Commands and evidence are in `review.py`, each `*-receipt.json` (exact argv/environment/limits/counts), raw logs, JUnit files, before/after manifests, `parent-archive-sha256.txt`, and `scope-complete.json`. All subprocess limits are 180 seconds or less; no pytest deadline/assertion was modified. Owned archive source is retained separately; operator files were only materialized for hash equivalence and never executed.

YAGNI-3 for proposed next correction, before any implementation:

1. Necessary: the existing fake registration contract must work in isolation and bounded compatibility rather than relying on incidental sys.modules cache state.
2. Reuse: the existing fake ModuleType + monkeypatch fixture already supplies the SDK registration surface; extend that fixture's one missing imported exception module, keeping catalog/context assertions and strict production imports unchanged.
3. Shortest: in TIP024's existing fake fixture, provide a local exception ModuleType exposing a minimal fake ToolError class and monkeypatch its exact sys.modules key. No adapter fallback, production import relaxation, dependency change, global preloader, or wider architecture.

This suggestion changes an existing test and therefore exceeds the TIP072 two-path contract. Contractor should authorize a separate bounded fixture correction or explicitly extend the scope, then delegate implementation. Verification should prove isolated fresh-process TIP024 success and the same original 230-case compatibility command with unchanged assertions and unrelaxed budgets, then independently verify frozen TIP072 source. Original TIP072 compatibility FAIL receipts must remain. Full source CI remains NOT_RUN for TIP072; source gate is not accepted by these local probes. Original Windows FIFO mechanism, Deep capacity timeout, and runtime MCP outage remain separate unresolved questions.
