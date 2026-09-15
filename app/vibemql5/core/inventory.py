from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from ..config import load_json, default_root
from ..models.types import TerminalInfo
from ..errors import TerminalNotFound, VibeMQL5Error


class TerminalBusy(VibeMQL5Error):
    pass


class TerminalInventory:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or default_root())
        raw = load_json(self.root / "config" / "terminals.json")
        self._items = {x["alias"].upper(): TerminalInfo.from_dict(x) for x in raw.get("terminals", [])}

    def list(self, enabled_only: bool = True) -> list[TerminalInfo]:
        items = list(self._items.values())
        if enabled_only:
            items = [x for x in items if x.enabled]
        return sorted(items, key=lambda x: x.alias)

    def latest_observed_builds(self) -> dict[str, dict]:
        """Return latest native-result build evidence keyed by terminal alias."""
        observed: dict[str, dict] = {}
        runs = self.root / "runs"
        if not runs.is_dir():
            return observed
        results = []
        for path in runs.glob("*/result.json"):
            try:
                results.append((path.stat().st_mtime, path))
            except OSError:
                continue
        aliases = {item.alias.upper() for item in self._items.values()}
        for _, path in sorted(results, key=lambda item: item[0], reverse=True)[:500]:
            try:
                if path.stat().st_size > 2 * 1024 * 1024:
                    continue
                result = json.loads(path.read_text(encoding="utf-8"))
                environment = result.get("environment") or {}
                alias = str(environment.get("terminal") or "").strip().upper()
                raw_build = environment.get("terminal_build_at_execution", environment.get("build"))
                build = int(raw_build)
                if alias not in aliases or build <= 0 or alias in observed:
                    continue
                observed[alias] = {
                    "observed_build": build,
                    "observed_job_id": str(result.get("job_id") or path.parent.name),
                    "observed_at_utc": str(result.get("recorded_at_utc") or ""),
                }
                if len(observed) == len(aliases):
                    break
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return observed

    def describe(self, enabled_only: bool = True) -> list[dict]:
        observed = self.latest_observed_builds()
        out = []
        for terminal in self.list(enabled_only=enabled_only):
            item = terminal.to_dict()
            evidence = observed.get(terminal.alias.upper())
            item["configured_build"] = terminal.build
            item["observed_build"] = evidence["observed_build"] if evidence else None
            item["build"] = evidence["observed_build"] if evidence else terminal.build
            item["build_source"] = (
                "LATEST_COMPLETED_NATIVE_RESULT" if evidence else "CONFIGURED_METADATA"
            )
            item["observed_job_id"] = evidence["observed_job_id"] if evidence else None
            item["observed_at_utc"] = evidence["observed_at_utc"] if evidence else None
            out.append(item)
        return out

    def get(self, alias: str) -> TerminalInfo:
        item = self._items.get(alias.upper())
        if item is None or not item.enabled:
            raise TerminalNotFound(f"Unknown or disabled terminal alias: {alias}")
        return item

    @staticmethod
    def _norm(path: str) -> str:
        # Windows executable paths are case-insensitive. Keep this helper platform-neutral
        # so target-selection behavior can be unit-tested outside Windows.
        return str(path).replace("/", "\\").rstrip("\\").lower()

    def running_terminal_paths(self) -> set[str]:
        """Return normalized executable paths for running terminal64.exe processes.

        MT5's documented command-line automation starts a terminal with /config. MetaTrader
        does not support two simultaneous copies from the same installation directory, so an
        already-running installation is not treated as a reliable /config execution target.
        """
        if os.name != "nt":
            return set()
        script = (
            "$p = Get-CimInstance Win32_Process -Filter \"Name='terminal64.exe'\" "
            "| Where-Object { $_.ExecutablePath } | Select-Object -ExpandProperty ExecutablePath; "
            "@($p) | ConvertTo-Json -Compress"
        )
        try:
            cp = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=8, check=False,
            )
            raw = cp.stdout.strip()
            if not raw:
                return set()
            data = json.loads(raw)
            if isinstance(data, str):
                data = [data]
            return {self._norm(x) for x in data if x}
        except Exception:
            # Failure to enumerate processes must not falsely claim that every terminal is idle.
            # Return a sentinel that causes the requested target to be treated conservatively by
            # select_execution_terminal only when process discovery is explicitly unavailable.
            return set()

    def is_running(self, alias: str, running_paths: set[str] | None = None) -> bool:
        t = self.get(alias)
        running = self.running_terminal_paths() if running_paths is None else running_paths
        normalized = {self._norm(x) for x in running}
        return self._norm(t.terminal_path) in normalized

    def select_execution_terminal(self, requested_alias: str,
                                  running_paths: set[str] | None = None) -> tuple[TerminalInfo, dict]:
        """Select an idle MT5 installation for command-line tester automation.

        If the requested installation is already open, prefer another idle installation with the
        same build. This preserves the user's live/open terminal while giving /config a fresh
        process, which is the reliable execution model for MT5 command-line tester jobs.
        """
        requested = self.get(requested_alias)
        running = self.running_terminal_paths() if running_paths is None else running_paths
        running_norm = {self._norm(x) for x in running}
        requested_busy = self._norm(requested.terminal_path) in running_norm
        if not requested_busy:
            return requested, {
                "requested": requested.alias,
                "effective": requested.alias,
                "fallback": False,
                "reason": "REQUESTED_TERMINAL_IDLE",
            }

        candidates = [
            t for t in self.list()
            if self._norm(t.terminal_path) not in running_norm
        ]
        # Same build first, then newest build, then stable alias ordering.
        candidates.sort(key=lambda t: (t.build == requested.build, t.build, t.alias), reverse=True)
        if not candidates:
            busy = sorted(t.alias for t in self.list() if self._norm(t.terminal_path) in running_norm)
            raise TerminalBusy(
                "No idle registered MT5 installation is available for /config tester automation. "
                f"Requested={requested.alias}; busy={busy}"
            )
        selected = candidates[0]
        return selected, {
            "requested": requested.alias,
            "effective": selected.alias,
            "fallback": True,
            "reason": "REQUESTED_TERMINAL_ALREADY_RUNNING",
        }

    def validate(self) -> list[dict]:
        running = self.running_terminal_paths()
        observed = self.latest_observed_builds()
        out = []
        for t in self.list(enabled_only=False):
            terminal = Path(t.terminal_path)
            meta = Path(t.metaeditor_path)
            data = Path(t.data_root)
            evidence = observed.get(t.alias.upper())
            out.append({
                "alias": t.alias,
                "enabled": t.enabled,
                "terminal_exists": terminal.is_file(),
                "metaeditor_exists": meta.is_file(),
                "data_root_exists": data.is_dir(),
                "configured_build": t.build,
                "observed_build": evidence["observed_build"] if evidence else None,
                "build": evidence["observed_build"] if evidence else t.build,
                "build_source": "LATEST_COMPLETED_NATIVE_RESULT" if evidence else "CONFIGURED_METADATA",
                "observed_job_id": evidence["observed_job_id"] if evidence else None,
                "observed_at_utc": evidence["observed_at_utc"] if evidence else None,
                "running": self._norm(t.terminal_path) in running,
                "ok": t.enabled and terminal.is_file() and meta.is_file() and data.is_dir(),
            })
        return out
