from __future__ import annotations

import json
import ctypes
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from vibemql5.core.facade import ToolFacade
from vibemql5.core.live_terminal import LiveTerminal
from vibemql5.core.live_terminal_windows import WindowsCharts, _png_rgb


class Inventory:
    running = True

    def __init__(self, root: Path):
        self.terminal = SimpleNamespace(terminal_path=str(root / "MT5-2" / "terminal64.exe"),
                                        data_root=str(root / "Data"))

    def get(self, alias):
        assert alias == "MT5-2"
        return self.terminal

    def is_running(self, alias):
        return self.running

    @staticmethod
    def _norm(value):
        return str(value).replace("/", "\\").lower().rstrip("\\")


class MT5:
    initialized = 0
    shutdowns = 0
    positions = 0
    orders = 0

    def __init__(self, inventory):
        self.terminal = SimpleNamespace(path=str(Path(inventory.terminal.terminal_path).parent),
                                        data_path=inventory.terminal.data_root,
                                        connected=True, ping_last=35720, build=6182, trade_allowed=False)
        self.account = SimpleNamespace(login=123456789, server="TEST", currency="USD", trade_mode=2,
                                       margin_mode=1, leverage=1000, balance=10000.0, equity=9980.5,
                                       profit=-19.5, credit=0.0, margin=2.0, margin_free=9978.5,
                                       margin_level=499025.0, trade_allowed=False, trade_expert=False)

    def initialize(self, path, timeout):
        assert timeout <= 2000
        self.initialized += 1
        return True

    def terminal_info(self):
        return self.terminal

    def account_info(self):
        return self.account

    def positions_total(self):
        return self.positions

    def orders_total(self):
        return self.orders

    def shutdown(self):
        self.shutdowns += 1


class GUI:
    def __init__(self):
        self.items = [{"chart_id": 27, "symbol": "XAUUSDm", "timeframe": "M1", "visible": True,
                       "width": 32, "height": 32, "expert": {"attached": None, "status": "UNKNOWN"}}]
        self.captures = []

    def list_charts(self, path):
        return self.items

    def capture_chart(self, path, chart_id, aspect_ratio="16:9"):
        self.captures.append((chart_id, aspect_ratio))
        width, height = (960, 540) if aspect_ratio == "16:9" else (32, 32)
        return _png_rgb(width, height, bytes([0, 1, 2, 0]) * (width * height))


def test_win32_child_enumeration_ignores_unused_return_value(tmp_path, monkeypatch):
    monkeypatch.setattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, raising=False)
    terminal_exe = str(tmp_path / "MT5-2" / "terminal64.exe")
    gui = WindowsCharts.__new__(WindowsCharts)
    gui.user = SimpleNamespace(
        EnumWindows=lambda callback, _data: callback(100, 0),
        EnumChildWindows=lambda _parent, callback, _data: (callback(200, 0), callback(201, 0), 0)[2],
        IsWindowVisible=lambda _hwnd: True,
        GetParent=lambda hwnd: 200 if hwnd == 201 else 100,
    )
    gui._path_for_hwnd = lambda _hwnd: terminal_exe
    gui._title = lambda hwnd: "XAUUSDm,M1" if hwnd == 201 else ""
    gui._size = lambda _hwnd: (1600, 900)
    gui._class = lambda hwnd: {100: "MetaQuotes::MetaTrader::5.00", 200: "MDIClient",
                              201: "AfxFrameOrView140su"}[hwnd]
    assert gui.list_charts(terminal_exe) == [{
        "chart_id": 201, "symbol": "XAUUSDm", "timeframe": "M1", "visible": True,
        "width": 1600, "height": 900, "renderable": True,
        "expert": {"attached": None, "status": "UNKNOWN"},
        "indicators": {"status": "UNKNOWN"},
    }]


def test_four_zero_client_charts_counted_under_verified_mdi(tmp_path, monkeypatch):
    monkeypatch.setattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, raising=False)
    terminal_exe = str(tmp_path / "MT5-2" / "terminal64.exe")
    gui = WindowsCharts.__new__(WindowsCharts)
    def children(_parent, callback, _data):
        for hwnd in [200, 201, 202, 203, 204]:
            callback(hwnd, 0)
        return 0
    gui.user = SimpleNamespace(
        EnumWindows=lambda callback, _data: callback(100, 0),
        EnumChildWindows=children,
        IsWindowVisible=lambda _hwnd: True,
        GetParent=lambda hwnd: 200 if hwnd >= 201 else 100,
    )
    gui._path_for_hwnd = lambda _hwnd: terminal_exe
    gui._title = lambda hwnd: {201: "XAUUSD247m,M1", 202: "XAUUSDm,M1",
                              203: "BTCUSDm,M1", 204: "XAUUSDm,M1"}.get(hwnd, "")
    gui._size = lambda hwnd: (0, 0) if hwnd >= 201 else (1075, 900)
    gui._class = lambda hwnd: "MDIClient" if hwnd == 200 else (
        "MetaQuotes::MetaTrader::5.00" if hwnd == 100 else "AfxFrameOrView140su")
    charts = gui.list_charts(terminal_exe)
    assert len(charts) == 4
    assert [item["symbol"] for item in charts] == ["XAUUSD247m", "XAUUSDm", "BTCUSDm", "XAUUSDm"]
    assert all(item["visible"] and not item["renderable"] and item["width"] == 0 for item in charts)
    monkeypatch.setattr(gui, "capture_chart", lambda _path, _chart_id, _ratio: _png_rgb(320, 200, bytes([0, 1, 2, 0]) * 64000))
    live = LiveTerminal(Inventory(tmp_path), "MT5-2", gui=gui)
    meta, png = live.capture(201, "native")
    assert meta["restored_temporarily"] is True
    assert (meta["chart"]["width"], meta["chart"]["height"]) == (0, 0)
    assert (meta["image_width"], meta["image_height"]) == (320, 200)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("unknown_chart_size", [None, (800, 600), (20, 15)])
