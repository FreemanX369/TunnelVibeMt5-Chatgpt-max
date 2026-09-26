"""Focused chart rollback regressions and interactive MT5-2 acceptance."""
from __future__ import annotations

import ctypes
import os
import struct
from types import SimpleNamespace

import pytest

from vibemql5.config import default_root
from vibemql5.core.concurrency import ConcurrencyManager
from vibemql5.core.inventory import TerminalInventory
from vibemql5.core.live_terminal import LiveTerminal
from vibemql5.core.live_terminal_windows import WindowsCharts, _WindowPlacement, _png_rgb


def test_bounded_mdi_message_checks_call_success():
    class Sender:
        def __call__(self, hwnd, message, wparam, lparam, flags, timeout, pointer):
            assert (hwnd, message, wparam, lparam, flags, timeout) == (200, 0x0223, 201, 0, 0x22, 2000)
            ctypes.cast(pointer, ctypes.POINTER(ctypes.c_size_t)).contents.value = 42
            return 1

    gui = WindowsCharts.__new__(WindowsCharts)
    gui.user = SimpleNamespace(SendMessageTimeoutW=Sender())
    assert gui._send_bounded(200, 0x0223, 201) == 42
    gui.user.SendMessageTimeoutW = lambda *_args: 0
    with pytest.raises(RuntimeError, match="LIVE_CHART_WINDOW_MESSAGE_TIMEOUT"):
        gui._send_bounded(200, 0x0223, 201)


def _fake_minimized_gui(monkeypatch, *, capture_fails=False, rollback_fails=False,
                        activation_fails=False, restore_times_out=False, selected=201,
                        placement_fails_after_dispatch=False, rollback_placement_fails=False,
                        activation_restores=False, navigation_fails=False):
    monkeypatch.setattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, raising=False)
    gui = WindowsCharts.__new__(WindowsCharts)
    iconic = {201: True, 202: True}
    active = [202]
    normal = {201: (32, 32, 427, 820), 202: (64, 64, 459, 2243)}
    originals = normal.copy()
    calls = []

    def placement(hwnd, pointer):
        rect = ctypes.cast(pointer, ctypes.POINTER(_WindowPlacement)).contents
        rect.showCmd = 2 if iconic[hwnd] else 1
        (rect.rcNormalPosition.left, rect.rcNormalPosition.top,
         rect.rcNormalPosition.right, rect.rcNormalPosition.bottom) = normal[hwnd]
        return 1

    def set_placement(hwnd, pointer):
        new = ctypes.cast(pointer, ctypes.POINTER(_WindowPlacement)).contents
        rect = new.rcNormalPosition
        target = (rect.left, rect.top, rect.right, rect.bottom)
        operation = "reset" if target == originals[hwnd] else "resize"
        calls.append((operation, hwnd))
        normal[hwnd] = target
        iconic[hwnd] = new.showCmd == 2
        if (operation == "resize" and placement_fails_after_dispatch
                or operation == "reset" and rollback_placement_fails):
            return 0
        return 1

    def send(hwnd, message, wparam, lparam, flags, timeout, pointer):
        assert flags == 0x22 and timeout == 2000
        if message == 0x0229:
            ctypes.cast(pointer, ctypes.POINTER(ctypes.c_size_t)).contents.value = active[0]
        elif message == 0x0223:
            assert hwnd == 200 and wparam == selected
            calls.append(("restore", wparam))
            iconic[wparam] = False
            active[0] = wparam
            if restore_times_out:
                return 0
        elif message == 0x0222:
            assert hwnd == 200 and wparam == 202
            calls.append(("activate", wparam))
            if not activation_fails:
                active[0] = wparam
                if activation_restores:
                    iconic[wparam] = False
                    normal[wparam] = (0, 0, 972, 575)
        elif message == 0x0112:
            assert wparam == 0xF020 and hwnd == selected
            if rollback_fails:
                return 0
            iconic[hwnd] = True
        elif message in (0x0100, 0x0101):
            assert hwnd == selected and wparam == 0x23 and not iconic[hwnd]
            assert lparam == (0x014F0001 if message == 0x0100 else 0xC14F0001)
            calls.append(("end_down" if message == 0x0100 else "end_up", hwnd))
            if navigation_fails and message == 0x0100:
                return 0
        else:
            raise AssertionError("UNEXPECTED_WINDOW_MESSAGE")
        return 1

    def minimize(hwnd, command):
        assert command == 6 and hwnd in (selected, active[0])
        calls.append(("minimize", hwnd))
        if rollback_fails:
            return 0
        iconic[hwnd] = True
        return 1

    gui.user = SimpleNamespace(
        EnumWindows=lambda callback, _data: callback(100, 0),
        EnumChildWindows=lambda _main, callback, _data: (callback(200, 0), callback(201, 0),
                                                         callback(202, 0), 0)[-1],
        GetParent=lambda hwnd: 200 if hwnd in iconic else 100,
        IsWindowVisible=lambda _hwnd: True,
        IsIconic=lambda hwnd: iconic[hwnd],
        GetWindowPlacement=placement,
        SetWindowPlacement=set_placement,
        SendMessageTimeoutW=send,
        ShowWindowAsync=minimize,
    )
    gui._path_for_hwnd = lambda _hwnd: "C:\\MT5-2\\terminal64.exe"
    gui._class = lambda hwnd: "MetaQuotes::MetaTrader::5.00" if hwnd == 100 else "MDIClient" if hwnd == 200 else "AfxChart"
    gui._size = lambda hwnd: (1075, 2320) if hwnd in (100, 200) else (
        (0, 0) if iconic[hwnd] else (normal[hwnd][2] - normal[hwnd][0] - 12,
                                        normal[hwnd][3] - normal[hwnd][1] - 35))
    gui.list_charts = lambda _path: [
        {"chart_id": hwnd, "visible": True, "renderable": not iconic[hwnd]
         and 32 <= gui._size(hwnd)[0] <= 2560 and 32 <= gui._size(hwnd)[1] <= 1600,
         "width": gui._size(hwnd)[0], "height": gui._size(hwnd)[1]}
        for hwnd in iconic]

    def capture(_path, hwnd):
        assert hwnd == selected and not iconic[hwnd]
        calls.append(("capture", hwnd))
        if capture_fails:
            raise RuntimeError("FAKE_CAPTURE_FAILED")
        return b"\x89PNG\r\n\x1a\n"

    gui._capture_process = capture
    return gui, iconic, active, calls


