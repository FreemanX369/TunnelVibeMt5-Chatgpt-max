"""Windows chart discovery and client-only capture, bound to one MT5 executable."""
from __future__ import annotations

import ctypes
import os
import re
import struct
import subprocess
import sys
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
        self.user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.IsWindowVisible.argtypes = [wintypes.HWND]
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
        charts: dict[int, dict] = {}

        @callback
        def child_cb(hwnd, _data):
            if not (match := _CHART_TITLE.match(self._title(hwnd))):
                return True
            if (self._path_for_hwnd(hwnd) or "").replace("/", "\\").casefold() != target:
                return True
            width, height = self._size(hwnd)
            if width < 32 or height < 32:
                return True
            charts[hwnd] = {"chart_id": hwnd, "symbol": match.group(1), "timeframe": match.group(2),
                            "visible": bool(self.user.IsWindowVisible(hwnd)), "width": width, "height": height,
                            "expert": {"attached": None, "status": "UNKNOWN"},
                            "indicators": {"status": "UNKNOWN"}}
            return True

        for main in mains:
            # Microsoft documents the EnumChildWindows BOOL return as unused.
            # A zero result does not prove enumeration failed; trust only validated callbacks.
            self.user.EnumChildWindows(main, child_cb, 0)
        if not charts:
            raise RuntimeError("LIVE_CHART_WINDOWS_NOT_VERIFIABLE")
        return sorted(charts.values(), key=lambda item: item["chart_id"])

    def capture_chart(self, terminal_exe: str, chart_id: int) -> bytes:
        """Run PrintWindow in a disposable process; terminate it after five seconds."""
        try:
            done = subprocess.run(
                [sys.executable, "-m", "vibemql5.core.live_terminal_windows", terminal_exe, str(chart_id)],
                capture_output=True, check=False, timeout=5,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("LIVE_CHART_CAPTURE_TIMEOUT") from exc
        if done.returncode or not done.stdout.startswith(b"\x89PNG\r\n\x1a\n") or len(done.stdout) > 8_000_000:
            raise RuntimeError("LIVE_CHART_CAPTURE_FAILED")
        return done.stdout

    def _capture_local(self, terminal_exe: str, chart_id: int) -> bytes:
        before = next((c for c in self.list_charts(terminal_exe) if c["chart_id"] == chart_id), None)
        if not before or not before["visible"]:
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
