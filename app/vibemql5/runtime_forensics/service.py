from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import secrets
import subprocess
import sys
from typing import Any

from .authority import AuthorityError, AuthorityRecord, sign_record
from .compare_snapshots import load_pages as load_compare_pages, compare_pages, target_specific
from .scan_known_values import scan as scan_known_values
from ..core.jobs import _command_binds_job, _process_identity, _same_process_identity
from ..core.jobs import _process_identity, _same_process_identity, _command_binds_job

_PROFILES = {"private"}
_LABEL_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_CAPTURE_RE = re.compile(r"^RTC-[A-Za-z0-9-]+$")
_EXPECTED_AGENT = "metatester64.exe"
_TERMINAL_ID = "MT5-2"


def _norm_win(path: str) -> str:
    return str(PureWindowsPath(path)).replace("/", "\\").rstrip("\\").casefold()


def _is_under(path: str, roots: list[str]) -> bool:
    p = _norm_win(path)
    for root in roots:
        r = _norm_win(root)
        if p == r or p.startswith(r + "\\"):
            return True
    return False


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise AuthorityError(f"INVALID_JSON_OBJECT: {path}")
    return raw


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _load_key() -> bytes:
    raw = os.environ.get("VIBEMQL5_RUNTIME_AUTH_KEY_HEX", "").strip()
    if len(raw) != 64 or not re.fullmatch(r"[0-9a-fA-F]{64}", raw):
        raise AuthorityError("AUTHORITY_KEY_MISSING")
    return bytes.fromhex(raw)


def _query_metatester_candidates() -> list[dict[str, Any]]:
    if os.name != "nt":
        raise AuthorityError("WINDOWS_REQUIRED")
    TH32CS_SNAPPROCESS = 0x00000002
    MAX_PATH = 260
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * MAX_PATH),
        ]
    k32=ctypes.WinDLL("kernel32",use_last_error=True)
    k32.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    k32.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    k32.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(PROCESSENTRY32W)]
    k32.Process32FirstW.restype=wintypes.BOOL
    k32.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.restype=wintypes.BOOL
    k32.CloseHandle.argtypes=[wintypes.HANDLE]
    k32.CloseHandle.restype=wintypes.BOOL
    snap=k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0)
    invalid=ctypes.c_void_p(-1).value
    if snap==invalid:
        raise AuthorityError("AGENT_DISCOVERY_FAILED")
    out=[]
    try:
        pe=PROCESSENTRY32W(); pe.dwSize=ctypes.sizeof(PROCESSENTRY32W)
        ok=bool(k32.Process32FirstW(snap,ctypes.byref(pe)))
        while ok:
            if str(pe.szExeFile).casefold()==_EXPECTED_AGENT:
                pid=int(pe.th32ProcessID)
                try:
                    image, creation=_creation_and_image_100ns(pid)
                    out.append({"pid":pid,"image_path":image,"creation_time_100ns":creation})
                except AuthorityError:
                    pass
            ok=bool(k32.Process32NextW(snap,ctypes.byref(pe)))
    finally:
        k32.CloseHandle(snap)
    if out:
        return out
    # R3.7.1 fallback: Toolhelp32 can miss the Strategy Tester agent on this VPS.
    # This fixed query is not caller-controlled and returns candidate PIDs only;
    # path + creation identity are still revalidated with WinAPI below.
    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$x=@(Get-Process -Name metatester64 -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty Id);"
        "$x|ConvertTo-Json -Compress"
    )
    try:
        cp = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=3, check=False,
        )
    except subprocess.TimeoutExpired:
        return []
    raw = cp.stdout.strip() if cp.returncode == 0 else ""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except Exception:
        return []
    pids = value if isinstance(value, list) else [value]
    for item in pids:
        try:
            pid = int(item)
            image, creation = _creation_and_image_100ns(pid)
        except Exception:
            continue
        out.append({"pid": pid, "image_path": image, "creation_time_100ns": creation})
    return out