@pytest.mark.parametrize("capture_fails", [False, True])
def test_temporary_restore_capture_always_restores_minimized_chart(monkeypatch, capture_fails):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch, capture_fails=capture_fails)
    if capture_fails:
        with pytest.raises(RuntimeError, match="FAKE_CAPTURE_FAILED"):
            gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201, "native")
    else:
        assert gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201, "native") == b"\x89PNG\r\n\x1a\n"
    assert calls == [("restore", 201), ("end_down", 201), ("end_up", 201),
                     ("capture", 201), ("minimize", 201), ("activate", 202)]
    assert iconic == {201: True, 202: True}
    assert active == [202]
    assert gui._placement(201) == (2, (32, 32, 427, 820))


def test_temporary_restore_rejects_wrong_or_unsafe_chart_without_mutation(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch)
    with pytest.raises(RuntimeError, match="LIVE_CHART_NOT_FOUND_OR_VISIBLE"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 999, "native")
    with pytest.raises(RuntimeError, match="LIVE_CHART_NO_SAFE_RESTORE_SIZE"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 202, "native")
    assert iconic == {201: True, 202: True} and active == [202] and calls == []


def test_temporary_restore_rejects_unknown_active_selection_before_mutation(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch)
    active[0] = 0
    with pytest.raises(RuntimeError, match="LIVE_CHART_ACTIVE_WINDOW_UNVERIFIED"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201, "native")
    assert iconic == {201: True, 202: True} and calls == []


