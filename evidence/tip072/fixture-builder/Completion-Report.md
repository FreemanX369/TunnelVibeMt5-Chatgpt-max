# TIP072F — self-contained TIP024 fake SDK fixture

STATUS: DONE locally; candidate publication/full CI/deployment NOT_RUN. Contractor independent verification remains required.

Implemented the authorized test-only correction in `tests/unit/test_tip024_multiclient_concurrency.py`: three new fixture setup statements create the missing fake `mcp.server.mcpserver.exceptions` module, provide its fake ToolError class, and install it with the existing monkeypatch lifecycle. Strict production SDK imports are unchanged. The registration/catalog/context assertions, test identities/counts, original deadlines and process budgets remain unchanged.

YAGNI-3 was answered in the Contractor TIP072F contract before implementation: the old fake test needed isolated execution, the existing ModuleType/monkeypatch fixture was reused, and only its missing imported exception surface was added. No dependency, global preload, fallback import, production or MCP surface change was needed.

| Check | Result | Wall seconds | Source manifest |
|---|---|---:|---|
| Retained original isolated case on parent/current |FAIL before correction|0.472 / 0.474|unchanged|
| Corrected isolated case, fresh process, no unrelated module collection |1 PASS / 0 SKIP|0.472|217 unchanged|
| Original five-module compatibility command |229 PASS / 1 existing SKIP / 0 FAIL|9.104|217 unchanged|
| Frozen TIP072 controls |31 PASS / 0 SKIP|0.528|217 unchanged|
| Truly missing required exception module, fresh incomplete fake-provider process |Expected strict SDK-required RuntimeError and exact ModuleNotFoundError cause observed; exit0|see receipt|217 unchanged|

The single skip is the existing `test_harmless_windows_api_and_structure_construction` in `test_tip057r_sdk` (actual Win32 API construction requires Windows). These test selections overlap and must not be added as distinct coverage. The TIP024 provider is explicitly a stub; none of its success proves real SDK, physical Fleet, or VPS qualification. The missing-exception control confirms the production SDK import still fails when the required module truly does not exist.

Frozen hashes:

- TIP072 concurrency production remains `0bf1db9cf1a97c36714bcc87f6229922f8d666b38d904ab0534a7c4aff474db4`.
- TIP072 new 31-case test remains `8e238ed853dea1d1283c07ac12bde9c2166e339fb14178edd1e74de573494d81`.
- TIP024 old test `07f822793d3ad08d946e0dedade8f2b2ba3b0f6b07631cd7ec851d112cbfcc3c` becomes `e33edee22aa54f3ca8fe5f91177324f9fdf6bdd147993781ec431160b0a7e7ee`.

`scope.json` records an AST proof: old fixture statements remain in exactly the original order, only three new nodes were inserted, and the entire module AST outside that named fixture body is unchanged. Source-before/after-fixture manifests show only the authorized TIP024 test changed relative to TIP072's frozen 217 paths. Every verification run captures before/after source manifests and exact bounded commands in receipts; `verify.py` records the complete workflow. Original pre-fix file bytes are retained as `test-tip024-before.py`; all old TIP072 failures and earlier diagnosis evidence remain intact. `git diff --check` passes.

FILES CHANGED: one existing test fixture; new evidence only in this bounded evidence directory. ISSUES/DEVIATIONS: none for TIP072F. No source commit, publication, CI rerun, VPS mutation, service restart, MT5 or live trading action was taken. Full-source CI and current runtime gates still need independent checking. The original TIP071 CI6/8 rejection, unknown original Windows FIFO owner/mechanism, separate Deep capacity timeout, current MCP outage, and deferred physical qualifications remain unresolved.
