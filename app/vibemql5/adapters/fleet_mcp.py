"""Separate opt-in fleet MCP catalog; legacy catalog remains unchanged."""
from __future__ import annotations

import argparse
from typing import Any

from .fleet_client_tools import FleetClientFacade, FLEET_TOOL_NAMES


def create_server(config=None, *, client_facade=None):
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations
    client = client_facade or FleetClientFacade.from_config(config)
    server = MCPServer("VibeMQL5 Fleet Client", instructions=(
        "This optional catalog connects to one separately operated HTTPS gateway. "
        "Select exact device/route/terminal/generation references. Project and source history remain node-owned. "
        "Read submission returns a command ID; poll its status. Native jobs preserve durable global/node identity. "
        "A delivered ACK is not a completed native effect. UNKNOWN remains unresolved. "
        "Source/worktree operations require a gateway-issued verified principal and exact writer/project CAS. "
        "Caller MCP metadata or agent labels do not confer authentication. "
        "An absent installed physical qualification returns a truthful denial. Legacy tools are a separate catalog."
    ))
    read = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
    write = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

    @server.tool(annotations=read)
    def fleet_server_info() -> dict[str, Any]:
        """Show client catalog and credential boundary without opening a service."""
        return client.server_info()

    @server.tool(annotations=read)
    def fleet_inventory(node: dict[str, Any] | None = None, operation_id: str | None = None) -> dict[str, Any]:
        """Read cached devices or queue node terminal inventory; runtime fields stay unobserved."""
        return client.inventory(node, operation_id)

    @server.tool(annotations=read)
    def fleet_read_state(target: dict[str, Any], operation_id: str) -> dict[str, Any]:
        return client.read("get_terminal_live_state", target, operation_id)

    @server.tool(annotations=read)
    def fleet_read_account(target: dict[str, Any], operation_id: str) -> dict[str, Any]:
        return client.read("get_account_snapshot", target, operation_id)

    @server.tool(annotations=read)
    def fleet_read_status(command_id: str) -> dict[str, Any]:
        return client.read_status(command_id)

    @server.tool(annotations=read)
    def fleet_snapshot(targets: list[dict[str, Any]], operation: str = "get_account_snapshot") -> dict[str, Any]:
        """Bounded partial observations; no financial totals or deduplication."""
        return client.snapshot(targets, operation)

    @server.tool(annotations=read)
    def fleet_command_status(command_id: str) -> dict[str, Any]:
        return client.command_status(command_id)

    @server.tool(annotations=write)
    def fleet_project_create(node: dict[str, Any], operation_id: str, project_id: str, workspace: str,
                             ea: str, checkpoint_id: str, active_goal: str = "") -> dict[str, Any]:
        return client.domain("/fleet/v1/projects/create", node, operation_id,
            dict(project_id=project_id, workspace=workspace, ea=ea, checkpoint_id=checkpoint_id, active_goal=active_goal))

    @server.tool(annotations=write)
    def fleet_project_enroll(node: dict[str, Any], operation_id: str, project_id: str,
                             expected_session_revision: str, expected_session_sha256: str,
                             default_target: dict[str, Any] | None = None,
                             strict_baseline: dict[str, Any] | None = None) -> dict[str, Any]:
        return client.domain("/fleet/v1/projects/enroll", node, operation_id,
            dict(project_id=project_id, owner_device_id=node["device_id"], expected_session_revision=expected_session_revision,
                 expected_session_sha256=expected_session_sha256, default_target=default_target, strict_baseline=strict_baseline))

    @server.tool(annotations=read)
    def fleet_project_get(node: dict[str, Any], operation_id: str, project_id: str) -> dict[str, Any]:
        return client.domain("/fleet/v1/projects/get", node, operation_id, {"project_id": project_id})

    @server.tool(annotations=write)
    def fleet_project_default_target(node: dict[str, Any], operation_id: str, project_id: str,
                                     target: dict[str, Any], expected_placement_revision: int) -> dict[str, Any]:
        return client.domain("/fleet/v1/projects/default-target", node, operation_id,
            dict(project_id=project_id, target=target, expected_placement_revision=expected_placement_revision))

    @server.tool(annotations=write)
    def fleet_project_freeze(node: dict[str, Any], operation_id: str, project_id: str, frozen_id: str,
                             writer_id: str, expected_placement_revision: int, expected_session_revision: str,
                             expected_session_sha256: str, target: dict[str, Any] | None = None) -> dict[str, Any]:
        return client.domain("/fleet/v1/projects/freeze", node, operation_id,
            dict(project_id=project_id, frozen_id=frozen_id, writer_id=writer_id, expected_placement_revision=expected_placement_revision,
                 expected_session_revision=expected_session_revision, expected_session_sha256=expected_session_sha256, target=target))

    @server.tool(annotations=read)
    def fleet_project_resume(node: dict[str, Any], operation_id: str, frozen_id: str) -> dict[str, Any]:
        return client.domain("/fleet/v1/projects/resume", node, operation_id, {"frozen_id": frozen_id})

    @server.tool(annotations=read)
    def fleet_compare_baseline(node: dict[str, Any], operation_id: str, baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        return client.domain("/fleet/v1/projects/baseline", node, operation_id, dict(baseline=baseline, candidate=candidate))

    @server.tool(annotations=write)
    def fleet_launch_job(operation_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Queue fleet.native/1 with an already frozen same-node placement."""
        return client.launch_job(operation_id, request)

    @server.tool(annotations=read)
    def fleet_get_job(global_job_id: str) -> dict[str, Any]:
        return client.get_job(global_job_id)

    @server.tool(annotations=read)
    def fleet_recover_job(operation_id: str, global_job_id: str, node: dict[str, Any], session_id: str) -> dict[str, Any]:
        """Request a quarantined historical receipt; leaves the original job fenced."""
        return client.recover_job(operation_id, global_job_id, node, session_id)

    @server.tool(annotations=write)
    def fleet_cancel_job(node: dict[str, Any], operation_id: str, global_job_id: str,
                         process_identity: dict[str, Any]) -> dict[str, Any]:
        return client.domain("/fleet/v1/jobs/cancel", node, operation_id, dict(global_job_id=global_job_id, process_identity=process_identity))

    @server.tool(annotations=read)
    def fleet_artifact_manifest(node: dict[str, Any], operation_id: str, scope: dict[str, Any]) -> dict[str, Any]:
        """Registered artifact ID/global/local job/target/hash only; no OS path."""
        return client.domain("/fleet/v1/artifacts/manifest", node, operation_id, scope)

    @server.tool(annotations=read)
    def fleet_artifact_chunk(node: dict[str, Any], operation_id: str, scope: dict[str, Any]) -> dict[str, Any]:
        return client.domain("/fleet/v1/artifacts/chunk", node, operation_id, scope)

    @server.tool(annotations=write)
    def fleet_principal_issue(request: dict[str, Any]) -> dict[str, Any]:
        return client.principal("issue", request)

    @server.tool(annotations=write)
    def fleet_principal_revoke(request: dict[str, Any]) -> dict[str, Any]:
        return client.principal("revoke", request)

    @server.tool(annotations=write)
    def fleet_principal_assign(request: dict[str, Any]) -> dict[str, Any]:
        return client.principal("assign", request)

    @server.tool(annotations=write)
    def fleet_principal_release(request: dict[str, Any]) -> dict[str, Any]:
        return client.principal("release", request)

    @server.tool(annotations=write)
    def fleet_principal_reconcile(request: dict[str, Any]) -> dict[str, Any]:
        """Owner approves only the durable original incomplete session commit."""
        return client.principal("reconcile", request)

    @server.tool(annotations=write)
    def fleet_writer_acquire(node: dict[str, Any], operation_id: str, request: dict[str, Any]) -> dict[str, Any]:
        return client.domain("/fleet/v1/writers/acquire", node, operation_id, request)

    @server.tool(annotations=write)
    def fleet_writer_release(node: dict[str, Any], operation_id: str, request: dict[str, Any]) -> dict[str, Any]:
        return client.domain("/fleet/v1/writers/release", node, operation_id, request)

    @server.tool(annotations=write)
    def fleet_write_source(node: dict[str, Any], operation_id: str, request: dict[str, Any]) -> dict[str, Any]:
        return client.domain("/fleet/v1/sources/write", node, operation_id, request)

    @server.tool(annotations=write)
    def fleet_worktree_prepare(node: dict[str, Any], operation_id: str, request: dict[str, Any]) -> dict[str, Any]:
        return client.domain("/fleet/v1/worktrees/prepare", node, operation_id, request)

    @server.tool(annotations=write)
    def fleet_worktree_commit(node: dict[str, Any], operation_id: str, request: dict[str, Any]) -> dict[str, Any]:
        return client.domain("/fleet/v1/worktrees/commit", node, operation_id, request)

    @server.tool(annotations=write)
    def fleet_worktree_retire(node: dict[str, Any], operation_id: str, request: dict[str, Any]) -> dict[str, Any]:
        return client.domain("/fleet/v1/worktrees/retire", node, operation_id, request)

    if tuple(server._tool_manager._tools) != FLEET_TOOL_NAMES:
        raise RuntimeError("FLEET_CATALOG_MISMATCH")
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vibemql5-fleet-mcp")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    create_server(args.config).run(transport="stdio")


if __name__ == "__main__":
    main()