def test_temporary_restore_reports_failed_rollback(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch, capture_fails=True, rollback_fails=True)
    with pytest.raises(RuntimeError, match="LIVE_CHART_ROLLBACK_REQUEST_FAILED"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201, "native")
    assert calls == [("restore", 201), ("end_down", 201), ("end_up", 201),
                     ("capture", 201), ("minimize", 201)]
    assert iconic[201] is False  # The failed rollback is explicit and never reported as success.


def test_temporary_restore_reports_failed_active_selection(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch, activation_fails=True)
    with pytest.raises(RuntimeError, match="LIVE_CHART_ACTIVE_SELECTION_CHANGED"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201, "native")
    assert iconic == {201: True, 202: True}
    assert active == [201]
    assert calls[-1] == ("activate", 202)


def test_restore_message_timeout_after_dispatch_still_rolls_back(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch, restore_times_out=True)
    with pytest.raises(RuntimeError, match="LIVE_CHART_WINDOW_MESSAGE_TIMEOUT"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201, "native")
    assert calls == [("restore", 201), ("minimize", 201), ("activate", 202)]
    assert iconic == {201: True, 202: True} and active == [202]


def test_navigation_failure_rolls_back_without_capturing(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch, navigation_fails=True)
    with pytest.raises(RuntimeError, match="LIVE_CHART_WINDOW_MESSAGE_TIMEOUT"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201)
    assert calls[:5] == [("resize", 201), ("restore", 201), ("end_down", 201),
                         ("end_up", 201), ("reset", 201)]
    assert ("capture", 201) not in calls and calls[-1] == ("reset", 201)
    assert iconic == {201: True, 202: True} and active == [202]


def test_already_16_9_chart_navigates_without_resizing(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch)
    iconic[201] = False
    gui.list_charts = lambda _path: [
        {"chart_id": 201, "visible": True, "renderable": True, "width": 960, "height": 540},
        {"chart_id": 202, "visible": True, "renderable": False, "width": 0, "height": 0},
    ]
    assert gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201) == b"\x89PNG\r\n\x1a\n"
    assert calls == [("end_down", 201), ("end_up", 201), ("capture", 201)]
    assert active == [202]


def test_live_capture_minimized_chart_metadata_and_png(monkeypatch, tmp_path):
    gui, iconic, active, _calls = _fake_minimized_gui(monkeypatch)
    gui._capture_process = lambda _path, _hwnd: _png_rgb(380, 740, bytes([2, 1, 0, 0]) * (380 * 740))
    inventory = TerminalInventory.__new__(TerminalInventory)
    inventory.get = lambda _alias: SimpleNamespace(terminal_path="C:\\MT5-2\\terminal64.exe")
    inventory.is_running = lambda _alias: True
    meta, png = LiveTerminal(inventory, "MT5-2", gui=gui).capture(201, "native")
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert (meta["image_width"], meta["image_height"], meta["restored_temporarily"]) == (380, 740, True)
    assert (meta["chart"]["width"], meta["chart"]["height"]) == (0, 0)
    assert iconic == {201: True, 202: True} and active == [202]


@pytest.mark.parametrize("capture_fails", [False, True])
def test_16_9_minimized_capture_restores_original_even_if_native_rect_exceeds_limit(monkeypatch, capture_fails):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch, capture_fails=capture_fails, selected=202)
    before = {hwnd: gui._placement(hwnd) for hwnd in iconic}
    assert before[202][1][3] - before[202][1][1] > 1600
    with pytest.raises(RuntimeError, match="LIVE_CHART_NO_SAFE_RESTORE_SIZE"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 202, "native")
    if capture_fails:
        with pytest.raises(RuntimeError, match="FAKE_CAPTURE_FAILED"):
            gui.capture_chart("C:\\MT5-2\\terminal64.exe", 202)
    else:
        assert gui.capture_chart("C:\\MT5-2\\terminal64.exe", 202).startswith(b"\x89PNG")
    assert calls == [("resize", 202), ("restore", 202), ("end_down", 202),
                     ("end_up", 202), ("capture", 202), ("reset", 202)]
    assert {hwnd: gui._placement(hwnd) for hwnd in iconic} == before
    assert iconic == {201: True, 202: True} and active == [202]


