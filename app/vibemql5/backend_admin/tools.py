from __future__ import annotations
from pathlib import Path
from typing import Any
from .core import BackendAdmin, BackendAdminError

def register_backend_admin_tools(mcp, root: str | Path):
    admin = BackendAdmin(Path(root))

    def expose(name):
        return mcp.tool(name=name)

    @expose("backend_read_file")
    def backend_read_file(path: str, max_bytes: int = 262144) -> dict[str, Any]:
        return admin.read_file(path, max_bytes=max_bytes)

    @expose("backend_get_file_hash")
    def backend_get_file_hash(path: str) -> dict[str, Any]:
        return admin.get_file_hash(path)

    @expose("backend_create_checkpoint")
    def backend_create_checkpoint(paths: list[str], label: str = "") -> dict[str, Any]:
        return admin.create_checkpoint(paths, label)

    @expose("backend_restore_checkpoint")
    def backend_restore_checkpoint(
        checkpoint_id: str,
        expected_current_sha256_by_path: dict[str, str],
        paths: list[str] | None = None,
    ) -> dict[str, Any]:
        return admin.restore_checkpoint(
            checkpoint_id,
            paths,
            expected_current_sha256_by_path,
        )

    @expose("backend_apply_patch")
    def backend_apply_patch(path: str, expected_sha256: str, checkpoint_id: str, patch: str) -> dict[str, Any]:
        return admin.apply_patch(path, expected_sha256, checkpoint_id, patch)

    @expose("backend_write_file")
    def backend_write_file(path: str, content: str, expected_sha256: str, checkpoint_id: str) -> dict[str, Any]:
        return admin.write_file(path, content, expected_sha256, checkpoint_id)

    @expose("backend_import_hotfix")
    def backend_import_hotfix(file: str, expected_sha256: str = "") -> dict[str, Any]:
        # MCP runtime should rewrite file-param to a local mounted path before this call.
        return admin.import_hotfix(file, expected_sha256)

    @expose("backend_apply_hotfix_bundle")
    def backend_apply_hotfix_bundle(bundle_path: str) -> dict[str, Any]:
        return admin.apply_hotfix_bundle(bundle_path)

    @expose("backend_run_tests")
    def backend_run_tests(suite: str) -> dict[str, Any]:
        return admin.run_tests(suite)

    @expose("backend_restart_runtime")
    def backend_restart_runtime(
        components: list[str] = ["http_mcp", "interactive_tunnel"],
        wait_ready_seconds: int = 15
    ) -> dict[str, Any]:
        return admin.schedule_restart(components, wait_ready_seconds)

    @expose("backend_read_evidence")
    def backend_read_evidence(relative_path: str, max_bytes: int = 262144) -> dict[str, Any]:
        return admin.read_evidence(relative_path, max_bytes)

    @expose("tunnel_admin_status")
    def tunnel_admin_status(instance: str = "all") -> dict[str, Any]:
        return admin.tunnel_admin_status(instance)

    @expose("tunnel_admin_install_autostart")
    def tunnel_admin_install_autostart(instance: str = "B") -> dict[str, Any]:
        return admin.tunnel_admin_install_autostart(instance)

    @expose("tunnel_admin_start")
    def tunnel_admin_start(instance: str) -> dict[str, Any]:
        return admin.tunnel_admin_start(instance)

    @expose("tunnel_admin_stop")
    def tunnel_admin_stop(instance: str, confirm: bool = False) -> dict[str, Any]:
        return admin.tunnel_admin_stop(instance, confirm)

    @expose("tunnel_admin_restart")
    def tunnel_admin_restart(instance: str, confirm: bool = False) -> dict[str, Any]:
        return admin.tunnel_admin_restart(instance, confirm)

    return admin