def test_empty_mdi_is_zero_only_without_any_direct_child(tmp_path, monkeypatch, unknown_chart_size):
    monkeypatch.setattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, raising=False)
    terminal_exe = str(tmp_path / "MT5-2" / "terminal64.exe")
    gui = WindowsCharts.__new__(WindowsCharts)
    def children(_parent, callback, _data):
        callback(200, 0)  # Verified MDIClient.
        if unknown_chart_size:
            callback(201, 0)  # Child with no reliable symbol/timeframe title.
        return 0
    gui.user = SimpleNamespace(
        EnumWindows=lambda callback, _data: callback(100, 0),
        EnumChildWindows=children,
        IsWindowVisible=lambda _hwnd: True,
        GetParent=lambda hwnd: 200 if hwnd == 201 else 100,
    )
    gui._path_for_hwnd = lambda _hwnd: terminal_exe
    gui._title = lambda _hwnd: ""
    gui._size = lambda hwnd: unknown_chart_size if hwnd == 201 else (1075, 800)
    gui._class = lambda hwnd: {100: "MetaQuotes::MetaTrader::5.00", 200: "MDIClient",
                              201: "AfxFrameOrView140su"}[hwnd]
    if unknown_chart_size:
        with pytest.raises(RuntimeError, match="LIVE_CHART_WINDOWS_NOT_VERIFIABLE"):
            gui.list_charts(terminal_exe)
    else:
        assert gui.list_charts(terminal_exe) == []


def test_account_reads_only_exact_running_terminal_and_converts_ping(tmp_path):
    inventory = Inventory(tmp_path)
    mt5 = MT5(inventory)
    live = LiveTerminal(inventory, "MT5-2", mt5=mt5)
    state = live.state()
    assert state["terminal"]["ping_last_us"] == 35720
    assert state["terminal"]["ping_ms"] == 35.72
    assert state["account"]["equity"] == 9980.5
    assert state["account"]["free_margin"] == 9978.5
    assert state["account"]["leverage"] == 1000
    assert state["account"]["login_masked"] == "*****6789"
    assert state["account"]["positions_count"] == 0
    assert (mt5.initialized, mt5.shutdowns) == (1, 1)

    inventory.running = False
    with pytest.raises(RuntimeError, match="FIXED_TERMINAL_NOT_RUNNING"):
        live.state()
    assert mt5.initialized == 1


def test_disconnected_terminal_never_reports_stale_account_values(tmp_path):
    inventory = Inventory(tmp_path)
    mt5 = MT5(inventory)
    mt5.terminal.connected = False
    state = LiveTerminal(inventory, "MT5-2", mt5=mt5).state()
    assert state["account"]["status"] == "UNAVAILABLE_DISCONNECTED"
    assert state["account"]["balance"] is None
    assert state["account"]["positions_count"] is None
    assert state["terminal"]["ping_ms"] is None


def test_account_fails_closed_when_ipc_binds_other_installation(tmp_path):
    inventory = Inventory(tmp_path)
    mt5 = MT5(inventory)
    mt5.terminal.data_path = str(tmp_path / "OTHER_DATA")
    with pytest.raises(RuntimeError, match="BINDING_MISMATCH"):
        LiveTerminal(inventory, "MT5-2", mt5=mt5).state()
    assert mt5.shutdowns == 1


def test_chart_capture_uses_unique_hwnd_and_does_not_infer_ea(tmp_path):
    inventory, gui = Inventory(tmp_path), GUI()
    live = LiveTerminal(inventory, "MT5-2", gui=gui)
    chart = live.charts()
    assert chart["attached_ea_count"] is None
    assert chart["charts"][0]["expert"]["attached"] is None
    with pytest.raises(RuntimeError, match="NOT_FOUND_OR_AMBIGUOUS"):
        live.capture(999)
    assert gui.captures == []
    meta, png = live.capture(27)
    assert gui.captures == [(27, "16:9")]
    assert meta["mime_type"] == "image/png"
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png[16:24]) == (960, 540)
    assert (meta["aspect_ratio"], meta["resized_temporarily"]) == ("16:9", True)
    native, original = live.capture(27, "native")
    assert (native["aspect_ratio"], native["resized_temporarily"]) == ("native", False)
    assert struct.unpack(">II", original[16:24]) == (32, 32)
    with pytest.raises(ValueError, match="LIVE_CHART_ASPECT_RATIO_INVALID"):
        live.capture(27, "4:3")
    assert gui.captures == [(27, "16:9"), (27, "native")]