def _creation_and_image_100ns(pid: int) -> tuple[str, int]:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259

    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.GetExitCodeProcess.restype = wintypes.BOOL
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME)]
    k32.GetProcessTimes.restype = wintypes.BOOL

    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        raise AuthorityError("AGENT_NOT_BOUND")
    try:
        ec = wintypes.DWORD(0)
        if not k32.GetExitCodeProcess(h, ctypes.byref(ec)) or ec.value != STILL_ACTIVE:
            raise AuthorityError("AGENT_NOT_BOUND")
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            raise AuthorityError("AGENT_IMAGE_MISMATCH")
        creation = FILETIME(); exit_ft = FILETIME(); kernel_ft = FILETIME(); user_ft = FILETIME()
        if not k32.GetProcessTimes(h, ctypes.byref(creation), ctypes.byref(exit_ft), ctypes.byref(kernel_ft), ctypes.byref(user_ft)):
            raise AuthorityError("AGENT_CREATION_TIME_MISMATCH")
        creation_100ns = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
        return buf.value, creation_100ns
    finally:
        k32.CloseHandle(h)


class RuntimeForensicsManager:
    """Job-bound runtime capture for the fixed MT5-2 Strategy Tester.

    V1 binding is deliberately fail-closed: an exact running VibeMQL5 job must have
    its persisted terminal identity still bound to the job, and exactly one live
    metatester64.exe candidate must exist under the fixed MT5 agent roots. If more
    than one candidate is present, capture is refused rather than guessing a PID.
    """

    def __init__(self, root: Path, jobs):
        self.root = Path(root)
        self.jobs = jobs
        self.runtime_root = self.root / "evidence" / "runtime"
        self.authority_root = self.root / "runtime-authority"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.authority_root.mkdir(parents=True, exist_ok=True)
        self.helper_path = Path(__file__).with_name("runtime_capture_windows.py").resolve()
        self.helper_sha256 = _sha256_file(self.helper_path)

    def _job(self, job_id: str) -> dict[str, Any]:
        if not str(job_id or "").startswith("BT-"):
            raise AuthorityError("JOB_NOT_FOUND")
        job = self.jobs.get_job(job_id)
        state = str(job.get("state") or "")
        # Production VibeMQL5 uses TESTING while the native Strategy Tester
        # is actively executing. RUNNING is retained for package/reference
        # compatibility, while all identity/binary/agent gates remain mandatory.
        if state not in {"TESTING", "RUNNING"}:
            raise AuthorityError("JOB_NOT_RUNNING")
        return job

    def _verify_terminal_binding(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job.get("job_id") or "")
        terminal = ((job.get("processes") or {}).get("terminal") or {})
        try:
            pid = int(terminal.get("pid") or 0)
        except Exception:
            pid = 0
        expected = terminal.get("identity") if isinstance(terminal.get("identity"), dict) else None

        if pid <= 0 or not expected:
            raise AuthorityError("TERMINAL_BINDING_MISSING")

        expected_image = str(expected.get("executable") or "")
        if PureWindowsPath(expected_image).name.lower() != "terminal64.exe":
            raise AuthorityError("TERMINAL_IMAGE_MISMATCH")

        if not _command_binds_job(expected, job_id, "terminal"):
            raise AuthorityError("TERMINAL_COMMAND_BINDING_MISMATCH")

        current = _process_identity(pid)
        if current:
            if not _same_process_identity(expected, current):
                detail = {
                    "expected": {
                        "pid": expected.get("pid"),
                        "creation_date": expected.get("creation_date"),
                        "executable": expected.get("executable"),
                        "command_line": expected.get("command_line"),
                    },
                    "current": {
                        "pid": current.get("pid"),
                        "creation_date": current.get("creation_date"),
                        "executable": current.get("executable"),
                        "command_line": current.get("command_line"),
                    },
                }
                raise AuthorityError(
                    "TERMINAL_PID_REUSED:" + json.dumps(detail, sort_keys=True, separators=(",", ":"))
                )
            if not _command_binds_job(current, job_id, "terminal"):
                raise AuthorityError("TERMINAL_COMMAND_BINDING_MISMATCH")
            return {**current, "binding_lifecycle": "LIVE_EXACT"}

        return {**expected, "binding_lifecycle": "EXITED_AFTER_EXACT_BIND"}
    def _allowed_roots(self, terminal_identity: dict[str, Any]) -> list[str]:
        roots: list[str] = []
        env_roots = os.environ.get("VIBEMQL5_MT5_AGENT_ROOTS", "")
        for value in env_roots.split(os.pathsep):
            value = value.strip()
            if value:
                roots.append(value)
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            roots.append(str(Path(appdata) / "MetaQuotes" / "Tester"))
        terminal_exe = str(terminal_identity.get("executable") or "").strip()
        if terminal_exe:
            roots.append(str(Path(terminal_exe).parent))
        dedup: list[str] = []
        seen = set()
        for root in roots:
            key = _norm_win(root)
            if key not in seen:
                seen.add(key); dedup.append(root)
        if not dedup:
            raise AuthorityError("AGENT_IMAGE_MISMATCH")
        return dedup

    def _resolve_agent(self, roots: list[str]) -> dict[str, Any]:
        candidates = []
        for row in _query_metatester_candidates():
            image = str(row.get("image_path") or "")
            if PureWindowsPath(image).name.casefold() != _EXPECTED_AGENT:
                continue
            if not _is_under(image, roots):
                continue
            try:
                actual_image, creation_100ns = _creation_and_image_100ns(int(row["pid"]))
            except AuthorityError:
                continue
            if PureWindowsPath(actual_image).name.casefold() != _EXPECTED_AGENT or not _is_under(actual_image, roots):
                continue
            candidates.append({"pid": int(row["pid"]), "image_path": actual_image, "creation_time_100ns": int(creation_100ns)})
        if not candidates:
            raise AuthorityError("AGENT_NOT_BOUND")
        if len(candidates) != 1:
            raise AuthorityError(f"AGENT_NOT_BOUND: expected one bound tester agent, found {len(candidates)}")
        return candidates[0]

    def _binary_identity(self, job_id: str, job: dict[str, Any]) -> tuple[str, str]:
        manifest_path = self.root / "runs" / job_id / "build-input-manifest.json"
        if not manifest_path.is_file():
            raise AuthorityError("BINARY_AUTHORITY_REQUIRED")
        manifest = _load_json(manifest_path)
        imported = dict(manifest.get("imported_ex5") or {})
        ea_ref = str(imported.get("ea_binary_ref") or "")
        ea_sha = str(imported.get("sha256") or "").lower()
        req_ref = str((job.get("request") or {}).get("ea_binary_ref") or "")
        if not ea_ref.startswith("BIN-") or not re.fullmatch(r"[0-9a-f]{64}", ea_sha):
            raise AuthorityError("BINARY_AUTHORITY_REQUIRED")
        if req_ref and req_ref != ea_ref:
            raise AuthorityError("BINARY_AUTHORITY_MISMATCH")
        return ea_ref, ea_sha

    def capture(self, job_id: str, profile: str = "private", label: str = "") -> dict[str, Any]:
        profile = str(profile or "private")
        label = str(label or "")
        attempt_id = "RTCA-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(4).upper()
        attempt_path = self.runtime_root / "attempts" / f"{attempt_id}.json"
        trace: dict[str, Any] = {
            "schema": "1.0",
            "attempt_id": attempt_id,
            "job_id": str(job_id or ""),
            "profile": profile,
            "label": label,
            "status": "RUNNING",
            "stage": "request_validation",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        def persist() -> None:
            try:
                _atomic_json(attempt_path, trace)
            except Exception as persist_exc:
                trace["diagnostic_write_error"] = str(persist_exc)

        def stage(name: str, **extra: Any) -> None:
            trace["stage"] = name
            trace["updated_at"] = datetime.now(timezone.utc).isoformat()
            if extra:
                trace.update(extra)
            persist()

        def error_code(exc: BaseException, fallback: str = "CAPTURE_FAILED") -> str:
            if isinstance(exc, subprocess.TimeoutExpired):
                return "HELPER_TIMEOUT"
            msg = str(exc or "").strip()
            head = msg.split(":", 1)[0].strip()
            if re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", head):
                return head
            return fallback

        def fail(name: str, exc: BaseException | None = None, *, code: str = "", details: dict[str, Any] | None = None) -> dict[str, Any]:
            message = str(exc or "capture failed")
            final_code = str(code or error_code(exc or RuntimeError(message)))
            trace.update({
                "status": "FAILED",
                "complete": False,
                "stage": name,
                "failure_stage": name,
                "error_code": final_code,
                "error": message,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            if details:
                trace["details"] = details
            persist()
            out = {
                "status": "FAILED",
                "complete": False,
                "attempt_id": attempt_id,
                "job_id": str(job_id or ""),
                "profile": profile,
                "label": label,
                "failure_stage": name,
                "error_code": final_code,
                "error": message,
                "diagnostic_path": str(attempt_path),
            }
            if details:
                for key in ("helper_stage", "helper_error_code", "win32_error", "win32_message", "helper_returncode",
                            "probe_stage", "probe_access_mask", "probe_pss_flags", "probe_pss_rc",
                            "probe_target_session", "probe_caller_session", "probe_same_session",
                            "probe_in_job", "probe_duration_ms", "probe_returncode",
                            "probe_stdout", "probe_stderr"):
                    if key in details:
                        out[key] = details[key]
            return out

        def parse_helper_failure(cp: subprocess.CompletedProcess[str]) -> dict[str, Any]:
            combined = []
            if cp.stderr:
                combined.extend(cp.stderr.strip().splitlines())
            if cp.stdout:
                combined.extend(cp.stdout.strip().splitlines())
            for line in reversed(combined):
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except Exception:
                    continue
                if isinstance(value, dict) and value.get("status") == "FAILED":
                    return value
            return {"status": "FAILED", "error": (cp.stderr or cp.stdout or "helper failed").strip()}

        try:
            if profile not in _PROFILES:
                return fail("request_validation", AuthorityError("PROFILE_INVALID"))
            if label and not _LABEL_RE.fullmatch(label):
                return fail("request_validation", AuthorityError("LABEL_INVALID"))

            stage("job_binding")
            job = self._job(job_id)
            start_state = str(job.get("state") or "")
            trace["job_state_at_start"] = start_state

            stage("terminal_binding", job_state_at_start=start_state)
            terminal_identity = self._verify_terminal_binding(job)

            stage("agent_roots")
            roots = self._allowed_roots(terminal_identity)
            trace["allowed_agent_root_count"] = len(roots)

            stage("agent_resolution")
            agent = self._resolve_agent(roots)
            trace["agent_pid"] = int(agent["pid"])
            trace["agent_image_basename"] = PureWindowsPath(str(agent["image_path"])).name
            trace["agent_creation_time_100ns"] = int(agent["creation_time_100ns"])

            stage("binary_identity")
            ea_ref, ea_sha = self._binary_identity(job_id, job)
            trace["ea_binary_ref"] = ea_ref
            trace["ea_sha256"] = ea_sha

            stage("authority_key")
            key = _load_key()
            trace["authority_key_present"] = True

            stage("authority_sign")
            nonce = secrets.token_hex(24)
            expires = datetime.now(timezone.utc) + timedelta(seconds=90)
            authority = sign_record(
                AuthorityRecord(
                    job_id=job_id,
                    terminal_id=_TERMINAL_ID,
                    agent_pid=int(agent["pid"]),
                    agent_creation_time_100ns=int(agent["creation_time_100ns"]),
                    agent_image_path=str(agent["image_path"]),
                    ea_binary_ref=ea_ref,
                    ea_sha256=ea_sha,
                    nonce=nonce,
                    expires_at_utc=expires.isoformat(),
                ),
                key,
            )
            authority_path = self.authority_root / f"{job_id}-{nonce[:12]}.json"
            _atomic_json(authority_path, authority.__dict__)
            trace["authority_file_sha256"] = _sha256_file(authority_path)

            # R3.5 bounded isolated PSS preflight.
            probe_cmd = [
                sys.executable, "-m", "vibemql5.runtime_forensics.pss_probe_windows",
                "--authority", str(authority_path),
                "--out-root", str(self.runtime_root),
            ]
            for root in roots:
                probe_cmd += ["--allowed-agent-root", root]

            stage("pss_preflight")
            try:
                probe_cp = subprocess.run(
                    probe_cmd,
                    cwd=str(self.root),
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                return fail("pss_preflight", exc, code="PSS_PREFLIGHT_TIMEOUT")

            probe_lines = []
            if probe_cp.stdout:
                probe_lines.extend(probe_cp.stdout.strip().splitlines())
            if probe_cp.stderr:
                probe_lines.extend(probe_cp.stderr.strip().splitlines())
            probe = None
            for probe_line in reversed(probe_lines):
                try:
                    candidate = json.loads(probe_line)
                except Exception:
                    continue
                if isinstance(candidate, dict) and candidate.get("status") in {"PASS", "FAILED"}:
                    probe = candidate
                    break
            if probe is None:
                probe_stdout = (probe_cp.stdout or "")[-4096:]
                probe_stderr = (probe_cp.stderr or "")[-4096:]
                trace["pss_preflight_raw"] = {
                    "returncode": int(probe_cp.returncode),
                    "stdout": probe_stdout,
                    "stderr": probe_stderr,
                }
                persist()
                return fail(
                    "pss_preflight",
                    RuntimeError("PSS_PREFLIGHT_RESULT_INVALID"),
                    code="PSS_PREFLIGHT_RESULT_INVALID",
                    details={
                        "probe_returncode": int(probe_cp.returncode),
                        "probe_stdout": probe_stdout,
                        "probe_stderr": probe_stderr,
                    },
                )

            details = {
                "probe_stage": probe.get("stage"),
                "probe_access_mask": probe.get("access_mask"),
                "probe_pss_flags": probe.get("pss_flags"),
                "probe_pss_rc": probe.get("pss_rc"),
                "probe_target_session": probe.get("target_session"),
                "probe_caller_session": probe.get("caller_session"),
                "probe_same_session": probe.get("same_session"),
                "probe_in_job": probe.get("in_job"),
                "probe_duration_ms": probe.get("duration_ms"),
                "probe_returncode": int(probe_cp.returncode),
            }
            for k in ("win32_error", "win32_message"):
                if probe.get(k) is not None:
                    details[k] = probe.get(k)

            trace["pss_preflight"] = probe
            persist()

            if probe.get("status") != "PASS":
                return fail(
                    "pss_preflight/" + str(probe.get("stage") or "unknown"),
                    RuntimeError(str(probe.get("error_code") or "PSS_PREFLIGHT_FAILED")),
                    code=str(probe.get("error_code") or "PSS_PREFLIGHT_FAILED"),
                    details=details,
                )

            # R3.6: successful preflight is now a gate into the bounded
            # private-pages-only helper path. MiniDumpWriteDump remains disabled.
            cmd = [
                sys.executable, "-m", "vibemql5.runtime_forensics.runtime_capture_windows",
                "--authority", str(authority_path),
                "--out-root", str(self.runtime_root),
                "--profile", profile,
            ]
            for root in roots:
                cmd += ["--allowed-agent-root", root]

            stage("helper_invoke", helper_sha256_expected=self.helper_sha256)
            try:
                cp = subprocess.run(cmd, cwd=str(self.root), capture_output=True, text=True, timeout=180, check=False)
            except subprocess.TimeoutExpired as exc:
                return fail("helper_invoke", exc, code="HELPER_TIMEOUT")

            trace["helper_returncode"] = int(cp.returncode)
            if cp.returncode != 0:
                helper = parse_helper_failure(cp)
                helper_stage = str(helper.get("stage") or "helper_unknown")
                helper_code = str(helper.get("error_code") or "CAPTURE_FAILED")
                details = {
                    "helper_stage": helper_stage,
                    "helper_error_code": helper_code,
                    "helper_returncode": int(cp.returncode),
                }
                for key in ("win32_error", "win32_message"):
                    if helper.get(key) is not None:
                        details[key] = helper.get(key)
                return fail("helper/" + helper_stage, RuntimeError(str(helper.get("error") or "helper failed")), code=helper_code, details=details)

            stage("helper_result")
            try:
                result = json.loads(cp.stdout.strip().splitlines()[-1])
            except Exception as exc:
                return fail("helper_result", exc, code="HELPER_RESULT_INVALID")
            if result.get("status") != "COMPLETED" or result.get("complete") is not True:
                return fail("helper_result", RuntimeError(str(result.get("error") or "helper incomplete")), code=str(result.get("error_code") or "CAPTURE_FAILED"))

            capture_id = str(result.get("capture_id") or "")
            if not _CAPTURE_RE.fullmatch(capture_id):
                return fail("manifest_verify", RuntimeError("invalid capture id"), code="CAPTURE_ID_INVALID")

            stage("manifest_verify", capture_id=capture_id)
            capture_dir = self.runtime_root / capture_id
            manifest_path = capture_dir / "capture-manifest.json"
            manifest = _load_json(manifest_path)
            if str(manifest.get("helper_sha256") or "").lower() != self.helper_sha256.lower():
                return fail("manifest_verify", AuthorityError("CAPTURE_HELPER_MISMATCH"))

            stage("post_capture_binding")
            post = self.jobs.get_job(job_id)
            post_state = str(post.get("state") or "")
            if post_state != start_state or post_state not in {"TESTING", "RUNNING"}:
                return fail("post_capture_binding", AuthorityError("POST_CAPTURE_BINDING_MISMATCH"))
            self._verify_terminal_binding(post)

            manifest.update({
                "job_state_at_start": start_state,
                "label": label,
                "binding_method": "serialized-single-agent-v1",
                "allowed_agent_roots": roots,
                "authority_file_sha256": _sha256_file(authority_path),
                "capture_attempt_id": attempt_id,
            })
            _atomic_json(manifest_path, manifest)
            trace.update({
                "status": "COMPLETED",
                "complete": True,
                "stage": "complete",
                "capture_id": capture_id,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            persist()
            return {
                "capture_id": capture_id,
                "attempt_id": attempt_id,
                "job_id": job_id,
                "profile": profile,
                "label": label,
                "status": "COMPLETED",
                "complete": True,
                "job_state_at_start": start_state,
                "binding_method": "serialized-single-agent-v1",
                "agent_pid": manifest.get("agent_pid"),
                "agent_creation_time_100ns": manifest.get("agent_creation_time_100ns"),
                "agent_image_path": manifest.get("agent_image_path"),
                "ea_binary_ref": manifest.get("ea_binary_ref"),
                "ea_sha256": manifest.get("ea_sha256"),
                "helper_sha256": manifest.get("helper_sha256"),
                "capture_mode": manifest.get("capture_mode"),
                "minidump_status": manifest.get("minidump_status"),
                "dump_sha256": manifest.get("dump_sha256"),
                "private_memory_sha256": manifest.get("private_memory_sha256"),
                "private_memory_bytes": manifest.get("private_memory_bytes"),
                "region_count_private": manifest.get("region_count_private"),
                "private_page_count": manifest.get("private_page_count"),
                "manifest_artifact": "capture-manifest.json",
                "dump_artifact": "runtime.dmp" if manifest.get("dump_sha256") else None,
                "regions_artifact": "regions.jsonl",
                "private_memory_artifact": "private-regions.bin",
                "page_hashes_artifact": "page-hashes.jsonl",
                "exportable_artifacts": ["capture-manifest.json", "regions.jsonl", "page-hashes.jsonl"],
                "diagnostic_path": str(attempt_path),
            }
        except Exception as exc:
            return fail(str(trace.get("stage") or "bridge_internal"), exc, code=error_code(exc, "BRIDGE_CAPTURE_EXCEPTION"))

    def _capture_dir(self, capture_id: str) -> tuple[Path, dict[str, Any]]:
        if not _CAPTURE_RE.fullmatch(str(capture_id or "")):
            raise AuthorityError("CAPTURE_NOT_FOUND")
        path = (self.runtime_root / capture_id).resolve()
        try:
            path.relative_to(self.runtime_root.resolve())
        except ValueError as exc:
            raise AuthorityError("CAPTURE_NOT_FOUND") from exc
        manifest_path = path / "capture-manifest.json"
        if not manifest_path.is_file():
            raise AuthorityError("CAPTURE_NOT_FOUND")
        manifest = _load_json(manifest_path)
        if manifest.get("complete") is not True or str(manifest.get("capture_id") or "") != capture_id:
            raise AuthorityError("CAPTURE_NOT_FOUND")
        return path, manifest

    def compare(self, capture_a: str, capture_b: str, mode: str = "delta", known_values: list[float | int] | None = None) -> dict[str, Any]:
        if mode not in {"delta", "target-control"}:
            raise AuthorityError("COMPARE_MODE_INVALID")
        values = list(known_values or [])
        if len(values) > 64:
            raise AuthorityError("KNOWN_VALUES_LIMIT")
        a_dir, a_manifest = self._capture_dir(capture_a)
        b_dir, b_manifest = self._capture_dir(capture_b)
        a_pages = load_compare_pages(a_dir / "page-hashes.jsonl")
        b_pages = load_compare_pages(b_dir / "page-hashes.jsonl")
        if mode == "delta":
            comparison = compare_pages(a_pages, b_pages)
        else:
            pages = target_specific(a_pages, b_pages)
            comparison = {"summary": {"target_specific": len(pages)}, "pages": pages}

        value_result = {"summary": {}, "hits": []}
        if values:
            scan_dir = a_dir if mode == "target-control" else b_dir
            value_result = scan_known_values(
                scan_dir / "private-regions.bin",
                scan_dir / "page-hashes.jsonl",
                [str(v) for v in values],
                200,
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out_name = f"comparison-{stamp}-{mode}.json"
        payload = {
            "schema": "1.0",
            "capture_a": capture_a,
            "capture_b": capture_b,
            "mode": mode,
            "capture_a_job": a_manifest.get("job_id"),
            "capture_b_job": b_manifest.get("job_id"),
            "comparison": comparison,
            "known_values": values,
            "value_scan": value_result,
        }
        out_path = a_dir / out_name
        _atomic_json(out_path, payload)
        return {
            "status": "COMPLETED",
            "capture_a": capture_a,
            "capture_b": capture_b,
            "mode": mode,
            "summary": comparison.get("summary") or {},
            "value_summary": value_result.get("summary") or {},
            "value_hit_count": len(value_result.get("hits") or []),
            "artifact": out_name,
            "export_scope": "runtime_capture",
            "export_source_id": capture_a,
        }
