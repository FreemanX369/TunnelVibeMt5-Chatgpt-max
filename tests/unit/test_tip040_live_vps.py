"""Optional isolated native acceptance; can be staged without changing production tools."""
from __future__ import annotations

import os
import struct

import pytest

from vibemql5.config import default_root
from vibemql5.core.concurrency import ConcurrencyManager
from vibemql5.core.inventory import TerminalInventory
from vibemql5.core.live_terminal import LiveTerminal
from vibemql5.core.live_terminal_windows import WindowsCharts


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
    with concurrency.native_execution("TIP040-LIVE-SMOKE", kind="read_only_acceptance", wait_seconds=2):
        live = LiveTerminal(inventory, "MT5-2", gui=WindowsCharts())
        state = live.state()
        assert state["terminal"]["alias"] == "MT5-2"
        assert state["terminal"]["ping_ms"] is None or state["terminal"]["ping_ms"] >= 0
        ea_files = live.ea_files()
        assert ea_files["status"] == "OK" and ea_files["executable_ex5_files"] >= 0
        charts = live.charts()
        assert charts["count"] > 0, "MT5-2 chart windows must be discoverable in the interactive session"
        visible = next((chart for chart in charts["charts"] if chart["visible"]), None)
        assert visible is not None, "MT5-2 must expose a visible chart for capture acceptance"
        meta, png = live.capture(visible["chart_id"])
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert struct.unpack(">II", png[16:24]) == (visible["width"], visible["height"])
        assert meta["bytes"] == len(png)
