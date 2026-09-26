"""Windows chart discovery and client-only capture, bound to one MT5 executable."""
from __future__ import annotations

import ctypes
import os
import re
import struct
import subprocess
import sys
import time
import zlib
from ctypes import wintypes
from pathlib import Path

_CHART_TITLE = re.compile(
    r"^([A-Za-z0-9_.#-]{1,48}),(M(?:1|2|3|4|5|6|10|12|15|20|30)|H(?:1|2|3|4|6|8|12)|D1|W1|MN1)(?:\b|\s|$)"
)


def _png_rgb(width: int, height: int, bgra: bytes) -> bytes:
    """Encode a top-down Win32 32-bit DIB without writing an image to the VPS."""
    if len(bgra) != width * height * 4:
        raise RuntimeError("CHART_CAPTURE_INVALID_DIB")
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        start = y * width * 4
        end = start + width * 4
        rgb = bytearray(width * 3)
        rgb[0::3] = bgra[start + 2:end:4]
        rgb[1::3] = bgra[start + 1:end:4]
        rgb[2::3] = bgra[start:end:4]
        raw.extend(rgb)

    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, level=3)) + chunk(b"IEND", b""))


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("bmiHeader", _BitmapInfoHeader), ("bmiColors", wintypes.DWORD * 1)]


class _WindowPlacement(ctypes.Structure):
    _fields_ = [("length", wintypes.UINT), ("flags", wintypes.UINT), ("showCmd", wintypes.UINT),
                ("ptMinPosition", wintypes.POINT), ("ptMaxPosition", wintypes.POINT),
                ("rcNormalPosition", wintypes.RECT), ("rcDevice", wintypes.RECT)]


