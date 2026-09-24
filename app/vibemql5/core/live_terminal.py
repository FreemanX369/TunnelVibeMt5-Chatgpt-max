"""Bounded, on-demand observations of the already running fixed MT5 terminal."""
from __future__ import annotations

import importlib
import math
import os
import re
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..parsers.tester_log import decode_text_bytes
from .inventory import TerminalInventory


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _flag(value: Any) -> bool | None:
    return bool(value) if value is not None else None


def _safe_line(line: str) -> str:
    if re.search(r"(?i)\b(password|api[_ -]?key|token|secret|credential|bearer)\b", line):
        return "[REDACTED_SENSITIVE_LOG_LINE]"
    line = re.sub(r"(?i)\bauthorization\s*[:=]\s*\S+", "authorization=[REDACTED]", line)
    line = re.sub(r"(?<!\d)\d{6,12}(?!\d)", "[ACCOUNT]", line)
    line = re.sub(r"(?i)\b[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL]", line)
    line = re.sub(r"(?i)(?:[A-Z]:\\|\\\\)[^\s\"']+", "[PATH]", line)
    return line[:500]


def _linked_directory(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


class LiveTerminal:
    def __init__(self, inventory: TerminalInventory, alias: str, gui: Any = None, mt5: Any = None):
        self.inventory = inventory
        self.alias = alias
        self.terminal = inventory.get(alias)
        self.gui = gui
        self.mt5 = mt5

    def _running(self) -> None:
        if not self.inventory.is_running(self.alias):
            raise RuntimeError("FIXED_TERMINAL_NOT_RUNNING")

    def state(self) -> dict[str, Any]:
        self._running()  # initialize() can start a terminal: never call it on an idle installation.
        mt5 = self.mt5 or importlib.import_module("MetaTrader5")
        if not mt5.initialize(self.terminal.terminal_path, timeout=2000):
            raise RuntimeError("MT5_LIVE_IPC_INITIALIZE_FAILED")
        try:
            info = mt5.terminal_info()
            if info is None:
                raise RuntimeError("MT5_LIVE_TERMINAL_INFO_UNAVAILABLE")
            # An IPC client can attach to another installed terminal. Require both roots.
            if (self.inventory._norm(getattr(info, "path", "")) !=
                    self.inventory._norm(str(Path(self.terminal.terminal_path).parent)) or
                    self.inventory._norm(getattr(info, "data_path", "")) !=
                    self.inventory._norm(self.terminal.data_root) or
                    not self.inventory.is_running(self.alias)):
                raise RuntimeError("MT5_LIVE_TERMINAL_BINDING_MISMATCH")
            connected = _flag(getattr(info, "connected", None))
            account = mt5.account_info() if connected else None
            if connected and account is None:
                raise RuntimeError("MT5_LIVE_ACCOUNT_INFO_UNAVAILABLE")
            ping_us = _integer(getattr(info, "ping_last", None))
            if ping_us is not None and ping_us < 0:
                ping_us = None
            login = str(getattr(account, "login", "") or "")
            count_positions = _integer(mt5.positions_total()) if account is not None else None
            count_orders = _integer(mt5.orders_total()) if account is not None else None
            if count_positions is not None and count_positions < 0:
                count_positions = None
            if count_orders is not None and count_orders < 0:
                count_orders = None
            return {
                "source": "MetaTrader5 Python IPC; bound to configured running executable and data root",
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "terminal": {"alias": self.alias, "build": _integer(getattr(info, "build", None)),
                             "connected": connected, "ping_last_us": ping_us,
                             "ping_ms": round(ping_us / 1000, 3) if connected and ping_us is not None else None,
                             "trade_allowed": _flag(getattr(info, "trade_allowed", None))},
                "account": {
                    "status": "CONNECTED" if connected else "UNAVAILABLE_DISCONNECTED",
                    "present": account is not None if connected else None,
                    "login_masked": ("*" * max(0, len(login) - 4) + login[-4:]) if login else None,
                    "server": getattr(account, "server", None), "currency": getattr(account, "currency", None),
                    "trade_mode": _integer(getattr(account, "trade_mode", None)),
                    "margin_mode": _integer(getattr(account, "margin_mode", None)),
                    "leverage": _integer(getattr(account, "leverage", None)),
                    "balance": _number(getattr(account, "balance", None)),
                    "equity": _number(getattr(account, "equity", None)),
                    "profit": _number(getattr(account, "profit", None)),
                    "credit": _number(getattr(account, "credit", None)),
                    "margin": _number(getattr(account, "margin", None)),
                    "free_margin": _number(getattr(account, "margin_free", None)),
                    "margin_level": _number(getattr(account, "margin_level", None)),
                    "trade_allowed": _flag(getattr(account, "trade_allowed", None)),
                    "expert_trade_allowed": _flag(getattr(account, "trade_expert", None)),
                    "positions_count": count_positions, "orders_count": count_orders,
                },
            }
        finally:
            mt5.shutdown()

    def charts(self) -> dict[str, Any]:
        self._running()
        if self.gui is None:
            from .live_terminal_windows import WindowsCharts
            self.gui = WindowsCharts()
        items = self.gui.list_charts(self.terminal.terminal_path)
        return {"source": "Win32 child windows of verified MT5-2 process", "alias": self.alias,
                "count": len(items), "charts": items,
                "attached_ea_count": None, "attached_ea_status": "UNKNOWN: Win32 does not expose EA attachment"}

    def capture(self, chart_id: int, aspect_ratio: str = "16:9") -> tuple[dict[str, Any], bytes]:
        if aspect_ratio not in {"16:9", "native"}:
            raise ValueError("LIVE_CHART_ASPECT_RATIO_INVALID")
        if isinstance(chart_id, bool) or not isinstance(chart_id, int) or chart_id <= 0:
            raise ValueError("CHART_ID_REQUIRED: use a chart_id returned by list_live_charts")
        charts = self.charts()["charts"]
        matches = [item for item in charts if item["chart_id"] == chart_id]
        if len(matches) != 1:
            raise RuntimeError("LIVE_CHART_NOT_FOUND_OR_AMBIGUOUS")
        item = matches[0]
        if not item["visible"]:
            raise RuntimeError("LIVE_CHART_NOT_VISIBLE")
        if item.get("renderable") is False and (item.get("width") != 0 or item.get("height") != 0):
            raise RuntimeError("LIVE_CHART_NOT_RENDERABLE")
        payload = self.gui.capture_chart(self.terminal.terminal_path, chart_id, aspect_ratio)
        if next((chart for chart in self.gui.list_charts(self.terminal.terminal_path)
                 if chart["chart_id"] == chart_id), None) != item:
            raise RuntimeError("LIVE_CHART_CHANGED_DURING_CAPTURE")
        if not payload.startswith(b"\x89PNG\r\n\x1a\n") or len(payload) > 8_000_000 or len(payload) < 24:
            raise RuntimeError("LIVE_CHART_INVALID_PNG")
        width, height = struct.unpack(">II", payload[16:24])
        if not (32 <= width <= 2560 and 32 <= height <= 1600 and width * height <= 3_000_000):
            raise RuntimeError("LIVE_CHART_INVALID_PNG_DIMENSIONS")
        if aspect_ratio == "16:9" and (width, height) != (960, 540):
            raise RuntimeError("LIVE_CHART_16_9_SIZE_UNVERIFIED")
        if aspect_ratio == "native" and item.get("renderable") is not False and (width, height) != (item["width"], item["height"]):
            raise RuntimeError("LIVE_CHART_CAPTURE_SIZE_MISMATCH")
        return {"alias": self.alias, "chart": item, "mime_type": "image/png", "bytes": len(payload),
                "image_width": width, "image_height": height,
                "aspect_ratio": aspect_ratio,
                "resized_temporarily": aspect_ratio == "16:9" and (item["width"], item["height"]) != (960, 540),
                "restored_temporarily": item.get("renderable") is False}, payload

    def logs(self, source: str = "journal", limit: int = 100) -> dict[str, Any]:
        if source not in {"journal", "experts"}:
            raise ValueError("LOG_SOURCE_INVALID")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("LOG_LIMIT_OUT_OF_RANGE")
        self._running()
        folder = Path(self.terminal.data_root) / ("Logs" if source == "journal" else "MQL5/Logs")
        if not folder.resolve().is_relative_to(Path(self.terminal.data_root).resolve()):
            raise RuntimeError("LOG_PATH_ESCAPES_FIXED_TERMINAL")
        candidates = sorted(folder.glob("[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].log"), reverse=True)
        if not candidates:
            return {"alias": self.alias, "source": source, "status": "NO_LOG_FILE", "lines": []}
        path = candidates[0]
        # One tail read only: no file-wide scan on each chat request.
        if path.resolve().parent != folder.resolve():
            raise RuntimeError("LOG_PATH_ESCAPES_FIXED_TERMINAL")
        with path.open("rb") as handle:
            prefix = handle.read(4)
            encoding = "utf-16-le" if prefix.startswith(b"\xff\xfe") else "utf-16-be" if prefix.startswith(b"\xfe\xff") else None
            size = handle.seek(0, 2)
            start = max(0, size - 131_072)
            if encoding and start % 2:
                start += 1
            handle.seek(start)
            data = handle.read(131_072)
        if start and encoding:
            decoded = data.decode(encoding, errors="replace")
            meta = {"encoding": encoding}
        else:
            decoded, meta = decode_text_bytes(data)
        lines = decoded.splitlines()
        if start:
            lines = lines[1:]
        return {"alias": self.alias, "source": source, "status": "OK", "log_date": path.stem,
                "lines": [_safe_line(x) for x in lines[-limit:]], "truncated_to_tail": start > 0,
                "encoding": meta["encoding"]}

    def ea_files(self) -> dict[str, Any]:
        """Count file names only; this says nothing about chart attachment or production use."""
        self._running()
        folder = Path(self.terminal.data_root) / "MQL5" / "Experts"
        data_root = Path(self.terminal.data_root).resolve()
        if not folder.is_dir() or _linked_directory(folder) or not folder.resolve().is_relative_to(data_root):
            return {"source": "fixed MT5-2 data-root filesystem", "status": "UNAVAILABLE",
                    "executable_ex5_files": None, "source_mq5_files": None}
        ex5 = mq5 = seen = 0
        for parent, dirs, files in os.walk(folder, followlinks=False):
            if not Path(parent).resolve().is_relative_to(data_root):
                raise RuntimeError("INSTALLED_EA_PATH_ESCAPES_FIXED_TERMINAL")
            dirs[:] = [name for name in dirs if not _linked_directory(Path(parent) / name)
                       and (Path(parent) / name).resolve().is_relative_to(data_root)]
            for name in files:
                path = Path(parent) / name
                if path.is_symlink():
                    continue
                seen += 1
                if seen > 10_000:
                    raise RuntimeError("INSTALLED_EA_INVENTORY_LIMIT_EXCEEDED")
                ex5 += name.lower().endswith(".ex5")
                mq5 += name.lower().endswith(".mq5")
        return {"source": "fixed MT5-2 data-root filesystem", "status": "OK",
                "executable_ex5_files": ex5, "source_mq5_files": mq5,
                "attached_ea_count": None, "meaning": "Installed file count; not a unique production EA count"}