def test_16_9_capture_of_visible_chart_preserves_mixed_mdi_layout(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch)
    iconic[201] = False
    before = {hwnd: gui._placement(hwnd) for hwnd in iconic}
    assert gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201).startswith(b"\x89PNG")
    assert calls == [("resize", 201), ("end_down", 201), ("end_up", 201),
                     ("capture", 201), ("reset", 201)]
    assert {hwnd: gui._placement(hwnd) for hwnd in iconic} == before
    assert iconic == {201: False, 202: True} and active == [202]


def test_16_9_invalid_ratio_does_not_mutate_mdi(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch)
    with pytest.raises(ValueError, match="LIVE_CHART_ASPECT_RATIO_INVALID"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201, "4:3")
    assert calls == [] and iconic == {201: True, 202: True} and active == [202]


def test_16_9_set_placement_failure_after_dispatch_still_restores_layout(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch, placement_fails_after_dispatch=True)
    before = {hwnd: gui._placement(hwnd) for hwnd in iconic}
    with pytest.raises(RuntimeError, match="LIVE_CHART_PLACEMENT_CHANGE_FAILED"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201)
    assert calls == [("resize", 201), ("reset", 201)]
    assert {hwnd: gui._placement(hwnd) for hwnd in iconic} == before
    assert iconic == {201: True, 202: True} and active == [202]


def test_16_9_reset_failure_is_reported_even_after_capture(monkeypatch):
    gui, _iconic, _active, calls = _fake_minimized_gui(monkeypatch, rollback_placement_fails=True)
    with pytest.raises(RuntimeError, match="LIVE_CHART_PLACEMENT_CHANGE_FAILED"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201)
    assert calls[-1] == ("reset", 201)


def test_16_9_rollback_recovers_active_window_placement_after_mdi_activation(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch, activation_restores=True)
    before = {hwnd: gui._placement(hwnd) for hwnd in iconic}
    assert gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201).startswith(b"\x89PNG")
    assert calls[-4:] == [("activate", 202), ("reset", 201), ("minimize", 202), ("reset", 202)]
    assert {hwnd: gui._placement(hwnd) for hwnd in iconic} == before
    assert iconic == {201: True, 202: True} and active == [202]


def test_16_9_tiny_visible_chart_rejected_before_mutation(monkeypatch):
    gui, iconic, active, calls = _fake_minimized_gui(monkeypatch)
    iconic[201] = False
    gui._size = lambda hwnd: (1075, 2320) if hwnd in (100, 200) else (20, 15) if hwnd == 201 else (0, 0)
    with pytest.raises(RuntimeError, match="LIVE_CHART_NOT_RENDERABLE"):
        gui.capture_chart("C:\\MT5-2\\terminal64.exe", 201)
    assert calls == [] and iconic == {201: False, 202: True} and active == [202]


