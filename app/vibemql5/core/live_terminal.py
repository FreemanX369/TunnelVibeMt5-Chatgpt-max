"""Bounded, on-demand observations of the already running fixed MT5 terminal."""
from __future__ import annotations

import importlib
import math
import os
import re
import struct
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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

    def _initialize(self, mt5: Any) -> None:
        if mt5.initialize(self.terminal.terminal_path, timeout=2000):
            return
        try:
            error = mt5.last_error()
            authorization_failed = (isinstance(error, tuple) and len(error) == 2
                                    and type(error[0]) is int and error[0] == -6
                                    and isinstance(error[1], str))
        except Exception:
            authorization_failed = False
        raise RuntimeError("MT5_LIVE_AUTHORIZATION_FAILED" if authorization_failed
                           else "MT5_LIVE_IPC_INITIALIZE_FAILED")

    def state(self) -> dict[str, Any]:
        self._running()  # initialize() can start a terminal: never call it on an idle installation.
        mt5 = self.mt5 or importlib.import_module("MetaTrader5")
        self._initialize(mt5)
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

    @contextmanager
    def _market_session(self):
        self._running()
        mt5 = self.mt5 or importlib.import_module("MetaTrader5")
        self._initialize(mt5)
        try:
            info = mt5.terminal_info()
            if info is None:
                raise RuntimeError("MT5_LIVE_TERMINAL_INFO_UNAVAILABLE")
            if (self.inventory._norm(getattr(info, "path", "")) !=
                    self.inventory._norm(str(Path(self.terminal.terminal_path).parent)) or
                    self.inventory._norm(getattr(info, "data_path", "")) !=
                    self.inventory._norm(self.terminal.data_root) or
                    not self.inventory.is_running(self.alias)):
                raise RuntimeError("MT5_LIVE_TERMINAL_BINDING_MISMATCH")
            if not bool(getattr(info, "connected", False)):
                raise RuntimeError("MT5_LIVE_TERMINAL_DISCONNECTED")
            yield mt5, info
        finally:
            mt5.shutdown()

    @staticmethod
    def _utc_iso_from_epoch(value: int | float | None, *, milliseconds: bool = False) -> str | None:
        if value is None:
            return None
        scale = 1000.0 if milliseconds else 1.0
        try:
            return datetime.fromtimestamp(float(value) / scale, tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            return None

    @staticmethod
    def _parse_utc(value: str) -> datetime:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("UTC_TIMESTAMP_REQUIRED")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("UTC_TIMESTAMP_INVALID") from exc
        if parsed.tzinfo is None:
            raise ValueError("UTC_TIMESTAMP_TIMEZONE_REQUIRED")
        return parsed.astimezone(timezone.utc)

    def symbol_snapshot(self, symbol: str) -> dict[str, Any]:
        name = str(symbol or "").strip()
        if not name or len(name) > 64:
            raise ValueError("SYMBOL_REQUIRED")
        with self._market_session() as (mt5, terminal_info):
            info = mt5.symbol_info(name)
            tick = mt5.symbol_info_tick(name)
            if info is None:
                raise RuntimeError("MT5_SYMBOL_NOT_FOUND")
            if tick is None:
                raise RuntimeError("MT5_SYMBOL_TICK_UNAVAILABLE")
            return {
                "source": "MetaTrader5 Python IPC; exact requested symbol; no symbol aliasing",
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "terminal": {"alias": self.alias, "build": _integer(getattr(terminal_info, "build", None))},
                "symbol": {
                    "name": getattr(info, "name", name),
                    "digits": _integer(getattr(info, "digits", None)),
                    "point": _number(getattr(info, "point", None)),
                    "trade_tick_size": _number(getattr(info, "trade_tick_size", None)),
                    "trade_contract_size": _number(getattr(info, "trade_contract_size", None)),
                    "volume_min": _number(getattr(info, "volume_min", None)),
                    "volume_max": _number(getattr(info, "volume_max", None)),
                    "volume_step": _number(getattr(info, "volume_step", None)),
                    "spread": _integer(getattr(info, "spread", None)),
                    "spread_float": _flag(getattr(info, "spread_float", None)),
                    "trade_mode": _integer(getattr(info, "trade_mode", None)),
                    "visible": _flag(getattr(info, "visible", None)),
                    "selected": _flag(getattr(info, "select", None)),
                },
                "tick": {
                    "time": _integer(getattr(tick, "time", None)),
                    "time_utc": self._utc_iso_from_epoch(getattr(tick, "time", None)),
                    "time_msc": _integer(getattr(tick, "time_msc", None)),
                    "time_msc_utc": self._utc_iso_from_epoch(getattr(tick, "time_msc", None), milliseconds=True),
                    "bid": _number(getattr(tick, "bid", None)),
                    "ask": _number(getattr(tick, "ask", None)),
                    "last": _number(getattr(tick, "last", None)),
                    "volume": _integer(getattr(tick, "volume", None)),
                    "volume_real": _number(getattr(tick, "volume_real", None)),
                    "flags": _integer(getattr(tick, "flags", None)),
                },
            }

    def rates(self, symbol: str, timeframe: str = "M1", start_pos: int = 0, count: int = 200) -> dict[str, Any]:
        name = str(symbol or "").strip()
        frame = str(timeframe or "").strip().upper()
        if not name or len(name) > 64:
            raise ValueError("SYMBOL_REQUIRED")
        if type(start_pos) is not int or not 0 <= start_pos <= 100000:
            raise ValueError("RATES_START_POS_OUT_OF_RANGE")
        if type(count) is not int or not 1 <= count <= 2000:
            raise ValueError("RATES_COUNT_OUT_OF_RANGE")
        with self._market_session() as (mt5, terminal_info):
            timeframe_value = getattr(mt5, f"TIMEFRAME_{frame}", None)
            if timeframe_value is None:
                raise ValueError("TIMEFRAME_NOT_SUPPORTED")
            if mt5.symbol_info(name) is None:
                raise RuntimeError("MT5_SYMBOL_NOT_FOUND")
            raw = mt5.copy_rates_from_pos(name, timeframe_value, start_pos, count)
            if raw is None:
                err = mt5.last_error()
                raise RuntimeError(f"MT5_COPY_RATES_FAILED:{err}")
            rows = []
            for row in raw:
                epoch = int(row["time"])
                rows.append({
                    "time": epoch,
                    "time_utc": self._utc_iso_from_epoch(epoch),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "tick_volume": int(row["tick_volume"]),
                    "spread": int(row["spread"]),
                    "real_volume": int(row["real_volume"]),
                })
            newest_epoch = max((x["time"] for x in rows), default=None)
            for row in rows:
                row["bar_status"] = (
                    "FORMING" if start_pos == 0 and row["time"] == newest_epoch else "CLOSED_OR_HISTORICAL"
                )
            return {
                "source": "MetaTrader5.copy_rates_from_pos; exact requested symbol",
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "terminal": {"alias": self.alias, "build": _integer(getattr(terminal_info, "build", None))},
                "symbol": name,
                "timeframe": frame,
                "start_pos": start_pos,
                "requested_count": count,
                "returned_count": len(rows),
                "current_bar_requested": start_pos == 0,
                "coverage": {
                    "first_utc": rows[0]["time_utc"] if rows else None,
                    "last_utc": rows[-1]["time_utc"] if rows else None,
                },
                "rates": rows,
            }

    def ticks(self, symbol: str, from_utc: str, count: int = 1000, flags: str = "all") -> dict[str, Any]:
        name = str(symbol or "").strip()
        mode = str(flags or "all").strip().lower()
        if not name or len(name) > 64:
            raise ValueError("SYMBOL_REQUIRED")
        if type(count) is not int or not 1 <= count <= 5000:
            raise ValueError("TICKS_COUNT_OUT_OF_RANGE")
        if mode not in {"all", "info", "trade"}:
            raise ValueError("TICKS_FLAGS_INVALID")
        start = self._parse_utc(from_utc)
        start_us = (start - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(microseconds=1)
        with self._market_session() as (mt5, terminal_info):
            if mt5.symbol_info(name) is None:
                raise RuntimeError("MT5_SYMBOL_NOT_FOUND")
            flag_value = {
                "all": mt5.COPY_TICKS_ALL,
                "info": mt5.COPY_TICKS_INFO,
                "trade": mt5.COPY_TICKS_TRADE,
            }[mode]
            raw = mt5.copy_ticks_from(name, start, count, flag_value)
            if raw is None:
                err = mt5.last_error()
                raise RuntimeError(f"MT5_COPY_TICKS_FAILED:{err}")
            rows = []
            filtered_before_start = 0
            for row in raw:
                epoch = int(row["time"])
                msc = int(row["time_msc"])
                # MT5 rounds its datetime cursor to seconds; preserve the caller's exact bound.
                if msc * 1000 < start_us:
                    filtered_before_start += 1
                    continue
                rows.append({
                    "time": epoch,
                    "time_utc": self._utc_iso_from_epoch(epoch),
                    "time_msc": msc,
                    "time_msc_utc": self._utc_iso_from_epoch(msc, milliseconds=True),
                    "bid": float(row["bid"]),
                    "ask": float(row["ask"]),
                    "last": float(row["last"]),
                    "volume": int(row["volume"]),
                    "volume_real": float(row["volume_real"]),
                    "flags": int(row["flags"]),
                })
            return {
                "source": "MetaTrader5.copy_ticks_from; exact requested symbol",
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "terminal": {"alias": self.alias, "build": _integer(getattr(terminal_info, "build", None))},
                "symbol": name,
                "from_utc": start.isoformat(),
                "flags": mode,
                "requested_count": count,
                "returned_count": len(rows),
                "filtered_before_from_utc": filtered_before_start,
                "coverage": {
                    "first_utc": rows[0]["time_msc_utc"] if rows else None,
                    "last_utc": rows[-1]["time_msc_utc"] if rows else None,
                },
                "ticks": rows,
            }

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
