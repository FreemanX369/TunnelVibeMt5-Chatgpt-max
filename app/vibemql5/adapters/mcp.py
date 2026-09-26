"""MCP connection adapter for ChatGPT / other MCP clients.

TIP-015C / Bridge 0.2.12 keeps trading/runtime semantics unchanged while adding
read-only durable observability for iteration revisions, fault receipts, and job history.
The MCP surface grows only by those three read-only tools. Streamable HTTP remains
loopback-only; Secure MCP Tunnel uses stdio in production.
"""
from __future__ import annotations
from vibemql5.backend_admin import register_backend_admin_tools

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any

from .. import __version__
from ..config import default_root
from ..contracts import MCP_TOOL_CATALOG_SHA256, MCP_TOOL_COUNT, MCP_TOOL_NAMES, RESULT_SCHEMA_VERSION
from ..core.facade import ToolFacade
from ..core.concurrency import actor_from_mcp_context, actor_scope
from ..core import workspace as workspace_module
from ..core.provenance import load_bridge_provenance, sha256_file
from .ex5_widget import EX5_INGRESS_WIDGET_HTML, EX5_INGRESS_WIDGET_SCHEMA_VERSION, EX5_INGRESS_WIDGET_URI
from .live_chart_widget import LIVE_CHART_WIDGET_HTML, LIVE_CHART_WIDGET_SCHEMA_VERSION, LIVE_CHART_WIDGET_URI


def _runtime_provenance(root: Path | None = None) -> dict[str, Any]:
    workspace_path = Path(workspace_module.__file__).resolve()
    mcp_path = Path(__file__).resolve()
    if root is None:
        candidate = mcp_path.parents[3]
        root = candidate if (candidate / "config" / "build-provenance.json").is_file() else default_root()
    canonical = load_bridge_provenance(Path(root))
    return {
        "bridge_build": canonical["bridge_build"],
        "bridge_version": canonical["bridge_version"],
        "provenance_schema": canonical["schema_version"],
        "mcp_tool_count": canonical["mcp_tool_count"],
        "mcp_tool_catalog_sha256": canonical["mcp_tool_catalog_sha256"],
        "pid": os.getpid(),
        "runtime_mode": os.environ.get("VIBEMQL5_RUNTIME_MODE", "manual"),
        "supervisor_generation": os.environ.get("VIBEMQL5_SUPERVISOR_GENERATION", ""),
        "supervisor_session_id": os.environ.get("VIBEMQL5_SUPERVISOR_SESSION_ID", ""),
        "workspace_module_path": str(workspace_path),
        "workspace_module_sha256": sha256_file(workspace_path),
        "mcp_module_path": str(mcp_path),
        "mcp_module_sha256": sha256_file(mcp_path),
    }


