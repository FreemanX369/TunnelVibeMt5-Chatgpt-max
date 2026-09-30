from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from vibemql5.core.live_terminal import LiveTerminal


class Inventory:
    def __init__(self, root: Path):
        self.terminal = SimpleNamespace(
            terminal_path=str(root / "MT5-2" / "terminal64.exe"),
            data_root=str(root / "MT5-2-DATA"),
        )

    def get(self, alias):
        assert alias == "MT5-2"
        return self.terminal

    def is_running(self, alias):
        return alias == "MT5-2"

    @staticmethod
    def _norm(value):
        return str(value).replace("/", "\\").lower().rstrip("\\")


class MT5:
    TIMEFRAME_M1 = 1
    COPY_TICKS_ALL = 0
    COPY_TICKS_INFO = 1
    COPY_TICKS_TRADE = 2

    def __init__(self, inventory):
        self.inventory = inventory
        self.shutdowns = 0
        self.rate_symbol = None
        self.tick_symbol = None
        self.terminal = SimpleNamespace(
            path=str(Path(inventory.terminal.terminal_path).parent),
            data_path=inventory.terminal.data_root,
            connected=True,
            build=6230,
        )
        self.symbol = SimpleNamespace(
            name="XAUUSDm",
            digits=3,
            point=0.001,
            trade_tick_size=0.001,
            trade_contract_size=100.0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            spread=25,
            spread_float=True,
            trade_mode=4,
            visible=True,
            select=True,
        )
        self.tick = SimpleNamespace(
            time=1790668800,
            time_msc=1790668800123,
            bid=4000.1,
            ask=4000.2,
            last=4000.15,
            volume=2,
            volume_real=2.0,
            flags=6,
        )

    def initialize(self, path, timeout):
        assert path == self.inventory.terminal.terminal_path
        assert timeout == 2000
        return True

    def terminal_info(self):
        return self.terminal

    def shutdown(self):
        self.shutdowns += 1

    def symbol_info(self, symbol):
        return self.symbol if symbol == "XAUUSDm" else None

    def symbol_info_tick(self, symbol):
        return self.tick if symbol == "XAUUSDm" else None

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        self.rate_symbol = symbol
        assert timeframe == self.TIMEFRAME_M1
        assert (start_pos, count) == (0, 2)
        return [
            {"time": 1790668740, "open": 3999.0, "high": 4000.0, "low": 3998.0, "close": 3999.5,
             "tick_volume": 10, "spread": 20, "real_volume": 0},
            {"time": 1790668800, "open": 3999.5, "high": 4000.3, "low": 3999.4, "close": 4000.1,
             "tick_volume": 5, "spread": 25, "real_volume": 0},
        ]

    def copy_ticks_from(self, symbol, start, count, flags):
        self.tick_symbol = symbol
        assert count == 2
        assert flags == self.COPY_TICKS_ALL
        return [
            {"time": 1790668800, "time_msc": 1790668800100, "bid": 4000.10, "ask": 4000.20,
             "last": 0.0, "volume": 0, "volume_real": 0.0, "flags": 2},
            {"time": 1790668800, "time_msc": 1790668800100, "bid": 4000.11, "ask": 4000.21,
             "last": 0.0, "volume": 0, "volume_real": 0.0, "flags": 2},
        ]

    def last_error(self):
        return (1, "fake")


def test_symbol_snapshot_requires_exact_symbol(tmp_path):
    inventory = Inventory(tmp_path)
    mt5 = MT5(inventory)
    live = LiveTerminal(inventory, "MT5-2", mt5=mt5)
    out = live.symbol_snapshot("XAUUSDm")
    assert out["symbol"]["name"] == "XAUUSDm"
    assert out["tick"]["bid"] == 4000.1
    assert out["terminal"]["build"] == 6230
    with pytest.raises(RuntimeError, match="MT5_SYMBOL_NOT_FOUND"):
        live.symbol_snapshot("XAUUSD247m")


def test_copy_rates_marks_only_newest_returned_current_bar_forming(tmp_path):
    inventory = Inventory(tmp_path)
    mt5 = MT5(inventory)
    out = LiveTerminal(inventory, "MT5-2", mt5=mt5).rates("XAUUSDm", "M1", 0, 2)
    assert mt5.rate_symbol == "XAUUSDm"
    assert out["returned_count"] == 2
    assert out["rates"][0]["bar_status"] == "CLOSED_OR_HISTORICAL"
    assert out["rates"][1]["bar_status"] == "FORMING"


def test_copy_ticks_preserves_same_millisecond_ticks(tmp_path):
    inventory = Inventory(tmp_path)
    mt5 = MT5(inventory)
    out = LiveTerminal(inventory, "MT5-2", mt5=mt5).ticks(
        "XAUUSDm", "2026-09-29T08:00:00Z", 2, "all"
    )
    assert mt5.tick_symbol == "XAUUSDm"
    assert out["returned_count"] == 2
    assert out["ticks"][0]["time_msc"] == out["ticks"][1]["time_msc"]
    assert out["ticks"][0]["bid"] != out["ticks"][1]["bid"]


def test_copy_ticks_rejects_naive_timestamp(tmp_path):
    inventory = Inventory(tmp_path)
    mt5 = MT5(inventory)
    with pytest.raises(ValueError, match="UTC_TIMESTAMP_TIMEZONE_REQUIRED"):
        LiveTerminal(inventory, "MT5-2", mt5=mt5).ticks(
            "XAUUSDm", "2026-09-29T08:00:00", 2, "all"
        )


@pytest.mark.parametrize("fraction,expected_count", [(".100", 1), (".100001", 0)])
def test_copy_ticks_filters_mt5_second_rounded_cursor_with_exact_inclusive_bound(tmp_path, monkeypatch, fraction, expected_count):
    inventory = Inventory(tmp_path)
    mt5 = MT5(inventory)
    original = mt5.copy_ticks_from("XAUUSDm", None, 2, mt5.COPY_TICKS_ALL)
    original[0]["time_msc"] -= 1
    monkeypatch.setattr(mt5, "copy_ticks_from", lambda *_args: original)
    out = LiveTerminal(inventory, "MT5-2", mt5=mt5).ticks(
        "XAUUSDm", f"2026-09-29T08:00:00{fraction}+00:00", 2, "all"
    )
    assert out["returned_count"] == expected_count
    assert out["filtered_before_from_utc"] == 2 - expected_count
    if expected_count:
        assert out["ticks"][0]["time_msc"] == 1790668800100