@pytest.mark.skipif(os.name != "nt", reason="requires the interactive Windows VPS")
def test_tip040_live_mt5_2_account_chart_and_png():
    root = default_root()
    if not (root / "config" / "terminals.json").is_file():
        pytest.skip("No deployed MT5-2 root")
    inventory = TerminalInventory(root)
    if not inventory.is_running("MT5-2"):
        pytest.skip("Fixed MT5-2 is not already running")
    concurrency = ConcurrencyManager(root)
    if concurrency.status()["native_lock"] is not None:
        pytest.skip("Native tester/compile lease occupied")
    with concurrency.native_execution("TIP040-LIVE-SMOKE", kind="reversible_chart_capture", wait_seconds=2):
        live = LiveTerminal(inventory, "MT5-2", gui=WindowsCharts())
        state = live.state()
        assert state["terminal"]["alias"] == "MT5-2"
        assert state["terminal"]["ping_ms"] is None or state["terminal"]["ping_ms"] >= 0
        ea_files = live.ea_files()
        assert ea_files["status"] == "OK" and ea_files["executable_ex5_files"] >= 0
        charts = live.charts()["charts"]
        assert charts, "LIVE_CHARTS_EMPTY"
        selected = next((chart for chart in charts if chart["renderable"]), None)
        before = None
        active_before = None
        if selected is None:
            before = {chart["chart_id"]: live.gui._placement(chart["chart_id"]) for chart in charts}
            candidates = []
            for chart in charts:
                show_cmd, (left, top, right, bottom) = before[chart["chart_id"]]
                width, height = right - left, bottom - top
                if (chart["visible"] and not chart["width"] and not chart["height"] and show_cmd == 2
                        and 64 <= width <= 2560 and 64 <= height <= 1600 and width * height <= 3_000_000):
                    candidates.append((width * height, chart["chart_id"]))
            assert candidates, "LIVE_CHARTS_NOT_RENDERABLE"
            mdi = live.gui._bound_mdi(inventory.get("MT5-2").terminal_path, set(before))
            active_before = live.gui._send_bounded(mdi, 0x0229)
            inactive = [candidate for candidate in candidates if candidate[1] != active_before]
            selected = next(chart for chart in charts
                            if chart["chart_id"] == min(inactive or candidates)[1])
        meta, png = live.capture(selected["chart_id"], "native")
        if before is not None:
            assert meta["restored_temporarily"] is True
            assert {chart["chart_id"]: live.gui._placement(chart["chart_id"])
                    for chart in live.charts()["charts"]} == before, "LIVE_CHART_LAYOUT_NOT_RESTORED"
            assert live.gui._send_bounded(mdi, 0x0229) == active_before, "LIVE_CHART_SELECTION_CHANGED"
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack(">II", png[16:24]) == (meta["image_width"], meta["image_height"])
        assert meta["bytes"] == len(png)


@pytest.mark.skipif(os.name != "nt", reason="requires the interactive Windows VPS")
def test_tip041_live_each_open_chart_16_9_and_exact_layout_rollback():
    root = default_root()
    if not (root / "config" / "terminals.json").is_file():
        pytest.skip("No deployed MT5-2 root")
    inventory = TerminalInventory(root)
    if not inventory.is_running("MT5-2"):
        pytest.skip("Fixed MT5-2 is not already running")
    concurrency = ConcurrencyManager(root)
    if concurrency.status()["native_lock"] is not None:
        pytest.skip("Native tester/compile lease occupied")
    with concurrency.native_execution("TIP041-16-9-LIVE", kind="reversible_chart_capture", wait_seconds=2):
        live = LiveTerminal(inventory, "MT5-2", gui=WindowsCharts())
        charts = live.charts()["charts"]
        assert charts, "LIVE_CHARTS_EMPTY"
        ids = {chart["chart_id"] for chart in charts}
        mdi = live.gui._bound_mdi(inventory.get("MT5-2").terminal_path, ids)
        before = {hwnd: live.gui._placement(hwnd) for hwnd in ids}
        details = {hwnd: live.gui._placement_details(hwnd) for hwnd in ids}
        iconic = {hwnd: bool(live.gui.user.IsIconic(hwnd)) for hwnd in ids}
        active = live.gui._send_bounded(mdi, 0x0229)
        for chart in charts:
            meta, png = live.capture(chart["chart_id"])
            assert (meta["image_width"], meta["image_height"], meta["aspect_ratio"]) == (960, 540, "16:9")
            assert struct.unpack(">II", png[16:24]) == (960, 540)
            assert meta["bytes"] == len(png)
            assert {hwnd: live.gui._placement(hwnd) for hwnd in ids} == before
            assert {hwnd: live.gui._placement_details(hwnd) for hwnd in ids} == details
            assert {hwnd: bool(live.gui.user.IsIconic(hwnd)) for hwnd in ids} == iconic
            assert live.gui._send_bounded(mdi, 0x0229) == active
        assert {chart["chart_id"] for chart in live.charts()["charts"]} == ids
