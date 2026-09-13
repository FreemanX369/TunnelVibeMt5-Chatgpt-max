# TIP-028 implementation evidence

Status: implementation verified; production promotion pending Owner approval.

## Scope

- Expose optional `operation_id` and `expected_revision_sha256` for `update_project_session`.
- Expose optional `operation_id` for direct `launch_test`.
- Bind ProjectSession retries to a canonical request SHA so a reused operation ID with a different request fails closed.
- Qualify existing JobStore restart reconciliation and ArtifactManager pinned-retention behavior.
- No EA, strategy, terminal policy, tool-name catalog, database, broker, scheduler, or daemon change.

## Backend evidence

- Pre-mutation checkpoints:
  - `BADMCP-20260913-220623-E99C23D0` — facade/MCP.
  - `BADMCP-20260913-220839-9ACD63CE` — ProjectSession operation fingerprint.
- Mutation receipts:
  - `BADMIN-20260913-220929-A29898E1` — project_sessions.py.
  - `BADMIN-20260913-220946-A6A6A116` — facade.py.
  - `BADMIN-20260913-221001-138C1EF3` — mcp.py.
  - `BADMIN-20260913-221049-A8FF3D2E` — focused test file.
- `py_compile`: PASS.
- Unit suite: 373 passed.
- Baseline-aware suite: 373 passed; baseline failures 0; current failures 0; new failures none.

## Promotion boundary

Runtime restart, live MCP schema acceptance, merge, and continuity promotion are intentionally deferred until explicit Owner approval.
