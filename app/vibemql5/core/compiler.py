from __future__ import annotations
import hashlib, json, shutil, subprocess, time
from pathlib import Path
from typing import Callable
from .inventory import TerminalInventory
from .workspace import WorkspaceManager
from ..config import default_root
from ..parsers.compiler_log import parse_compiler_log

class CompilerDriver:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root())
        self.inventory = TerminalInventory(self.root)
        self.workspace = WorkspaceManager(self.root)

    def _deploy(self, workspace: str, source_rel: str, terminal_alias: str, before_effect=None, frozen_inputs=None, after_effect=None) -> tuple[Path, str]:
        t = self.inventory.get(terminal_alias)
        source = self.workspace.resolve(workspace, source_rel, must_exist=frozen_inputs is None)
        ws_root = self.workspace.workspace_root(workspace)
        rel = source.relative_to(ws_root)
        if not rel.parts or rel.parts[0].lower() != "experts":
            raise ValueError("EA source must live under workspace/Experts")
        sub = Path(*rel.parts[1:])
        deploy_root = Path(t.data_root) / "MQL5" / "Experts" / "VibeMQL5" / workspace
        target = deploy_root / sub
        if before_effect: before_effect("deploy_source_prepare")
        target.parent.mkdir(parents=True, exist_ok=True)
        if after_effect: after_effect("deploy_source_prepare")
        if before_effect: before_effect("deploy_source_copy")
        if frozen_inputs is None:
            shutil.copy2(source, target)
        else:
            target.write_bytes(frozen_inputs[rel.as_posix()])
        if after_effect: after_effect("deploy_source_copy")

        inc = ws_root / "Include"
        include_files = ([ws_root / relative for relative in frozen_inputs if relative.startswith("Include/")]
                         if frozen_inputs is not None else [f for f in inc.rglob("*") if f.is_file()] if inc.exists() else [])
        if include_files:
            inc_target = Path(t.data_root) / "MQL5" / "Include" / "VibeMQL5" / workspace
            if before_effect: before_effect("deploy_include_prepare")
            inc_target.mkdir(parents=True, exist_ok=True)
            if after_effect: after_effect("deploy_include_prepare")
            for f in include_files:
                dest = inc_target / f.relative_to(inc)
                if before_effect: before_effect("deploy_include_prepare")
                dest.parent.mkdir(parents=True, exist_ok=True)
                if after_effect: after_effect("deploy_include_prepare")
                if before_effect: before_effect("deploy_include_copy")
                if frozen_inputs is None:
                    shutil.copy2(f, dest)
                else:
                    dest.write_bytes(frozen_inputs[f.relative_to(ws_root).as_posix()])
                if after_effect: after_effect("deploy_include_copy")

        expert_name = str(Path("VibeMQL5") / workspace / sub.with_suffix("")).replace("/", "\\")
        return target, expert_name

    def compile(self, workspace: str, source_rel: str, terminal_alias: str, run_dir: Path,
                timeout: int = 120, mock: bool = False,
                on_pid: Callable[[int], None] | None = None,
                owned_launch=None, before_effect=None, frozen_inputs=None, after_effect=None) -> dict:
        if before_effect: before_effect("compile_run_prepare")
        run_dir.mkdir(parents=True, exist_ok=True)
        if after_effect: after_effect("compile_run_prepare")
        log_path = run_dir / "compile.log"
        json_path = run_dir / "compile.json"
        source = self.workspace.resolve(workspace, source_rel, must_exist=frozen_inputs is None)

        if mock:
            content = source.read_text(encoding="utf-8-sig")
            if "__COMPILE_ERROR__" in content:
                log_path.write_text(f"{source}(1,1) : error 999 : mock compile error\nResult: 1 errors, 0 warnings\n", encoding="utf-8")
                expert_name = f"VibeMQL5\\{workspace}\\{Path(source_rel).stem}"
                deployed = source
            else:
                log_path.write_text("Result: 0 errors, 0 warnings\n", encoding="utf-8")
                expert_name = f"VibeMQL5\\{workspace}\\{Path(source_rel).stem}"
                deployed = source
                (run_dir / (source.stem + ".ex5.mock")).write_text("mock ex5", encoding="utf-8")
            result = parse_compiler_log(log_path)
            result.update({"expert_name": expert_name, "deployed_source": str(deployed), "mock": True})
            json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            return result

        t = self.inventory.get(terminal_alias)
        deployed, expert_name = (self._deploy(workspace, source_rel, terminal_alias, before_effect=before_effect, frozen_inputs=frozen_inputs, after_effect=after_effect)
                                 if before_effect or frozen_inputs is not None else self._deploy(workspace, source_rel, terminal_alias))
        ex5 = deployed.with_suffix(".ex5")
        native_log = deployed.with_suffix(".log")
        if before_effect: before_effect("compile_output_reset")
        native_log.unlink(missing_ok=True)
        if after_effect: after_effect("compile_output_reset")
        if before_effect: before_effect("compile_output_reset")
        ex5.unlink(missing_ok=True)
        if after_effect: after_effect("compile_output_reset")

        cmd = [t.metaeditor_path, f"/compile:{deployed}", "/log"]
        started = time.monotonic()
        if before_effect and owned_launch is None: before_effect("compiler_process_create")
        proc = (owned_launch or subprocess.Popen)(cmd, cwd=str(Path(t.metaeditor_path).parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if after_effect and owned_launch is None: after_effect("compiler_process_create")
        if on_pid:
            on_pid(proc.pid)
        timed_out = False
        try:
            exit_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if before_effect: before_effect("compiler_terminate")
            proc.kill()
            if after_effect: after_effect("compiler_terminate")
            proc.wait(timeout=10)
            exit_code = proc.returncode
            timed_out = True

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not timed_out and not (native_log.exists() or ex5.exists()):
            time.sleep(0.1)
        if native_log.exists():
            if before_effect: before_effect("compile_log_capture")
            shutil.copy2(native_log, log_path)
            if after_effect: after_effect("compile_log_capture")
        elif not log_path.exists():
            log_path.write_text("MetaEditor produced no compilation log.\n", encoding="utf-8")

        result = parse_compiler_log(log_path)
        if timed_out:
            result["status"] = "FAILED"
            result.setdefault("diagnostics", []).append({"file": str(deployed), "line": None, "column": None, "severity": "error", "message": "MetaEditor compile timeout", "code": "TIMEOUT"})
            result["errors"] = max(1, result.get("errors", 0))
        elif not ex5.exists():
            result["status"] = "FAILED"
            result.setdefault("diagnostics", []).append({"file": str(deployed), "line": None, "column": None, "severity": "error", "message": "EX5 output not found after compile", "code": "NO_EX5"})
            result["errors"] = max(1, result.get("errors", 0))
        immutable_ex5 = None
        if result.get("status") == "PASSED" and ex5.is_file() and ex5.stat().st_size > 0:
            captured_ex5 = run_dir / "compiled.ex5"
            if before_effect: before_effect("compile_ex5_capture")
            shutil.copy2(ex5, captured_ex5)
            raw = captured_ex5.read_bytes()
            if after_effect: after_effect("compile_ex5_capture")
            immutable_ex5 = {
                "path": str(captured_ex5),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "source_path": str(ex5),
            }
        result.update({
            "status_basis": {
                "compiler_log_status": result.get("status"),
                "timed_out": timed_out,
                "ex5_exists": ex5.is_file(),
                "ex5_bytes": ex5.stat().st_size if ex5.is_file() else 0,
                "process_exit_code_authoritative": False,
                "decision": (
                    "TIMEOUT" if timed_out else
                    "NO_EX5" if not ex5.exists() else
                    "COMPILER_LOG_AND_EX5"
                ),
            },
            "expert_name": expert_name,
            "deployed_source": str(deployed),
            "ex5_path": str(ex5),
            "immutable_ex5": immutable_ex5,
            "native_log_path": str(native_log),
            "command": cmd,
            "source": "windows_native_metaeditor" if __import__("os").name == "nt" else "native_metaeditor_nonwindows",
            "process_exit_code": exit_code,
            "duration_seconds": round(time.monotonic() - started, 3),
            "mock": False,
        })
        if before_effect: before_effect("compile_result_publish")
        if owned_launch is not None: result["cancelled"] = bool(getattr(owned_launch, "cancelled", False))
        json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        if after_effect: after_effect("compile_result_publish")
        return result
