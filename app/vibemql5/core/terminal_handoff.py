from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from .mt5_preflight import MT5Preflight, public_preflight
from ..models.types import TerminalInfo

WM_CLOSE = 0x0010


def _norm(path: str) -> str:
    return str(path).replace('/', '\\').rstrip('\\').lower()


def running_pids_for_executable(executable: str) -> list[int]:
    """Return PIDs whose executable path exactly matches the requested MT5 binary."""
    if os.name != 'nt':
        return []
    script = (
        "$x = Get-CimInstance Win32_Process -Filter \"Name='terminal64.exe'\" | "
        "Where-Object { $_.ExecutablePath -and $_.ExecutablePath -ieq '" + executable.replace("'", "''") + "' } | "
        "Select-Object -ExpandProperty ProcessId; @($x) | ConvertTo-Json -Compress"
    )
    cp = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    raw = cp.stdout.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, int):
        return [int(data)]
    if isinstance(data, list):
        return sorted({int(x) for x in data})
    return []


def _pid_executable(pid: int) -> str | None:
    """Resolve one PID to its executable path so force-kill cannot hit a recycled PID."""
    if os.name != 'nt':
        return None
    script = (
        f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\" -ErrorAction SilentlyContinue; "
        "if ($p -and $p.ExecutablePath) { [Console]::Out.Write($p.ExecutablePath) }"
    )
    cp = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    value = cp.stdout.strip()
    return value or None


def _pid_matches_executable(pid: int, executable: str) -> bool:
    actual = _pid_executable(pid)
    return bool(actual and _norm(actual) == _norm(executable))


def _post_wm_close(pid: int) -> int:
    if os.name != 'nt':
        return 0
    user32 = ctypes.windll.user32
    sent = ctypes.c_int(0)
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @WNDENUMPROC
    def callback(hwnd, _lparam):
        proc_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
        if int(proc_id.value) == int(pid):
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            sent.value += 1
        return True

    user32.EnumWindows(callback, 0)
    return int(sent.value)


def _taskkill_exact(pid: int, executable: str, *, force: bool) -> dict:
    """Kill only if PID still belongs to the exact MT5 installation we own."""
    if os.name != 'nt':
        return {'pid': int(pid), 'attempted': False, 'force': force, 'reason': 'NON_WINDOWS'}
    if not _pid_matches_executable(pid, executable):
        return {'pid': int(pid), 'attempted': False, 'force': force, 'reason': 'PID_PATH_MISMATCH_OR_EXITED'}
    args = ['taskkill', '/PID', str(int(pid)), '/T']
    if force:
        args.append('/F')
    cp = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
    return {
        'pid': int(pid),
        'attempted': True,
        'force': force,
        'exit_code': int(cp.returncode),
        'stdout': (cp.stdout or '').strip()[-500:],
        'stderr': (cp.stderr or '').strip()[-500:],
    }


def _wait_for_quiet(executable: str, deadline: float, quiet_seconds: float = 1.0,
                    on_new_pid=None) -> tuple[bool, set[int]]:
    """Require the exact terminal path to remain absent for a short settle window."""
    observed: set[int] = set()
    quiet_since: float | None = None
    while time.time() < deadline:
        current = set(running_pids_for_executable(executable))
        new = current - observed
        if new and on_new_pid is not None:
            on_new_pid(sorted(new))
        observed.update(current)
        if not current:
            quiet_since = quiet_since or time.time()
            if time.time() - quiet_since >= quiet_seconds:
                return True, observed
        else:
            quiet_since = None
        time.sleep(0.25)
    return False, observed


