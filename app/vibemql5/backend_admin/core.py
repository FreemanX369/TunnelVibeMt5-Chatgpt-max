from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable

from .models import FileMeta, Receipt, new_id, sha256_file, write_json_atomic

class BackendAdminError(RuntimeError):
    pass

class BackendAdmin:
    ALLOWED_EXTENSIONS = {
        ".py", ".ps1", ".psm1", ".json", ".md", ".txt", ".toml", ".yaml", ".yml",
        ".diff", ".patch", ".ini", ".cfg", ".xml", ".html"
    }
    HOTFIX_EXTENSIONS = {".zip", ".json", ".patch", ".diff", ".py", ".ps1"}
    MAX_FILE_BYTES = 16 * 1024 * 1024
    MAX_HOTFIX_BYTES = 16 * 1024 * 1024

    TEST_SUITES = {
        "py_compile",
        "unit",
        "runtime_forensics",
        "tip026",
        "baseline_aware",
    }

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.allowed_roots = [
            self.root / "app" / "vibemql5",
            self.root / "tests",
            self.root / "scripts",
            self.root / "ops" / "windows",
            self.root / "evidence" / "runtime",
            self.root / "config" / "build-provenance.json",
        ]
        self.mutable_roots = [
            self.root / "app" / "vibemql5",
            self.root / "tests",
            self.root / "scripts",
            self.root / "ops" / "windows",
            self.root / "config" / "build-provenance.json",
        ]
        self.backup_root = self.root / "backups" / "backend-admin"
        self.inbox_root = self.root / "maintenance" / "inbox"
        self.receipt_root = self.root / "evidence" / "runtime" / "backend-admin"
        self.python = self.root / ".venv" / "Scripts" / "python.exe"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.inbox_root.mkdir(parents=True, exist_ok=True)
        self.receipt_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _casefold_path(path: Path) -> str:
        return os.path.normcase(str(path.resolve()))

    def _under(self, path: Path, roots: Iterable[Path]) -> bool:
        rp = self._casefold_path(path)
        for root in roots:
            rr = self._casefold_path(root)
            if rp == rr or rp.startswith(rr + os.sep):
                return True
        return False

    def _reject_unsafe_string(self, raw: str) -> None:
        if not raw or "\x00" in raw:
            raise BackendAdminError("INVALID_PATH")
        if raw.startswith("\\\\") or raw.startswith("\\\\?\\"):
            raise BackendAdminError("UNC_OR_DEVICE_PATH_FORBIDDEN")
        if ":" in raw[2:]:
            raise BackendAdminError("NTFS_ADS_FORBIDDEN")
        parts = PureWindowsPath(raw).parts
        if ".." in parts:
            raise BackendAdminError("PATH_TRAVERSAL_FORBIDDEN")

    def resolve_allowed(self, raw: str, *, mutable: bool = False, must_exist: bool = False) -> Path:
        self._reject_unsafe_string(raw)
        p = Path(raw)
        if not p.is_absolute():
            p = self.root / p
        # strict=False permits new files while still normalizing traversal.
        p = p.resolve(strict=False)
        roots = self.mutable_roots if mutable else self.allowed_roots
        if not self._under(p, roots):
            raise BackendAdminError("PATH_OUTSIDE_ALLOWLIST")
        # Parent symlink/junction escapes are caught by resolved path comparison.
        if must_exist and not p.exists():
            raise BackendAdminError("FILE_NOT_FOUND")
        if p.exists() and p.is_dir():
            raise BackendAdminError("DIRECTORY_NOT_ALLOWED")
        if p.suffix.lower() not in self.ALLOWED_EXTENSIONS:
            raise BackendAdminError("FILE_EXTENSION_NOT_ALLOWED")
        return p

    def _receipt(self, operation: str, status: str, payload: dict[str, Any]) -> dict[str, Any]:
        op = new_id("BADMIN")
        rec = Receipt(op, operation, status, payload)
        path = self.receipt_root / f"{op}.json"
        write_json_atomic(path, rec.as_dict())
        out = rec.as_dict()
        out["receipt_path"] = str(path)
        return out

    def read_file(self, path: str, max_bytes: int = 262144) -> dict[str, Any]:
        p = self.resolve_allowed(path, must_exist=True)
        size = p.stat().st_size
        if size > min(max_bytes, self.MAX_FILE_BYTES):
            raise BackendAdminError("FILE_TOO_LARGE")
        data = p.read_bytes()
        try:
            text = data.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = data.decode("utf-8-sig")
            encoding = "utf-8-sig"
        return {
            "status": "PASS",
            "path": str(p),
            "bytes": len(data),
            "sha256": sha256_file(p),
            "encoding": encoding,
            "content": text,
        }

    def get_file_hash(self, path: str) -> dict[str, Any]:
        p = self.resolve_allowed(path, must_exist=True)
        m = FileMeta.from_path(p)
        return {"status": "PASS", **m.__dict__}

    def create_checkpoint(self, paths: list[str], label: str = "") -> dict[str, Any]:
        if not paths:
            raise BackendAdminError("CHECKPOINT_PATHS_REQUIRED")
        cid = new_id("BADMCP")
        dst = self.backup_root / cid
        files = []
        dst.mkdir(parents=True, exist_ok=False)
        for raw in paths:
            src = self.resolve_allowed(raw, must_exist=True)
            rel = src.relative_to(self.root)
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
            files.append({
                "path": str(src),
                "relative_path": str(rel).replace("\\", "/"),
                "sha256": sha256_file(src),
                "bytes": src.stat().st_size,
            })
        manifest = {
            "schema_version": "1.0",
            "checkpoint_id": cid,
            "label": label,
            "root": str(self.root),
            "files": files,
        }
        write_json_atomic(dst / "manifest.json", manifest)
        return self._receipt("backend_create_checkpoint", "PASS", manifest)

    def _load_checkpoint(self, checkpoint_id: str) -> tuple[Path, dict[str, Any]]:
        if not re.fullmatch(r"BADMCP-[A-Za-z0-9-]+", checkpoint_id):
            raise BackendAdminError("INVALID_CHECKPOINT_ID")
        d = (self.backup_root / checkpoint_id).resolve()
        if not self._under(d, [self.backup_root]) or not d.is_dir():
            raise BackendAdminError("CHECKPOINT_NOT_FOUND")
        mf = d / "manifest.json"
        if not mf.is_file():
            raise BackendAdminError("CHECKPOINT_MANIFEST_MISSING")
        return d, json.loads(mf.read_text(encoding="utf-8"))

    def restore_checkpoint(self, checkpoint_id: str, paths: list[str] | None = None) -> dict[str, Any]:
        d, manifest = self._load_checkpoint(checkpoint_id)
        wanted = None
        if paths:
            wanted = {str(self.resolve_allowed(x, mutable=True, must_exist=False)) for x in paths}
        restored = []
        for entry in manifest["files"]:
            target = self.resolve_allowed(entry["path"], mutable=True, must_exist=False)
            if wanted is not None and str(target) not in wanted:
                continue
            src = d / entry["relative_path"]
            if not src.is_file() or sha256_file(src) != entry["sha256"]:
                raise BackendAdminError("CHECKPOINT_FILE_INTEGRITY_FAILED")
            self._atomic_copy(src, target)
            restored.append({
                "path": str(target),
                "sha256": sha256_file(target),
                "bytes": target.stat().st_size,
            })
        return self._receipt("backend_restore_checkpoint", "PASS", {
            "checkpoint_id": checkpoint_id,
            "restored": restored,
        })

    def _checkpoint_has(self, checkpoint_id: str, target: Path) -> bool:
        _, manifest = self._load_checkpoint(checkpoint_id)
        t = str(target)
        return any(str(self.resolve_allowed(x["path"], must_exist=False)) == t for x in manifest["files"])

    def _require_cas(self, target: Path, expected_sha256: str, checkpoint_id: str) -> str:
        if not target.exists():
            if expected_sha256:
                raise BackendAdminError("EXPECTED_HASH_FOR_MISSING_FILE")
            return ""
        current = sha256_file(target)
        if not expected_sha256 or current.lower() != expected_sha256.lower():
            raise BackendAdminError(f"CAS_MISMATCH:{current}")
        if not checkpoint_id or not self._checkpoint_has(checkpoint_id, target):
            raise BackendAdminError("CHECKPOINT_DOES_NOT_COVER_FILE")
        return current

    def _atomic_bytes(self, target: Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=target.name+".", suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _atomic_copy(self, src: Path, target: Path) -> None:
        self._atomic_bytes(target, src.read_bytes())

    def write_file(self, path: str, content: str, expected_sha256: str, checkpoint_id: str) -> dict[str, Any]:
        target = self.resolve_allowed(path, mutable=True, must_exist=False)
        before = self._require_cas(target, expected_sha256, checkpoint_id)
        data = content.encode("utf-8")
        if len(data) > self.MAX_FILE_BYTES:
            raise BackendAdminError("FILE_TOO_LARGE")
        self._atomic_bytes(target, data)
        return self._receipt("backend_write_file", "PASS", {
            "path": str(target),
            "checkpoint_id": checkpoint_id,
            "sha256_before": before,
            "sha256_after": sha256_file(target),
            "bytes_after": target.stat().st_size,
        })

    def apply_patch(self, path: str, expected_sha256: str, checkpoint_id: str, patch: str) -> dict[str, Any]:
        target = self.resolve_allowed(path, mutable=True, must_exist=True)
        before = self._require_cas(target, expected_sha256, checkpoint_id)
        old = target.read_text(encoding="utf-8")
        new = self._apply_unified_patch_single_file(old, patch)
        self._atomic_bytes(target, new.encode("utf-8"))
        return self._receipt("backend_apply_patch", "PASS", {
            "path": str(target),
            "checkpoint_id": checkpoint_id,
            "sha256_before": before,
            "sha256_after": sha256_file(target),
            "bytes_after": target.stat().st_size,
        })

    @staticmethod
    def _apply_unified_patch_single_file(original: str, patch: str) -> str:
        # Minimal deterministic unified-diff applicator; exact context required.
        src = original.splitlines(keepends=True)
        lines = patch.splitlines(keepends=True)
        hunks = []
        i = 0
        hdr = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
        while i < len(lines):
            m = hdr.match(lines[i])
            if not m:
                i += 1
                continue
            old_start = int(m.group(1))
            body = []
            i += 1
            while i < len(lines) and not lines[i].startswith("@@ "):
                if lines[i].startswith(("--- ", "+++ ")):
                    break
                body.append(lines[i])
                i += 1
            hunks.append((old_start, body))
        if not hunks:
            raise BackendAdminError("PATCH_HAS_NO_HUNKS")
        out = []
        src_idx = 0
        for old_start, body in hunks:
            target_idx = old_start - 1
            if target_idx < src_idx or target_idx > len(src):
                raise BackendAdminError("PATCH_HUNK_RANGE_INVALID")
            out.extend(src[src_idx:target_idx])
            src_idx = target_idx
            for line in body:
                if not line:
                    continue
                tag = line[0]
                payload = line[1:]
                if tag == " ":
                    if src_idx >= len(src) or src[src_idx] != payload:
                        raise BackendAdminError("PATCH_CONTEXT_MISMATCH")
                    out.append(src[src_idx]); src_idx += 1
                elif tag == "-":
                    if src_idx >= len(src) or src[src_idx] != payload:
                        raise BackendAdminError("PATCH_DELETE_MISMATCH")
                    src_idx += 1
                elif tag == "+":
                    out.append(payload)
                elif tag == "\\":
                    continue
                else:
                    raise BackendAdminError("PATCH_FORMAT_INVALID")
        out.extend(src[src_idx:])
        return "".join(out)

    def import_hotfix(self, uploaded_path: str, expected_sha256: str) -> dict[str, Any]:
        src = Path(uploaded_path)
        if not src.is_file():
            raise BackendAdminError("HOTFIX_FILE_NOT_FOUND")
        if src.suffix.lower() not in self.HOTFIX_EXTENSIONS:
            raise BackendAdminError("HOTFIX_EXTENSION_NOT_ALLOWED")
        if src.stat().st_size > self.MAX_HOTFIX_BYTES:
            raise BackendAdminError("HOTFIX_TOO_LARGE")
        actual = sha256_file(src)
        if expected_sha256 and actual.lower() != expected_sha256.lower():
            raise BackendAdminError("HOTFIX_SHA256_MISMATCH")
        ref = f"HOTFIX-{actual[:24]}"
        dst_dir = self.inbox_root / actual
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        if dst.exists() and sha256_file(dst) != actual:
            raise BackendAdminError("HOTFIX_OBJECT_COLLISION")
        if not dst.exists():
            shutil.copy2(src, dst)
        return self._receipt("backend_import_hotfix", "PASS", {
            "bundle_ref": ref,
            "path": str(dst),
            "sha256": actual,
            "bytes": dst.stat().st_size,
        })

    def _safe_zip_members(self, z: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
        infos = z.infolist()
        total = 0
        for info in infos:
            name = info.filename.replace("\\", "/")
            pp = Path(name)
            if name.startswith("/") or ".." in pp.parts or ":" in name:
                raise BackendAdminError("HOTFIX_ZIP_TRAVERSAL")
            if info.is_dir():
                continue
            # Unix symlink type.
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise BackendAdminError("HOTFIX_ZIP_SYMLINK_FORBIDDEN")
            total += info.file_size
            if total > self.MAX_HOTFIX_BYTES:
                raise BackendAdminError("HOTFIX_ZIP_EXPANDED_TOO_LARGE")
        return infos

    def apply_hotfix_bundle(self, bundle_path: str) -> dict[str, Any]:
        bundle = Path(bundle_path)
        if not bundle.is_file() or bundle.suffix.lower() != ".zip":
            raise BackendAdminError("HOTFIX_ZIP_REQUIRED")
        with zipfile.ZipFile(bundle, "r") as z:
            self._safe_zip_members(z)
            try:
                manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            except KeyError:
                raise BackendAdminError("HOTFIX_MANIFEST_MISSING")
            if manifest.get("schema_version") != "1.0":
                raise BackendAdminError("HOTFIX_MANIFEST_SCHEMA_UNSUPPORTED")
            mutations = manifest.get("mutations") or []
            if not mutations:
                raise BackendAdminError("HOTFIX_MUTATIONS_REQUIRED")
            paths = [m["path"] for m in mutations]
            cp = self.create_checkpoint(paths, label=manifest.get("name","hotfix"))
            cid = cp["payload"]["checkpoint_id"]
            applied = []
            try:
                for m in mutations:
                    action = m.get("action")
                    path = m["path"]
                    expected = m.get("expected_sha256","")
                    if action == "write":
                        member = m["member"]
                        data = z.read(member).decode("utf-8")
                        applied.append(self.write_file(path, data, expected, cid))
                    elif action == "patch":
                        member = m["member"]
                        diff = z.read(member).decode("utf-8")
                        applied.append(self.apply_patch(path, expected, cid, diff))
                    else:
                        raise BackendAdminError("HOTFIX_ACTION_NOT_ALLOWED")
                tests = []
                for suite in manifest.get("tests", []):
                    tests.append(self.run_tests(suite))
                    if tests[-1]["status"] != "PASS":
                        raise BackendAdminError(f"HOTFIX_TEST_FAILED:{suite}")
                return self._receipt("backend_apply_hotfix_bundle", "PASS", {
                    "checkpoint_id": cid,
                    "bundle_sha256": sha256_file(bundle),
                    "applied_count": len(applied),
                    "tests": tests,
                })
            except Exception:
                self.restore_checkpoint(cid)
                raise

    def _run(self, argv: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv, cwd=str(self.root), capture_output=True, text=True,
            timeout=timeout, check=False
        )

    def run_tests(self, suite: str) -> dict[str, Any]:
        if suite not in self.TEST_SUITES:
            raise BackendAdminError("TEST_SUITE_NOT_ALLOWED")
        py = str(self.python)
        if suite == "py_compile":
            targets = [str(p) for p in (self.root/"app"/"vibemql5").rglob("*.py")]
            cp = self._run([py, "-m", "py_compile", *targets], timeout=180)
        elif suite == "unit":
            cp = self._run([py, "-m", "pytest", "-q", str(self.root/"tests"/"unit")], timeout=300)
        elif suite == "runtime_forensics":
            cp = self._run([py, "-m", "pytest", "-q", "-k", "runtime_forensics", str(self.root/"tests")], timeout=300)
        elif suite == "tip026":
            cp = self._run([py, "-m", "pytest", "-q", "-k", "tip026", str(self.root/"tests")], timeout=300)
        else:
            # Standalone baseline-aware gate uses an on-disk approved baseline list.
            baseline = self.receipt_root / "approved-unit-failures.json"
            baseline_state = "PRESENT" if baseline.is_file() else "MISSING"
            expected = set(json.loads(baseline.read_text(encoding="utf-8"))) if baseline.is_file() else set()
            xml = self.receipt_root / f"pytest-{new_id('RUN')}.xml"
            cp = self._run([py, "-m", "pytest", "-q", str(self.root/"tests"/"unit"), f"--junitxml={xml}"], timeout=300)
            current = self._failure_ids(xml)
            new = sorted(current - expected)
            return {
                "status": "PASS" if not new else "FAIL",
                "suite": suite,
                "returncode": cp.returncode,
                "baseline_failures": len(expected),
                "current_failures": len(current),
                "new_failures": new,
                "stdout_tail": cp.stdout[-4096:],
                "stderr_tail": cp.stderr[-4096:],
            }
        return {
            "status": "PASS" if cp.returncode == 0 else "FAIL",
            "suite": suite,
            "returncode": cp.returncode,
            "stdout_tail": cp.stdout[-4096:],
            "stderr_tail": cp.stderr[-4096:],
        }

    @staticmethod
    def _failure_ids(xml_path: Path) -> set[str]:
        import xml.etree.ElementTree as ET
        root = ET.parse(xml_path).getroot()
        out = set()
        for tc in root.iter("testcase"):
            if tc.find("failure") is not None or tc.find("error") is not None:
                out.add(f"{tc.get('classname','')}::{tc.get('name','')}")
        return out

    def read_evidence(self, relative_path: str, max_bytes: int = 262144) -> dict[str, Any]:
        if relative_path.startswith("\\") or ".." in Path(relative_path).parts:
            raise BackendAdminError("EVIDENCE_PATH_INVALID")
        p = (self.root / "evidence" / "runtime" / relative_path).resolve(strict=False)
        if not self._under(p, [self.root/"evidence"/"runtime"]) or not p.is_file():
            raise BackendAdminError("EVIDENCE_NOT_FOUND")
        if p.stat().st_size > max_bytes:
            raise BackendAdminError("EVIDENCE_TOO_LARGE")
        raw = p.read_bytes()
        return {
            "status": "PASS",
            "path": str(p),
            "bytes": len(raw),
            "sha256": sha256_file(p),
            "content": raw.decode("utf-8", errors="replace"),
        }

    def schedule_restart(self, components: list[str], wait_ready_seconds: int = 15) -> dict[str, Any]:
        allowed = {"http_mcp", "interactive_tunnel"}
        if not components or any(x not in allowed for x in components):
            raise BackendAdminError("RESTART_COMPONENT_NOT_ALLOWED")
        controller = self.root / "scripts" / "backend-admin-restart.ps1"
        if not controller.is_file():
            raise BackendAdminError("RESTART_CONTROLLER_MISSING")
        rid = new_id("BRESTART")
        receipt = self.receipt_root / f"{rid}.json"
        args = [
            "powershell.exe", "-NoProfile", "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass", "-File", str(controller),
            "-Root", str(self.root),
            "-ReceiptPath", str(receipt),
            "-Components", ",".join(components),
            "-WaitReadySeconds", str(max(5, min(wait_ready_seconds, 60))),
        ]
        stdout_path = self.receipt_root / f"{rid}.stdout.log"
        stderr_path = self.receipt_root / f"{rid}.stderr.log"

        def spawn_with_flags(flags: int) -> subprocess.Popen:
            out = stdout_path.open("ab", buffering=0)
            err = stderr_path.open("ab", buffering=0)
            try:
                return subprocess.Popen(
                    args,
                    cwd=str(self.root),
                    close_fds=True,
                    creationflags=flags,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                )
            finally:
                out.close()
                err.close()

        # Windows:
        # CREATE_BREAKAWAY_FROM_JOB | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        # Breakaway prevents the restart controller from being killed with the
        # MCP process tree it is responsible for restarting.
        if os.name == "nt":
            preferred_flags = 0x01000000 | 0x00000200 | 0x08000000
            fallback_flags = 0x00000200 | 0x08000000
        else:
            preferred_flags = 0
            fallback_flags = 0

        launcher_mode = "BREAKAWAY"
        launch_error = ""
        try:
            proc = spawn_with_flags(preferred_flags)
        except OSError as exc:
            launch_error = f"{type(exc).__name__}:{exc}"
            launcher_mode = "FALLBACK_NO_BREAKAWAY"
            proc = spawn_with_flags(fallback_flags)

        return self._receipt("backend_restart_runtime", "RESTART_SCHEDULED", {
            "restart_id": rid,
            "components": components,
            "restart_receipt": str(receipt),
            "controller_pid": proc.pid,
            "launcher_mode": launcher_mode,
            "preferred_launch_error": launch_error,
            "controller_stdout": str(stdout_path),
            "controller_stderr": str(stderr_path),
            "terminal_touched": False,
        })