def test_log_tail_is_bounded_and_redacted(tmp_path):
    inventory = Inventory(tmp_path)
    folder = Path(inventory.terminal.data_root) / "Logs"
    folder.mkdir(parents=True)
    (folder / "20260924.log").write_bytes(("\ufeff" + "\n".join(
        [f"line {index}" for index in range(500)] + ["login=123456789 api_key=secret-fixture"]
    )).encode("utf-16-le"))
    live = LiveTerminal(inventory, "MT5-2", gui=GUI())
    logs = live.logs("journal", limit=2)
    assert len(logs["lines"]) == 2
    assert "secret-fixture" not in str(logs)
    assert "123456789" not in str(logs)
    with pytest.raises(ValueError, match="LOG_LIMIT_OUT_OF_RANGE"):
        live.logs("journal", 1000000)


@pytest.mark.parametrize("source,relative", [("journal", "Logs"), ("experts", "MQL5/Logs")])
def test_logs_reject_linked_directory_outside_fixed_root(tmp_path, source, relative):
    inventory = Inventory(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "20260924.log").write_text("private outside content")
    folder = Path(inventory.terminal.data_root) / relative
    folder.parent.mkdir(parents=True, exist_ok=True)
    try:
        folder.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(RuntimeError, match="LOG_PATH_ESCAPES_FIXED_TERMINAL"):
        LiveTerminal(inventory, "MT5-2", gui=GUI()).logs(source)


def test_installed_ea_file_count_is_bounded_and_never_claims_attachment(tmp_path):
    inventory = Inventory(tmp_path)
    folder = Path(inventory.terminal.data_root) / "MQL5" / "Experts"
    nested = folder / "custom"
    nested.mkdir(parents=True)
    (folder / "Example.ex5").write_bytes(b"compiled")
    (nested / "Other.EX5").write_bytes(b"compiled")
    (nested / "Other.mq5").write_text("source")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "Hidden.ex5").write_bytes(b"compiled")
    try:
        (folder / "escape").symlink_to(outside, target_is_directory=True)
    except OSError:
        pass  # Windows CI may not grant symlink creation.
    result = LiveTerminal(inventory, "MT5-2", gui=GUI()).ea_files()
    assert result["executable_ex5_files"] == 2
    assert result["source_mq5_files"] == 1
    assert result["attached_ea_count"] is None
    assert result["status"] == "OK"


def test_installed_ea_count_skips_windows_junction_directories(tmp_path, monkeypatch):
    inventory = Inventory(tmp_path)
    folder = Path(inventory.terminal.data_root) / "MQL5" / "Experts"
    linked = folder / "reparse"
    linked.mkdir(parents=True)
    (folder / "Owned.ex5").write_bytes(b"ex5")
    (linked / "Outside.ex5").write_bytes(b"ex5")
    original = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda path: path.name == "reparse" or original(path))
    result = LiveTerminal(inventory, "MT5-2", gui=GUI()).ea_files()
    assert result["executable_ex5_files"] == 1


def test_mcp_capture_returns_image_content_without_encoded_text(tmp_path, monkeypatch):
    from vibemql5.adapters.mcp import create_server
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "terminals.json").write_text(json.dumps({"terminals": []}), encoding="utf-8")
    png = _png_rgb(32, 32, bytes([0, 1, 2, 0]) * 1024)
    monkeypatch.setattr(ToolFacade, "reconcile_cancelled_jobs", lambda self, **_kw: {})
    ratios = []
    def fake_capture(_self, chart_id, aspect_ratio):
        ratios.append(aspect_ratio)
        return (
        {"alias": "MT5-2", "chart": {"chart_id": chart_id}, "mime_type": "image/png", "bytes": len(png)}, png
        )
    monkeypatch.setattr(ToolFacade, "capture_live_chart", fake_capture)
    server = create_server(tmp_path, transport="stdio")
    capture_tool = server._tool_manager._tools["capture_live_chart"]
    annotations = capture_tool.annotations
    assert annotations.read_only_hint is False
    assert annotations.destructive_hint is False
    assert annotations.idempotent_hint is True
    assert capture_tool.parameters["properties"]["aspect_ratio"]["default"] == "16:9"
    response = capture_tool.fn(ctx=object(), chart_id=27)
    assert response.content[1].type == "image"
    assert response.content[1].mime_type == "image/png"
    assert response.structured_content["chart"]["chart_id"] == 27
    assert all("iVBOR" not in item.text for item in response.content if item.type == "text")
    capture_tool.fn(ctx=object(), chart_id=27, aspect_ratio="native")
    assert ratios == ["16:9", "native"]