def create_server(root: Path, transport: str = "unknown"):
    try:
        from mcp.server.mcpserver import MCPServer, Context
        from mcp.types import CallToolResult, ResourceLink, TextContent, ToolAnnotations
    except ImportError as exc:
        raise RuntimeError('MCP SDK v2 is required. Run: pip install -e ".[mcp]"') from exc

    # MCP SDK 2.1 evaluates postponed annotations with inspect.signature(..., eval_str=True).
    # These SDK types are imported lazily inside create_server(), so publish them into
    # function.__globals__ before decorators inspect nested tool signatures. This preserves
    # the direct CallToolResult return contract without making MCP a module-import dependency.
    globals().update({
        "CallToolResult": CallToolResult,
        "ResourceLink": ResourceLink,
        "TextContent": TextContent,
        "ToolAnnotations": ToolAnnotations,
        "Context": Context,
    })

    facade = ToolFacade(root)

    def _invoke(ctx: Context, operation: str, fn):
        # TIP-024 provenance only: stdio does not expose authenticated ChatGPT account identity.
        actor = actor_from_mcp_context(ctx, transport=transport)
        actor["operation"] = operation
        with actor_scope(actor):
            return fn()

    # TUN-11 startup recovery: converge durable cancel intents after MCP/controller
    # restart. Only cancel_requested jobs are touched and process signalling remains
    # exact-identity bound inside JobManager.
    startup_cancel_recovery = facade.reconcile_cancelled_jobs(wait_seconds=0.5)
    server = MCPServer(
        "VibeMQL5 Bridge",
        instructions=(
            "VibeMQL5 controls a fixed MT5-2 Strategy Tester backend in multi-client serialized mode. "
            "Use a distinct project_id per logical ChatGPT workstream. For durable multi-session work, create/update a project session and call resume_project_session before continuing after reconnect/restart. "
            "Existing-source mutations are fail-closed: read_source/get_source_hash, create_checkpoint, then pass exact expected_sha256 and checkpoint_id to write_source/apply_patch; restore_checkpoint requires expected_current_sha256. "
            "All direct native compiles and Strategy Tester jobs share one FIFO MT5 execution lease. Compile source-driven EAs before launching tests. For a user-supplied compiled EX5, prefer import_ex5 when ChatGPT fileParams binding works. If host attachment binding is unavailable, call open_ex5_ingress so the user can upload/select the EX5 in the ChatGPT widget; the widget calls app-only import_ex5_authorized_file and returns the same immutable ea_binary_ref. Pass that ref to launch_test; imported binaries must not be recompiled. Tests are asynchronous: launch_test returns a job_id; "
            "use bounded get_job long-polling and then read_result. Restore the checkpoint when acceptance fails. "
            "backend_run_powershell executes caller-supplied PowerShell as the Bridge Windows identity, requires confirm=true, and shares the same serialized mutation/native locks. It is not sandboxed, cannot identify the ChatGPT account, and must not be used to print secrets or credentials. "
            "capture_live_chart returns image/png, an inline viewer, and a hash-bound PNG ResourceLink for the same bytes. Present the returned file link when a download is requested; export_file(scope='exports', source_id=file_export.source_id, expected_sha256=file_export.sha256) can retrieve it later without recapturing. The MCP image block alone does not prove final chat visibility. "
            "For user-requested downloads, call export_file only on scoped VibeMQL5 artifacts; never request arbitrary filesystem paths."
        ),
    )
    read_only_local = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
    reversible_chart_capture = ToolAnnotations(
        read_only_hint=False,  # A minimized MT5 chart is temporarily restored, then minimized again.
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    @server.tool(annotations=read_only_local)
    def server_info() -> dict[str, Any]:
        """Return adapter version, root, active MCP transport and fixed tester terminal."""
        canonical = load_bridge_provenance(root)
        return {
            "name": "VibeMQL5 Bridge",
            "version": __version__,
            "bridge_build": canonical["bridge_build"],
            "tool_count": MCP_TOOL_COUNT,
            "tool_catalog_sha256": MCP_TOOL_CATALOG_SHA256,
            "tool_names": list(MCP_TOOL_NAMES),
            "tool_visibility": {
                "server_catalog_count": MCP_TOOL_COUNT,
                "model_visible_expected_count": MCP_TOOL_COUNT - 1,
                "app_only_tools": ["import_ex5_authorized_file"],
            },
            "generic_shell_exposed": True,
            "root": str(root),
            "transport": transport,
            "fixed_terminal": facade._fixed_terminal(),
            "mcp_sdk": "2.x",
            "source_checkpointing": "native-persistent",
            "result_schema": RESULT_SCHEMA_VERSION,
            "continuity_schema": "1.0",
            "project_session_schema": "1.0",
            "file_export_schema": "1.0",
            "file_export_max_bytes": 16777216,
            "binary_ingress_schema": "1.0",
            "binary_ingress_max_bytes": 16777216,
            "binary_ingress_extensions": [".ex5"],
            "binary_ingress_transport": "openai/fileParams",
            "binary_ingress_transports": ["openai/fileParams", "chatgpt/widget-authorized-url"],
            "binary_ingress_widget_schema": EX5_INGRESS_WIDGET_SCHEMA_VERSION,
            "binary_ingress_widget_uri": EX5_INGRESS_WIDGET_URI,
            "binary_ingress_widget_render_tool": "open_ex5_ingress",
            "binary_ingress_widget_import_tool": "import_ex5_authorized_file",
            "binary_ingress_widget_source": "CHATGPT_WIDGET_FILE_IMPORT",
            "binary_ingress_receipt_schema": "1.0",
            "binary_ingress_receipt_resolver": "get_ex5_import_receipt",
            "live_chart_widget_schema": LIVE_CHART_WIDGET_SCHEMA_VERSION,
            "live_chart_widget_uri": LIVE_CHART_WIDGET_URI,
            "live_chart_widget_render_tool": "capture_live_chart",
            "live_chart_file_delivery": "hash-bound-mcp-resource-link",
            "live_chart_file_export_scope": "exports",
            "runtime_capture_schema": "1.0",
            "runtime_capture_transport": "job-bound/pss-proof+bounded-live-stream",
            "runtime_capture_profiles": ["private"],
            "runtime_capture_binding": "serialized-single-agent-v1",
            "cancel_recovery_schema": "1.0",
            "multi_client_concurrency_schema": "1.0",
            "multi_client_mode": "SERIALIZED_SHARED_VPS",
            "authenticated_client_identity": False,
            "generic_shell_exposed": True,
            "startup_cancel_recovery": startup_cancel_recovery,
            "runtime_provenance": _runtime_provenance(root),
        }

    @server.tool(annotations=read_only_local)
    def health() -> dict[str, Any]:
        """Fast operational health check: resources, queue and MT5 inventory count."""
        return facade.health()

    @server.tool(annotations=read_only_local)
    def get_terminal_live_state(ctx: Context) -> dict[str, Any]:
        """Read account, connection and ping from the running fixed MT5-2 terminal on request."""
        return _invoke(ctx, "get_terminal_live_state", facade.get_terminal_live_state)

    @server.tool(annotations=read_only_local)
    def get_account_snapshot(ctx: Context) -> dict[str, Any]:
        """Read live Balance/Equity/Free Margin/Leverage and trade state; no trading calls."""
        return _invoke(ctx, "get_account_snapshot", facade.get_account_snapshot)

    @server.tool(annotations=read_only_local)
    def list_live_charts(ctx: Context) -> dict[str, Any]:
        """Enumerate chart windows owned by the exact fixed MT5-2 process; EA/indicator UNKNOWN."""
        return _invoke(ctx, "list_live_charts", facade.list_live_charts)

    @server.resource(LIVE_CHART_WIDGET_URI, mime_type="text/html;profile=mcp-app")
    def live_chart_widget_resource() -> str:
        """Render the captured PNG inside the chat with a direct PNG download link."""
        return LIVE_CHART_WIDGET_HTML

    @server.tool(
        meta={
            "ui": {"resourceUri": LIVE_CHART_WIDGET_URI, "visibility": ["model", "app"]},
            "openai/outputTemplate": LIVE_CHART_WIDGET_URI,
            "openai/toolInvocation/invoking": "Capturing MT5-2 chart",
            "openai/toolInvocation/invoked": "Chart captured",
        },
        annotations=reversible_chart_capture,
    )
    def capture_live_chart(ctx: Context, chart_id: int, aspect_ratio: str = "16:9") -> CallToolResult:
        """Capture one MT5-2 chart as 960x540 PNG; return an image, viewer and PNG file link."""
        from mcp.types import ImageContent
        meta, png = _invoke(ctx, "capture_live_chart", lambda: facade.capture_live_chart(chart_id, aspect_ratio))
        exported = meta["file_export"]
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(meta, sort_keys=True, separators=(",", ":"))),
                     ImageContent(type="image", data=base64.b64encode(png).decode("ascii"), mime_type="image/png"),
                     ResourceLink(type="resource_link", uri=exported["uri"], name=exported["file_name"],
                                  title=exported["file_name"], description=f"MT5-2 chart PNG SHA-256 {exported['sha256']}",
                                  mime_type="image/png", size=exported["bytes"])],
            structured_content=meta,
        )

    @server.tool(annotations=read_only_local)
    def read_terminal_journal(ctx: Context, source: str = "journal", limit: int = 100) -> dict[str, Any]:
        """Read bounded sanitized tail of MT5 Journal or Experts log; source=journal|experts."""
        return _invoke(ctx, "read_terminal_journal", lambda: facade.read_terminal_journal(source, limit))

    @server.tool(annotations=read_only_local)
    def inspect_terminal(ctx: Context, include_logs: bool = False) -> dict[str, Any]:
        """One on-demand account/network/chart observation; optionally include bounded logs."""
        return _invoke(ctx, "inspect_terminal", lambda: facade.inspect_terminal(include_logs))

    @server.tool()
    def diagnose() -> dict[str, Any]:
        """Deep diagnostics for VibeMQL5 configuration and MT5 inventory."""
        return facade.diagnose()

    @server.tool()
    def runtime_status() -> dict[str, Any]:
        """Read supervisor/watchdog recovery state without exposing credentials."""
        return facade.runtime_status()

    @server.tool(annotations=read_only_local)
    def get_continuity(project_id: str) -> dict[str, Any]:
        """Read the current integrity-verified Continuity Manifest."""
        return facade.get_continuity(project_id)

    @server.tool(annotations=read_only_local)
    def read_continuity_events(
        project_id: str,
        after_seq: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Read immutable SHA-linked continuity events without changing state."""
        return facade.read_continuity_events(project_id, after_seq, limit)

    @server.tool(annotations=read_only_local)
    def verify_continuity(project_id: str) -> dict[str, Any]:
        """Verify continuity chains, heads and operation indexes without mutation."""
        return facade.verify_continuity(project_id)

    @server.tool(
        annotations=ToolAnnotations(
            title="Append audited continuity event",
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    def append_continuity_event(
        ctx: Context,
        project_id: str,
        event_type: str,
        payload: dict[str, Any],
        operation_id: str,
        expected_manifest_revision: int,
        expected_manifest_sha256: str = "",
    ) -> dict[str, Any]:
        """Append one typed event using operation idempotency and exact manifest CAS."""
        return _invoke(ctx, "append_continuity_event", lambda: facade.append_continuity_event(
            project_id,
            event_type,
            payload,
            operation_id,
            expected_manifest_revision,
            expected_manifest_sha256,
        ))

    @server.tool()
    def create_continuity_checkpoint(
        ctx: Context,
        project_id: str,
        label: str,
        operation_id: str,
        expected_manifest_revision: int,
        expected_manifest_sha256: str,
    ) -> dict[str, Any]:
        """Create an immutable cryptographic resume anchor for the exact continuity head."""
        return _invoke(ctx, "create_continuity_checkpoint", lambda: facade.create_continuity_checkpoint(
            project_id,
            label,
            operation_id,
            expected_manifest_revision,
            expected_manifest_sha256,
        ))

    @server.tool()
    def reconcile_continuity(
        ctx: Context,
        project_id: str,
        operation_id: str,
        expected_manifest_revision: int,
        expected_manifest_sha256: str = "",
    ) -> dict[str, Any]:
        """Reconcile durable event/manifest side effects using exact current-head CAS."""
        return _invoke(ctx, "reconcile_continuity", lambda: facade.reconcile_continuity(
            project_id,
            operation_id,
            expected_manifest_revision,
            expected_manifest_sha256,
        ))

    @server.tool()
    def list_project_sessions() -> list[dict[str, Any]]:
        """List durable EA development sessions and their latest verified revision."""
        return facade.list_project_sessions()

    @server.tool()
    def get_project_session(project_id: str) -> dict[str, Any]:
        """Read the latest integrity-verified immutable project-session revision."""
        return facade.get_project_session(project_id)

    @server.tool()
    def create_project_session(
        ctx: Context,
        project_id: str,
        workspace: str,
        ea: str,
        active_goal: str = "",
        decision_refs: list[str] | None = None,
        phase: str = "IDLE",
        checkpoint_id: str = "",
        baseline_job_id: str = "",
        last_job_id: str = "",
    ) -> dict[str, Any]:
        """Create REV-000001 and bind it to the current byte-accurate EA source state."""
        return _invoke(ctx, "create_project_session", lambda: facade.create_project_session(
            project_id, workspace, ea, active_goal, decision_refs or [], phase,
            checkpoint_id, baseline_job_id, last_job_id,
        ))

    @server.tool()
    def update_project_session(
        ctx: Context,
        project_id: str,
        expected_revision: str,
        active_goal: str | None = None,
        decision_refs: list[str] | None = None,
        phase: str | None = None,
        checkpoint_id: str | None = None,
        baseline_job_id: str | None = None,
        last_job_id: str | None = None,
        operation_id: str = "",
        expected_revision_sha256: str = "",
    ) -> dict[str, Any]:
        """Append an immutable session revision with optional operation idempotency and SHA CAS."""
        return _invoke(ctx, "update_project_session", lambda: facade.update_project_session(
            project_id, expected_revision, active_goal, decision_refs, phase,
            checkpoint_id, baseline_job_id, last_job_id,
            operation_id, expected_revision_sha256,
        ))

    @server.tool()
    def update_project_session_v2(
        ctx: Context,
        project_id: str,
        expected_revision: str,
        operation_id: str,
        expected_revision_sha256: str,
        active_goal: str | None = None,
        decision_refs: list[str] | None = None,
        phase: str | None = None,
        checkpoint_id: str | None = None,
        baseline_job_id: str | None = None,
        last_job_id: str | None = None,
    ) -> dict[str, Any]:
        """Append a session revision with required operation idempotency and SHA CAS."""
        return _invoke(ctx, "update_project_session_v2", lambda: facade.update_project_session(
            project_id, expected_revision, active_goal, decision_refs, phase,
            checkpoint_id, baseline_job_id, last_job_id,
            operation_id, expected_revision_sha256,
        ))

    @server.tool()
    def resume_project_session(project_id: str) -> dict[str, Any]:
        """Validate source/checkpoint/job references before continuing a prior project session."""
        return facade.resume_project_session(project_id)

    @server.tool()
    def start_iteration(
        ctx: Context,
        project_id: str,
        expected_session_revision: str,
        expected_session_revision_sha256: str,
        expected_source_sha256: str,
        expected_source_bytes: int,
        mutation: dict[str, Any],
        preset: str = "smoke",
        set_file: str = "",
        overrides: dict[str, Any] | None = None,
        timeout_seconds: int = 0,
    ) -> dict[str, Any]:
        """Create one durable guarded iteration bound to exact session/source CAS values."""
        return _invoke(ctx, "start_iteration", lambda: facade.start_iteration(
            project_id, expected_session_revision, expected_session_revision_sha256,
            expected_source_sha256, expected_source_bytes, mutation,
            preset, set_file, overrides or {}, timeout_seconds,
        ))

    @server.tool()
    def get_iteration(iteration_id: str) -> dict[str, Any]:
        """Read the current immutable guarded-iteration revision."""
        return facade.get_iteration(iteration_id)

    @server.tool()
    def list_iterations() -> list[dict[str, Any]]:
        """List durable guarded iterations without changing state."""
        return facade.list_iterations()

    @server.tool()
    def resume_iteration(ctx: Context, iteration_id: str, expected_revision: str, expected_revision_sha256: str) -> dict[str, Any]:
        """Advance/reconcile a guarded iteration using exact iteration revision CAS."""
        return _invoke(ctx, "resume_iteration", lambda: facade.resume_iteration(iteration_id, expected_revision, expected_revision_sha256))

    @server.tool()
    def accept_iteration(ctx: Context, iteration_id: str, expected_revision: str, expected_revision_sha256: str) -> dict[str, Any]:
        """Explicitly accept DECISION_PENDING and advance the project session exactly once."""
        return _invoke(ctx, "accept_iteration", lambda: facade.accept_iteration(iteration_id, expected_revision, expected_revision_sha256))

    @server.tool()
    def reject_iteration(ctx: Context, iteration_id: str, expected_revision: str, expected_revision_sha256: str) -> dict[str, Any]:
        """Reject a guarded candidate and reconcile byte-exact checkpoint restore."""
        return _invoke(ctx, "reject_iteration", lambda: facade.reject_iteration(iteration_id, expected_revision, expected_revision_sha256))

    @server.tool()
    def cancel_iteration(ctx: Context, iteration_id: str, expected_revision: str, expected_revision_sha256: str) -> dict[str, Any]:
        """Persist cancellation intent, stop the exact bound job, and rollback only after stop proof."""
        return _invoke(ctx, "cancel_iteration", lambda: facade.cancel_iteration(iteration_id, expected_revision, expected_revision_sha256))

    @server.tool()
    def read_iteration_history(iteration_id: str, limit: int = 100, newest_first: bool = True) -> dict[str, Any]:
        """Read integrity-checked immutable iteration revisions without mutating state."""
        return facade.read_iteration_history(iteration_id, limit, newest_first)

    @server.tool()
    def list_fault_receipts(limit: int = 100, newest_first: bool = True) -> dict[str, Any]:
        """Read durable TIP-015B crash receipts directly; never arm, clear, or trigger faults."""
        return facade.list_fault_receipts(limit, newest_first)

    @server.tool()
    def list_job_history(limit: int = 100, newest_first: bool = True, workspace: str = "", state: str = "") -> dict[str, Any]:
        """List integrity-checked durable async job records with optional read-only filters."""
        return facade.list_job_history(limit, newest_first, workspace, state)

    @server.tool()
    def list_workspaces() -> list[str]:
        """List source workspaces available to ChatGPT."""
        return facade.list_workspaces()

    @server.tool()
    def list_terminals() -> list[dict[str, Any]]:
        """List registered MT5 terminals. Execution remains fixed to MT5-2 by policy."""
        return facade.list_terminals()

    @server.tool()
    def list_eas(workspace: str) -> list[str]:
        """List .mq5 Expert Advisors inside one workspace."""
        return facade.list_eas(workspace)

    @server.tool()
    def list_presets() -> list[str]:
        """List tester presets such as smoke and validation."""
        return facade.list_presets()

    @server.tool()
    def list_parameter_sets(workspace: str) -> list[str]:
        """List .set files inside one workspace."""
        return facade.list_parameter_sets(workspace)

    @server.tool()
    def read_source(workspace: str, path: str) -> dict[str, Any]:
        """Read an allowed source file together with its SHA-256."""
        return facade.read_source(workspace, path)

    @server.tool()
    def get_source_hash(workspace: str, path: str) -> dict[str, Any]:
        """Return byte-accurate SHA-256/size metadata for one source file."""
        return facade.get_source_hash(workspace, path)

    @server.tool()
    def create_checkpoint(ctx: Context, workspace: str, path: str, label: str = "") -> dict[str, Any]:
        """Persist an immutable byte-for-byte source checkpoint and return checkpoint_id."""
        return _invoke(ctx, "create_checkpoint", lambda: facade.create_checkpoint(workspace, path, label))

    @server.tool()
    def list_checkpoints(workspace: str, path: str = "") -> list[dict[str, Any]]:
        """List persisted checkpoints for a workspace, optionally filtered by source path."""
        return facade.list_checkpoints(workspace, path)

    @server.tool()
    def diff_checkpoint(workspace: str, checkpoint_id: str, context_lines: int = 3) -> dict[str, Any]:
        """Return a unified diff between a checkpoint and the current source."""
        return facade.diff_checkpoint(workspace, checkpoint_id, context_lines)

    @server.tool()
    def restore_checkpoint(
        ctx: Context,
        workspace: str,
        checkpoint_id: str,
        expected_current_sha256: str = "",
    ) -> dict[str, Any]:
        """Atomically restore checkpoint bytes; expected_current_sha256 CAS is mandatory in multi-client mode."""
        return _invoke(ctx, "restore_checkpoint", lambda: facade.restore_checkpoint(workspace, checkpoint_id, expected_current_sha256))

    @server.tool()
    def write_source(
        ctx: Context,
        workspace: str,
        path: str,
        content: str,
        expected_sha256: str = "",
        checkpoint_id: str = "",
    ) -> dict[str, Any]:
        """Atomically create/replace source; existing files require exact expected_sha256 plus checkpoint_id."""
        return _invoke(ctx, "write_source", lambda: facade.write_source(workspace, path, content, expected_sha256, checkpoint_id))

    @server.tool()
    def apply_patch(
        ctx: Context,
        workspace: str,
        path: str,
        replacements: list[dict[str, Any]],
        expected_sha256: str = "",
        checkpoint_id: str = "",
    ) -> dict[str, Any]:
        """Apply exact replacements atomically; expected_sha256 plus checkpoint_id are mandatory."""
        return _invoke(ctx, "apply_patch", lambda: facade.apply_patch(workspace, path, replacements, expected_sha256, checkpoint_id))

    @server.tool()
    def compile_ea(ctx: Context, workspace: str, ea: str) -> dict[str, Any]:
        """Compile one EA with fixed MT5-2; concurrent native operations are FIFO serialized."""
        return _invoke(ctx, "compile_ea", lambda: facade.compile_ea(workspace, ea, terminal="MT5-2", mock=False))

    @server.tool(
        meta={"openai/fileParams": ["file"]},
        annotations=ToolAnnotations(
            title="Import external EX5",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=True,
        ),
    )
    def import_ex5(
        ctx: Context,
        workspace: str,
        file: dict[str, Any],
        destination_path: str = "",
        expected_sha256: str = "",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Import one ChatGPT-supplied EX5 into immutable VibeMQL5 provenance.

        The top-level ``file`` field is declared through OpenAI's file-aware MCP
        metadata and is expected to contain an authorized temporary ``download_url``
        plus ``file_id``. Binary bytes are streamed directly, never base64/text encoded.
        Only workspace/Experts/*.ex5 is allowed. The returned ea_binary_ref must be
        supplied to launch_test for binary-only execution.
        """
        return _invoke(ctx, "import_ex5", lambda: facade.import_ex5(
            workspace, file, destination_path, expected_sha256, bool(overwrite)
        ))

    @server.resource(EX5_INGRESS_WIDGET_URI, mime_type="text/html;profile=mcp-app")
    def ex5_ingress_widget_resource() -> str:
        """Render the self-contained ChatGPT-native EX5 ingress widget."""
        return EX5_INGRESS_WIDGET_HTML

    @server.tool(
        meta={
            "ui": {"resourceUri": EX5_INGRESS_WIDGET_URI, "visibility": ["model", "app"]},
            "openai/outputTemplate": EX5_INGRESS_WIDGET_URI,
            "openai/widgetAccessible": True,
            "openai/toolInvocation/invoking": "Opening EX5 uploader",
            "openai/toolInvocation/invoked": "EX5 uploader ready",
        },
        annotations=ToolAnnotations(
            title="Open VibeMQL5 EX5 uploader",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    def open_ex5_ingress(
        workspace: str = "BD",
        destination_path: str = "Experts/WSLOW public v1.12.ex5",
        expected_sha256: str = "",
    ) -> CallToolResult:
        """Open a ChatGPT-native widget that can upload/select an EX5 and import it securely."""
        payload = {
            "schema_version": EX5_INGRESS_WIDGET_SCHEMA_VERSION,
            "workspace": workspace,
            "destination_path": destination_path,
            "expected_sha256": str(expected_sha256 or "").strip().lower(),
            "max_bytes": 16777216,
            "allowed_extensions": [".ex5"],
            "backend_tool": "import_ex5_authorized_file",
        }
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(payload, sort_keys=True, separators=(",", ":")))],
            structured_content=payload,
        )

    @server.tool(
        meta={
            "ui": {"visibility": ["app"]},
            "openai/widgetAccessible": True,
        },
        annotations=ToolAnnotations(
            title="Import widget-authorized EX5",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=True,
        ),
    )
    def import_ex5_authorized_file(
        ctx: Context,
        workspace: str,
        file_id: str,
        download_url: str,
        file_name: str,
        mime_type: str = "application/octet-stream",
        destination_path: str = "",
        expected_sha256: str = "",
        overwrite: bool = False,
    ) -> CallToolResult:
        """App-only fallback for a widget-authorized ChatGPT EX5 temporary URL.

        The model does not supply arbitrary URLs. The ChatGPT widget obtains file_id and
        a short-lived download URL using host APIs, and this tool reuses TIP-026's
        allowlisted downloader plus immutable EX5 store. The URL is never persisted.
        """
        result = _invoke(ctx, "import_ex5_authorized_file", lambda: facade.import_ex5_authorized_file(
            workspace, file_id, download_url, file_name, mime_type, destination_path,
            expected_sha256, bool(overwrite)
        ))
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result, sort_keys=True, separators=(",", ":")))],
            structured_content=result,
        )

    @server.tool(
        meta={"ui": {"visibility": ["model"]}},
        annotations=ToolAnnotations(
            title="Read canonical EX5 import receipt",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    def get_ex5_import_receipt(
        ctx: Context,
        mutation_operation_id: str = "",
        import_id: str = "",
        ea_binary_ref: str = "",
    ) -> dict[str, Any]:
        """Resolve exactly one canonical imported-EX5 identity selector.

        Supply exactly one of mutation_operation_id, import_id, or ea_binary_ref.
        Path, filename and expected-SHA lookup are intentionally unsupported.
        """
        return _invoke(ctx, "get_ex5_import_receipt", lambda: facade.get_ex5_import_receipt(
            mutation_operation_id, import_id, ea_binary_ref
        ))

    @server.tool()
    def launch_test(
        ctx: Context,
        workspace: str,
        ea: str,
        preset: str = "smoke",
        set_file: str = "",
        overrides: dict[str, Any] | None = None,
        timeout_seconds: int = 0,
        ea_binary_ref: str = "",
        operation_id: str = "",
    ) -> dict[str, Any]:
        """Launch an async MT5-2 test with optional durable operation idempotency."""
        timeout_seconds = int(timeout_seconds)
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be 0 (event-driven) or a positive number of seconds")
        if timeout_seconds > 86400:
            raise ValueError("timeout_seconds cannot exceed 86400 when explicitly set")
        return _invoke(ctx, "launch_test", lambda: facade.launch_test(
            workspace,
            ea,
            terminal="MT5-2",
            preset=preset,
            set_file=set_file or None,
            overrides=overrides or {},
            mock=False,
            test_timeout=timeout_seconds,
            ea_binary_ref=ea_binary_ref,
            operation_id=operation_id,
        ))

    @server.tool()
    def launch_test_v2(
        ctx: Context,
        workspace: str,
        ea: str,
        operation_id: str,
        preset: str = "smoke",
        set_file: str = "",
        overrides: dict[str, Any] | None = None,
        timeout_seconds: int = 0,
        ea_binary_ref: str = "",
    ) -> dict[str, Any]:
        """Launch an async MT5-2 test with a required idempotency operation id."""
        return launch_test(
            ctx=ctx,
            workspace=workspace,
            ea=ea,
            preset=preset,
            set_file=set_file,
            overrides=overrides,
            timeout_seconds=timeout_seconds,
            ea_binary_ref=ea_binary_ref,
            operation_id=operation_id,
        )

    @server.tool()
    def get_job(job_id: str, wait_seconds: float = 0, after_event_seq: int = -1) -> dict[str, Any]:
        """Get job state; optionally wait up to 55s for a newer durable event/terminal state."""
        return facade.get_job(job_id, wait_seconds, after_event_seq)

    @server.tool()
    def cancel_job(ctx: Context, job_id: str) -> dict[str, Any]:
        """Cancel only the exact VibeMQL5 job/PID; never kill all terminal64 processes."""
        return _invoke(ctx, "cancel_job", lambda: facade.cancel_job(job_id))

    @server.tool()
    def read_result(job_id: str) -> dict[str, Any]:
        """Read machine-readable result.json for a completed job."""
        return facade.read_result(job_id)

    @server.tool()
    def read_compile_diagnostics(job_id: str) -> dict[str, Any]:
        """Read structured MetaEditor compiler errors/warnings for a job."""
        return facade.read_compile_diagnostics(job_id)

    @server.tool()
    def read_tester_events(job_id: str) -> dict[str, Any]:
        """Read structured tester events/fatal diagnostics for a job."""
        return facade.read_tester_events(job_id)

    @server.tool()
    def read_artifact(job_id: str, name: str, offset: int = 0, max_bytes: int = 262144) -> dict[str, Any]:
        """Read a job-scoped logical artifact; binary artifacts are returned as bounded base64 chunks."""
        return facade.read_artifact(job_id, name, offset, max_bytes)

    @server.resource("vibemql5-export://artifact/{token}", mime_type="application/octet-stream")
    def file_export_resource(token: str) -> bytes:
        """Read one hash-bound export resource after revalidating scope, size and SHA-256."""
        raw, _meta = facade.read_file_export_resource(token)
        return raw

    @server.tool(
        annotations=ToolAnnotations(
            title="Export VibeMQL5 file",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
    )
    def export_file(
        scope: str,
        source_id: str,
        name: str = "",
        expected_sha256: str = "",
    ) -> CallToolResult:
        """Return a hash-bound MCP ResourceLink from an explicit read-only scope.

        Backward-compatible scopes: job, evidence, exports. TIP-025 scopes: job_source and
        job_parameter_set resolve only immutable build-input snapshots; release_bundle builds
        a deterministic job-bound ZIP; workspace_source and parameter_set are current-workspace
        convenience exports and are never historical job authority. Absolute paths, traversal,
        symlink/junction escape, sensitive-looking filenames, wrong hashes, incomplete artifacts,
        unsupported extensions and files over the configured export limit fail closed.
        """
        meta = facade.prepare_file_export(scope, source_id, name, expected_sha256)
        summary = json.dumps(meta, sort_keys=True, separators=(",", ":"))
        return CallToolResult(
            content=[
                TextContent(type="text", text=summary),
                ResourceLink(
                    type="resource_link",
                    uri=meta["uri"],
                    name=meta["file_name"],
                    title=meta["file_name"],
                    description=f"VibeMQL5 hash-bound export {meta['sha256']}",
                    mime_type=meta["mime_type"],
                    size=meta["bytes"],
                ),
            ],
            structured_content=meta,
        )

    @server.tool()
    def capture_runtime_snapshot(
        ctx: Context,
        job_id: str,
        profile: str = "private",
        label: str = "",
    ) -> dict[str, Any]:
        """Capture a running MT5-2 job launched with an imported EX5 ea_binary_ref (BIN authority).

        Source-compiled jobs are unsupported; PID is server-resolved only.
        """
        return _invoke(ctx, "capture_runtime_snapshot", lambda: facade.capture_runtime_snapshot(job_id, profile, label))

    @server.tool()
    def compare_runtime_snapshots(
        ctx: Context,
        capture_a: str,
        capture_b: str,
        mode: str = "delta",
        known_values: list[float | int] | None = None,
    ) -> dict[str, Any]:
        """Compare immutable runtime captures; never accesses a caller-selected live process."""
        return _invoke(ctx, "compare_runtime_snapshots", lambda: facade.compare_runtime_snapshots(
            capture_a, capture_b, mode, known_values or []
        ))

    @server.tool()
    def compare_baseline(workspace: str, baseline: str, job_id: str) -> dict[str, Any]:
        """Compare job evidence with a named baseline without treating profit as an automatic gate."""
        return facade.compare_baseline(workspace, baseline, job_id)


    # TIP026_BACKEND_ADMIN_BOOTSTRAP_V3
    _backend_admin = register_backend_admin_tools(server, r"C:\VibeMQL5")

    @server.tool(annotations=ToolAnnotations(
        title="Run PowerShell command",
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    ))
    def backend_run_powershell(
        ctx: Context,
        script: str,
        confirm: bool = False,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        """Run unrestricted PowerShell as the Bridge Windows identity; pass confirm=true each time."""
        return _invoke(
            ctx,
            "backend_run_powershell",
            lambda: _backend_admin.run_powershell(script, confirm, timeout_seconds),
        )

    return server


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vibemql5-mcp")
    parser.add_argument("--root", default=str(default_root()))
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="streamable-http")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    server = create_server(Path(args.root), transport=args.transport)
    if args.transport == "streamable-http":
        server.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