class WindowsCharts:
    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("WINDOWS_CHARTS_UNAVAILABLE")
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
        self.user.EnumChildWindows.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.LPARAM]
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.GetParent.argtypes = [wintypes.HWND]
        self.user.GetParent.restype = wintypes.HWND
        self.user.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(_WindowPlacement)]
        self.user.SetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(_WindowPlacement)]
        self.user.SetWindowPlacement.restype = wintypes.BOOL
        self.user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user.IsIconic.argtypes = [wintypes.HWND]
        self.user.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                                  wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        self.user.SendMessageTimeoutW.restype = wintypes.BOOL
        self.user.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.ShowWindowAsync.restype = wintypes.BOOL
        self.user.GetDC.argtypes = [wintypes.HWND]
        self.user.GetDC.restype = wintypes.HDC
        self.user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self.user.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
        self.gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self.gdi.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        self.gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        self.gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self.gdi.SelectObject.restype = wintypes.HGDIOBJ
        self.gdi.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                     ctypes.c_void_p, ctypes.POINTER(_BitmapInfo), wintypes.UINT]
        self.gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self.gdi.DeleteDC.argtypes = [wintypes.HDC]
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                           wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]

    def _path_for_hwnd(self, hwnd: int) -> str | None:
        pid = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        handle = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return None
        try:
            path = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(path))
            return path.value if self.kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(length)) else None
        finally:
            self.kernel.CloseHandle(handle)

    def _title(self, hwnd: int) -> str:
        size = self.user.GetWindowTextLengthW(hwnd)
        if size <= 0 or size > 200:
            return ""
        buffer = ctypes.create_unicode_buffer(size + 1)
        self.user.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    def _size(self, hwnd: int) -> tuple[int, int]:
        rect = wintypes.RECT()
        if not self.user.GetClientRect(hwnd, ctypes.byref(rect)):
            return (0, 0)
        return (rect.right - rect.left, rect.bottom - rect.top)

    def _class(self, hwnd: int) -> str:
        buffer = ctypes.create_unicode_buffer(128)
        return buffer.value if self.user.GetClassNameW(hwnd, buffer, len(buffer)) else ""

    def list_charts(self, terminal_exe: str) -> list[dict]:
        callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        mains: list[int] = []
        target = str(Path(terminal_exe)).replace("/", "\\").rstrip("\\").casefold()

        @callback
        def main_cb(hwnd, _data):
            if (self._path_for_hwnd(hwnd) or "").replace("/", "\\").casefold() == target:
                mains.append(hwnd)
            return True

        if not self.user.EnumWindows(main_cb, 0):
            raise RuntimeError("MT5_WINDOWS_ENUMERATION_FAILED")
        if not mains:
            raise RuntimeError("MT5_WINDOW_NOT_FOUND_IN_INTERACTIVE_SESSION")
        children: list[int] = []

        @callback
        def child_cb(hwnd, _data):
            if (self._path_for_hwnd(hwnd) or "").replace("/", "\\").casefold() != target:
                return True
            children.append(hwnd)
            return True

        for main in mains:
            # Microsoft documents the EnumChildWindows BOOL return as unused.
            # A zero result does not prove enumeration failed; trust only validated callbacks.
            self.user.EnumChildWindows(main, child_cb, 0)
        main_visible = [hwnd for hwnd in mains if self.user.IsWindowVisible(hwnd)
                        and self._size(hwnd)[0] >= 200 and self._size(hwnd)[1] >= 150]
        mdi = [hwnd for hwnd in children if self._class(hwnd) == "MDIClient"
               and self.user.IsWindowVisible(hwnd) and self._size(hwnd)[0] >= 200
               and self._size(hwnd)[1] >= 150]
        if (len(main_visible) != 1 or self._class(main_visible[0]) != "MetaQuotes::MetaTrader::5.00"
                or len(mdi) != 1):
            raise RuntimeError("LIVE_CHART_WINDOWS_NOT_VERIFIABLE")
        direct = [hwnd for hwnd in children if self.user.GetParent(hwnd) == mdi[0]]
        charts = []
        for hwnd in direct:
            if not (match := _CHART_TITLE.match(self._title(hwnd))):
                raise RuntimeError("LIVE_CHART_WINDOWS_NOT_VERIFIABLE")
            width, height = self._size(hwnd)
            visible = bool(self.user.IsWindowVisible(hwnd))
            charts.append({"chart_id": hwnd, "symbol": match.group(1), "timeframe": match.group(2),
                           "visible": visible, "width": width, "height": height,
                           "renderable": visible and width >= 32 and height >= 32
                           and width <= 2560 and height <= 1600 and width * height <= 3_000_000,
                           "expert": {"attached": None, "status": "UNKNOWN"},
                           "indicators": {"status": "UNKNOWN"}})
        return sorted(charts, key=lambda item: item["chart_id"])

    def capture_chart(self, terminal_exe: str, chart_id: int, aspect_ratio: str = "16:9") -> bytes:
        """Run PrintWindow in a disposable process with a bounded render timeout."""
        if aspect_ratio not in {"16:9", "native"}:
            raise ValueError("LIVE_CHART_ASPECT_RATIO_INVALID")
        charts = self.list_charts(terminal_exe)
        selected = next((chart for chart in charts if chart["chart_id"] == chart_id), None)
        if selected is None or not selected["visible"]:
            raise RuntimeError("LIVE_CHART_NOT_FOUND_OR_VISIBLE")
        if aspect_ratio == "16:9":
            if selected["renderable"] and (selected["width"], selected["height"]) == (960, 540):
                return self._capture_at_latest(terminal_exe, chart_id)
            if not selected["renderable"] and (selected["width"] or selected["height"]):
                raise RuntimeError("LIVE_CHART_NOT_RENDERABLE")
            return self._temporarily_resize_capture(terminal_exe, chart_id, charts)
        if selected["renderable"]:
            return self._capture_at_latest(terminal_exe, chart_id)
        if selected["width"] or selected["height"]:
            raise RuntimeError("LIVE_CHART_NOT_RENDERABLE")
        return self._temporarily_restore_capture(terminal_exe, chart_id, charts)

    def _capture_at_latest(self, terminal_exe: str, chart_id: int) -> bytes:
        # End moves the selected MT5 chart to its newest bar without changing Auto Scroll.
        try:
            self._send_bounded(chart_id, 0x0100, 0x23, 0x014F0001)  # WM_KEYDOWN / VK_END
        finally:
            self._send_bounded(chart_id, 0x0101, 0x23, 0xC14F0001)  # WM_KEYUP / VK_END
        time.sleep(0.12)  # Let MT5 paint the new viewport before PrintWindow.
        return self._capture_process(terminal_exe, chart_id)

    def _capture_process(self, terminal_exe: str, chart_id: int) -> bytes:
        try:
            done = subprocess.run(
                [sys.executable, "-m", "vibemql5.core.live_terminal_windows", terminal_exe, str(chart_id)],
                capture_output=True, check=False, timeout=8,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("LIVE_CHART_CAPTURE_TIMEOUT") from exc
        if done.returncode or not done.stdout.startswith(b"\x89PNG\r\n\x1a\n") or len(done.stdout) > 8_000_000:
            raise RuntimeError("LIVE_CHART_CAPTURE_FAILED")
        return done.stdout

    def _placement(self, hwnd: int) -> tuple[int, tuple[int, ...]]:
        placement = self._placement_state(hwnd)
        rect = placement.rcNormalPosition
        return int(placement.showCmd), (rect.left, rect.top, rect.right, rect.bottom)

    def _placement_state(self, hwnd: int) -> _WindowPlacement:
        placement = _WindowPlacement()
        placement.length = ctypes.sizeof(placement)
        if not self.user.GetWindowPlacement(hwnd, ctypes.byref(placement)):
            raise RuntimeError("LIVE_CHART_PLACEMENT_UNAVAILABLE")
        return placement

    def _set_placement(self, hwnd: int, placement: _WindowPlacement) -> None:
        if not self.user.SetWindowPlacement(hwnd, ctypes.byref(placement)):
            raise RuntimeError("LIVE_CHART_PLACEMENT_CHANGE_FAILED")

    def _placement_details(self, hwnd: int) -> tuple[int, ...]:
        state = self._placement_state(hwnd)
        return (state.flags, state.ptMinPosition.x, state.ptMinPosition.y,
                state.ptMaxPosition.x, state.ptMaxPosition.y,
                state.rcDevice.left, state.rcDevice.top, state.rcDevice.right, state.rcDevice.bottom)

    def _send_bounded(self, hwnd: int, message: int, wparam: int = 0, lparam: int = 0) -> int:
        result = ctypes.c_size_t()
        if not self.user.SendMessageTimeoutW(hwnd, message, wparam, lparam, 0x0002 | 0x0020, 2000,
                                              ctypes.byref(result)):
            raise RuntimeError("LIVE_CHART_WINDOW_MESSAGE_TIMEOUT")
        return result.value  # WM_MDIRESTORE returns zero on success; the API BOOL is authoritative.

    def _bound_mdi(self, terminal_exe: str, chart_ids: set[int]) -> int:
        """Confirm one visible MT5 MDI client and exactly the requested chart identities."""
        callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        target = str(Path(terminal_exe)).replace("/", "\\").rstrip("\\").casefold()
        owned = lambda hwnd: (self._path_for_hwnd(hwnd) or "").replace("/", "\\").casefold() == target
        mains: list[int] = []

        @callback
        def main_cb(hwnd, _data):
            if owned(hwnd) and self._class(hwnd) == "MetaQuotes::MetaTrader::5.00" and self.user.IsWindowVisible(hwnd):
                mains.append(hwnd)
            return True

        self.user.EnumWindows(main_cb, 0)
        if len(mains) != 1:
            raise RuntimeError("LIVE_CHART_MAIN_NOT_UNIQUE")
        children: list[int] = []

        @callback
        def child_cb(hwnd, _data):
            if owned(hwnd):
                children.append(hwnd)
            return True

        self.user.EnumChildWindows(mains[0], child_cb, 0)  # Return value is unused by Win32.
        mdi = [hwnd for hwnd in children if self._class(hwnd) == "MDIClient" and self.user.IsWindowVisible(hwnd)
               and self._size(hwnd)[0] >= 200 and self._size(hwnd)[1] >= 150]
        if len(mdi) != 1 or {hwnd for hwnd in children if self.user.GetParent(hwnd) == mdi[0]} != chart_ids:
            raise RuntimeError("LIVE_CHART_MDI_BINDING_CHANGED")
        return mdi[0]

    def _temporarily_restore_capture(self, terminal_exe: str, chart_id: int, charts: list[dict]) -> bytes:
        """Restore only the selected exact-process minimized chart, then verify full rollback."""
        ids = {item["chart_id"] for item in charts}
        if len(ids) != len(charts) or chart_id not in ids:
            raise RuntimeError("LIVE_CHART_IDENTITIES_UNAVAILABLE")
        mdi = self._bound_mdi(terminal_exe, ids)
        before = {hwnd: self._placement(hwnd) for hwnd in ids}
        if any(before[hwnd][0] != 2 or not self.user.IsIconic(hwnd) for hwnd in ids):
            raise RuntimeError("LIVE_CHART_RESTORE_PRECONDITION_FAILED")
        left, top, right, bottom = before[chart_id][1]
        width, height = right - left, bottom - top
        if not (64 <= width <= 2560 and 64 <= height <= 1600 and width * height <= 3_000_000):
            raise RuntimeError("LIVE_CHART_NO_SAFE_RESTORE_SIZE")
        active = self._send_bounded(mdi, 0x0229)  # WM_MDIGETACTIVE; read only.
        if active not in ids:
            raise RuntimeError("LIVE_CHART_ACTIVE_WINDOW_UNVERIFIED")
        try:
            self._send_bounded(mdi, 0x0223, chart_id)  # WM_MDIRESTORE sent to the bound MDI client.
            deadline = time.monotonic() + 2
            while True:
                current = next((item for item in self.list_charts(terminal_exe) if item["chart_id"] == chart_id), None)
                if current and current["renderable"] and not self.user.IsIconic(chart_id):
                    return self._capture_at_latest(terminal_exe, chart_id)
                if time.monotonic() >= deadline:
                    raise RuntimeError("LIVE_CHART_RESTORE_NOT_RENDERABLE")
                time.sleep(0.05)
        finally:
            # The window message can time out after MT5 has processed it. Always try rollback.
            if not self.user.ShowWindowAsync(chart_id, 6):  # SW_MINIMIZE
                try:
                    self._send_bounded(chart_id, 0x0112, 0xF020)  # WM_SYSCOMMAND / SC_MINIMIZE
                except RuntimeError as exc:
                    raise RuntimeError("LIVE_CHART_ROLLBACK_REQUEST_FAILED") from exc
            self._verify_restored_layout(terminal_exe, mdi, ids, before)
            if self._send_bounded(mdi, 0x0229) != active:
                try:
                    self._send_bounded(mdi, 0x0222, active)  # WM_MDIACTIVATE original exact child.
                finally:
                    # Activation should leave minimized windows untouched. If MT5 restores
                    # one, still undo that change before reporting a rollback failure.
                    for hwnd in ids:
                        if not self.user.IsIconic(hwnd) and not self.user.ShowWindowAsync(hwnd, 6):
                            raise RuntimeError("LIVE_CHART_ROLLBACK_REQUEST_FAILED")
                    self._verify_restored_layout(terminal_exe, mdi, ids, before)
            if self._send_bounded(mdi, 0x0229) != active:
                raise RuntimeError("LIVE_CHART_ACTIVE_SELECTION_CHANGED")

    def _temporarily_resize_capture(self, terminal_exe: str, chart_id: int, charts: list[dict]) -> bytes:
        """Capture a 960x540 client area and restore all MDI placement and selection state."""
        ids = {item["chart_id"] for item in charts}
        if len(ids) != len(charts) or chart_id not in ids:
            raise RuntimeError("LIVE_CHART_IDENTITIES_UNAVAILABLE")
        mdi = self._bound_mdi(terminal_exe, ids)
        before = {hwnd: self._placement(hwnd) for hwnd in ids}
        details = {hwnd: self._placement_details(hwnd) for hwnd in ids}
        states = {hwnd: self._placement_state(hwnd) for hwnd in ids}
        iconic = {hwnd: bool(self.user.IsIconic(hwnd)) for hwnd in ids}
        selected = next(item for item in charts if item["chart_id"] == chart_id)
        if (iconic[chart_id] and (before[chart_id][0] != 2 or selected["width"] or selected["height"])):
            raise RuntimeError("LIVE_CHART_RESIZE_PRECONDITION_FAILED")
        if not iconic[chart_id] and (before[chart_id][0] not in (1, 3) or not selected["renderable"]):
            raise RuntimeError("LIVE_CHART_RESIZE_PRECONDITION_FAILED")
        mdi_width, mdi_height = self._size(mdi)
        if mdi_width < 972 or mdi_height < 575:
            raise RuntimeError("LIVE_CHART_MDI_TOO_SMALL_FOR_16_9")
        active = self._send_bounded(mdi, 0x0229)  # WM_MDIGETACTIVE
        if active not in ids:
            raise RuntimeError("LIVE_CHART_ACTIVE_WINDOW_UNVERIFIED")
        original = states[chart_id]
        if self._placement(chart_id) != before[chart_id] or self._placement_details(chart_id) != details[chart_id]:
            raise RuntimeError("LIVE_CHART_PLACEMENT_CHANGED_BEFORE_CAPTURE")
        modified = _WindowPlacement.from_buffer_copy(original)
        rect = modified.rcNormalPosition
        left = max(0, min(rect.left, mdi_width - 972))
        top = max(0, min(rect.top, mdi_height - 575))
        rect.left, rect.top, rect.right, rect.bottom = left, top, left + 972, top + 575
        if original.showCmd == 3:  # A maximized child must be normal during the capture.
            modified.showCmd = 1
        try:
            self._set_placement(chart_id, modified)
            if iconic[chart_id]:
                self._send_bounded(mdi, 0x0223, chart_id)  # WM_MDIRESTORE
            deadline = time.monotonic() + 2
            while True:
                current = next((item for item in self.list_charts(terminal_exe) if item["chart_id"] == chart_id), None)
                if (current and current["renderable"] and not self.user.IsIconic(chart_id)
                        and (current["width"], current["height"]) == (960, 540)):
                    return self._capture_at_latest(terminal_exe, chart_id)
                if time.monotonic() >= deadline:
                    raise RuntimeError("LIVE_CHART_16_9_SIZE_UNVERIFIED")
                time.sleep(0.05)
        finally:
            # SetWindowPlacement may change a chart even when it reports failure.
            self._set_placement(chart_id, original)
            if iconic[chart_id] and not self.user.IsIconic(chart_id):
                if not self.user.ShowWindowAsync(chart_id, 6):  # SW_MINIMIZE
                    self._send_bounded(chart_id, 0x0112, 0xF020)
                self._set_placement(chart_id, original)
            self._verify_restored_layout(terminal_exe, mdi, ids, before, iconic, details)
            if self._send_bounded(mdi, 0x0229) != active:
                try:
                    self._send_bounded(mdi, 0x0222, active)  # WM_MDIACTIVATE
                finally:
                    # Activation can restore a minimized child on some MT5 builds.
                    self._set_placement(chart_id, original)
                    if iconic[active] and not self.user.IsIconic(active):
                        if not self.user.ShowWindowAsync(active, 6):
                            raise RuntimeError("LIVE_CHART_ROLLBACK_REQUEST_FAILED")
                        self._set_placement(active, states[active])
                    self._verify_restored_layout(terminal_exe, mdi, ids, before, iconic, details)
            if self._send_bounded(mdi, 0x0229) != active:
                raise RuntimeError("LIVE_CHART_ACTIVE_SELECTION_CHANGED")

    def _verify_restored_layout(self, terminal_exe: str, mdi: int, ids: set[int],
                                before: dict[int, tuple[int, tuple[int, ...]]],
                                iconic: dict[int, bool] | None = None,
                                details: dict[int, tuple[int, ...]] | None = None) -> None:
        iconic = iconic or {hwnd: True for hwnd in ids}
        deadline = time.monotonic() + 3
        while True:
            if (self._bound_mdi(terminal_exe, ids) == mdi
                    and {item["chart_id"]: self._placement(item["chart_id"])
                         for item in self.list_charts(terminal_exe)} == before
                    and all(bool(self.user.IsIconic(hwnd)) == iconic[hwnd] for hwnd in ids)
                    and (details is None or {hwnd: self._placement_details(hwnd) for hwnd in ids} == details)):
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("LIVE_CHART_ROLLBACK_LAYOUT_CHANGED")
            time.sleep(0.05)

    def _capture_local(self, terminal_exe: str, chart_id: int) -> bytes:
        before = next((c for c in self.list_charts(terminal_exe) if c["chart_id"] == chart_id), None)
        if not before or not before["visible"] or not before["renderable"]:
            raise RuntimeError("LIVE_CHART_NOT_FOUND_OR_VISIBLE")
        width, height = before["width"], before["height"]
        if width > 2560 or height > 1600 or width * height > 3_000_000:
            raise RuntimeError("LIVE_CHART_DIMENSIONS_EXCEED_LIMIT")
        source_dc = self.user.GetDC(chart_id)
        if not source_dc:
            raise RuntimeError("LIVE_CHART_DC_UNAVAILABLE")
        memory_dc = bitmap = old = None
        try:
            memory_dc = self.gdi.CreateCompatibleDC(source_dc)
            bitmap = self.gdi.CreateCompatibleBitmap(source_dc, width, height)
            if not memory_dc or not bitmap:
                raise RuntimeError("LIVE_CHART_BITMAP_UNAVAILABLE")
            old = self.gdi.SelectObject(memory_dc, bitmap)
            if not old or not self.user.PrintWindow(chart_id, memory_dc, 1):  # PW_CLIENTONLY
                raise RuntimeError("LIVE_CHART_PRINTWINDOW_FAILED")
            self.gdi.SelectObject(memory_dc, old)
            old = None  # GetDIBits requires the bitmap to be deselected from all DCs.
            info = _BitmapInfo()
            info.bmiHeader = _BitmapInfoHeader(ctypes.sizeof(_BitmapInfoHeader), width, -height, 1, 32, 0,
                                                width * height * 4, 0, 0, 0, 0)
            pixels = ctypes.create_string_buffer(width * height * 4)
            if self.gdi.GetDIBits(memory_dc, bitmap, 0, height, pixels, ctypes.byref(info), 0) != height:
                raise RuntimeError("LIVE_CHART_GETDIBITS_FAILED")
            step = max(1, width * height // 4096)
            if len({pixels.raw[i:i + 3] for i in range(0, len(pixels), 4 * step)}) < 3:
                raise RuntimeError("LIVE_CHART_BLANK_CAPTURE")
            after = next((c for c in self.list_charts(terminal_exe) if c["chart_id"] == chart_id), None)
            if after != before:
                raise RuntimeError("LIVE_CHART_CHANGED_DURING_CAPTURE")
            image = _png_rgb(width, height, pixels.raw)
            if len(image) > 8_000_000:
                raise RuntimeError("LIVE_CHART_PNG_TOO_LARGE")
            return image
        finally:
            if old:
                self.gdi.SelectObject(memory_dc, old)
            if bitmap:
                self.gdi.DeleteObject(bitmap)
            if memory_dc:
                self.gdi.DeleteDC(memory_dc)
            self.user.ReleaseDC(chart_id, source_dc)


if __name__ == "__main__":
    if len(sys.argv) != 3 or os.name != "nt":
        sys.exit(2)
    try:
        sys.stdout.buffer.write(WindowsCharts()._capture_local(sys.argv[1], int(sys.argv[2])))
    except Exception:
        sys.exit(1)  # No paths, account data or image bytes are written to stderr.