def close_terminal_gracefully(terminal_path: str, timeout: int = 20) -> dict:
    """Close one exact MT5 installation with bounded, path-verified escalation.

    RC5.2 only attempted WM_CLOSE and non-force taskkill. In unattended/tunnel sessions
    an MT5 GUI can ignore WM_CLOSE (different desktop, modal dialog, or hung UI), which
    caused MT5_HANDOFF_CLOSE_FAILED before native tester startup. This implementation:
      1) asks every exact-path PID to close via WM_CLOSE;
      2) handles immediate respawn/replacement PIDs;
      3) tries non-force taskkill;
      4) uses exact-path-verified /F only as the final bounded fallback;
      5) requires a one-second quiescent window before handing the installation to tester.
    """
    started = time.time()
    initial = running_pids_for_executable(terminal_path)
    if not initial:
        return {
            'was_running': False,
            'closed_pids': [],
            'observed_pids': [],
            'respawned_pids': [],
            'wm_close_messages': 0,
            'taskkill_used': False,
            'force_kill_used': False,
            'close_elapsed_seconds': 0.0,
        }

    observed: set[int] = set(initial)
    respawned: set[int] = set()
    wm_sent_to: set[int] = set()
    messages = 0
    nonforce_results: list[dict] = []
    force_results: list[dict] = []

    def request_graceful(pids: list[int]) -> None:
        nonlocal messages
        for pid in pids:
            if pid not in observed:
                respawned.add(pid)
            observed.add(pid)
            if pid in wm_sent_to:
                continue
            wm_sent_to.add(pid)
            try:
                messages += _post_wm_close(pid)
            except Exception:
                pass

    request_graceful(initial)
    ok, seen = _wait_for_quiet(
        terminal_path,
        time.time() + max(1, int(timeout)),
        quiet_seconds=1.0,
        on_new_pid=request_graceful,
    )
    respawned.update(seen - set(initial))
    observed.update(seen)
    if ok:
        return {
            'was_running': True,
            'closed_pids': sorted(observed),
            'observed_pids': sorted(observed),
            'respawned_pids': sorted(respawned),
            'wm_close_messages': messages,
            'taskkill_used': False,
            'force_kill_used': False,
            'close_elapsed_seconds': round(time.time() - started, 3),
        }

    current = running_pids_for_executable(terminal_path)
    for pid in current:
        nonforce_results.append(_taskkill_exact(pid, terminal_path, force=False))
    ok, seen = _wait_for_quiet(
        terminal_path,
        time.time() + 5,
        quiet_seconds=1.0,
        on_new_pid=request_graceful,
    )
    respawned.update(seen - set(initial))
    observed.update(seen)
    if ok:
        return {
            'was_running': True,
            'closed_pids': sorted(observed),
            'observed_pids': sorted(observed),
            'respawned_pids': sorted(respawned),
            'wm_close_messages': messages,
            'taskkill_used': bool(nonforce_results),
            'force_kill_used': False,
            'taskkill_results': nonforce_results,
            'close_elapsed_seconds': round(time.time() - started, 3),
        }

    force_attempted: set[int] = set()
    force_deadline = time.time() + 8
    quiet_since: float | None = None
    while time.time() < force_deadline:
        current = set(running_pids_for_executable(terminal_path))
        observed.update(current)
        respawned.update(current - set(initial))
        for pid in sorted(current - force_attempted):
            force_attempted.add(pid)
            force_results.append(_taskkill_exact(pid, terminal_path, force=True))
        if not current:
            quiet_since = quiet_since or time.time()
            if time.time() - quiet_since >= 1.0:
                return {
                    'was_running': True,
                    'closed_pids': sorted(observed),
                    'observed_pids': sorted(observed),
                    'respawned_pids': sorted(respawned),
                    'wm_close_messages': messages,
                    'taskkill_used': bool(nonforce_results),
                    'force_kill_used': bool(force_results),
                    'taskkill_results': nonforce_results,
                    'force_kill_results': force_results,
                    'close_elapsed_seconds': round(time.time() - started, 3),
                }
        else:
            quiet_since = None
        time.sleep(0.25)

    remaining = running_pids_for_executable(terminal_path)
    summary = {
        'initial_pids': initial,
        'observed_pids': sorted(observed),
        'respawned_pids': sorted(respawned),
        'remaining_pids': remaining,
        'wm_close_messages': messages,
        'nonforce_attempts': len(nonforce_results),
        'force_attempts': len(force_results),
    }
    raise RuntimeError(
        'MT5_HANDOFF_CLOSE_FAILED: could not obtain exclusive access to '
        f'{terminal_path}; diagnostics={json.dumps(summary, separators=(",", ":"))}'
    )


def restart_normal_terminal(terminal: TerminalInfo, login: int, symbol: str,
                            timeout: int = 60) -> dict:
    install_dir = str(Path(terminal.terminal_path).parent)
    proc = subprocess.Popen(
        [terminal.terminal_path, f'/login:{int(login)}'],
        cwd=install_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + max(10, timeout)
    last = None
    while time.time() < deadline:
        time.sleep(1.0)
        last = MT5Preflight(terminal.terminal_path).probe(symbol, timeout_ms=8000)
        if last.get('ok') and int(last.get('_login') or 0) == int(login):
            return {
                'restart_pid': proc.pid,
                'reconnected': True,
                'preflight': public_preflight(last),
            }
    return {
        'restart_pid': proc.pid,
        'reconnected': False,
        'preflight': public_preflight(last),
    }


@contextmanager
def exclusive_live_terminal_handoff(terminal: TerminalInfo, login: int, symbol: str,
                                    close_timeout: int = 20, reconnect_timeout: int = 60):
    """Temporarily hand the exact live MT5 installation to Strategy Tester.

    The caller must start the tester from the same installation while inside this context.
    On exit, the normal trading terminal is relaunched with the same saved account login.
    No credentials or Config folders are copied between installations.
    """
    meta = {
        'mode': 'EXCLUSIVE_MT5_2_HANDOFF',
        'terminal': terminal.alias,
        'terminal_path': terminal.terminal_path,
        'login': int(login),
        'restore_attempted': False,
        'reconnected': False,
    }
    closed = close_terminal_gracefully(terminal.terminal_path, close_timeout)
    meta.update(closed)
    try:
        yield meta
    finally:
        if meta.get('was_running'):
            meta['restore_attempted'] = True
            restored = restart_normal_terminal(terminal, login, symbol, reconnect_timeout)
            meta.update(restored)
        else:
            meta['restore_attempted'] = False
            meta['restore_skipped_reason'] = 'PRE_HANDOFF_TERMINAL_WAS_STOPPED'
            meta['reconnected'] = False
