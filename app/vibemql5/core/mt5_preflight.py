from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Any


def _name(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    return str(getattr(obj, "name", ""))


def choose_symbol(requested: str, symbols: Iterable[Any]) -> str | None:
    req = requested.strip()
    if not req:
        return None
    req_u = req.upper()
    items = [s for s in symbols if _name(s)]
    if not items:
        return None
    for s in items:
        if _name(s) == req:
            return _name(s)
    for s in items:
        if _name(s).upper() == req_u:
            return _name(s)
    scored: list[tuple[int, int, str]] = []
    for s in items:
        n = _name(s)
        nu = n.upper()
        visible = bool(getattr(s, "visible", False))
        selected = bool(getattr(s, "select", False))
        bonus = (20 if selected else 0) + (10 if visible else 0)
        if nu.startswith(req_u):
            score = 800 + bonus; extra = len(n) - len(req)
        elif nu.endswith(req_u):
            score = 700 + bonus; extra = len(n) - len(req)
        elif req_u in nu:
            score = 600 + bonus; extra = len(n) - len(req)
        else:
            continue
        scored.append((score, -max(0, extra), n))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][2]


@dataclass
class MT5Preflight:
    terminal_path: str

    def probe(self, requested_symbol: str, timeout_ms: int = 10000) -> dict:
        try:
            import MetaTrader5 as mt5  # type: ignore
        except Exception as exc:
            return {"ok": False, "code": "METATRADER5_PYTHON_PACKAGE_UNAVAILABLE", "message": str(exc), "connected": False, "resolved_symbol": None}
        initialized = False
        try:
            initialized = bool(mt5.initialize(self.terminal_path, timeout=timeout_ms))
            if not initialized:
                return {"ok": False, "code": "MT5_IPC_INITIALIZE_FAILED", "message": repr(mt5.last_error()), "connected": False, "resolved_symbol": None, "package_version": getattr(mt5, "__version__", None)}
            ti = mt5.terminal_info(); ai = mt5.account_info(); connected = bool(ti and getattr(ti, "connected", False))
            candidates = mt5.symbols_get(group=f"*{requested_symbol}*") or ()
            resolved = choose_symbol(requested_symbol, candidates)
            if resolved and connected:
                try: mt5.symbol_select(resolved, True)
                except Exception: pass
            return {"ok": connected and ai is not None, "code": "READY" if connected and ai is not None else "TERMINAL_NOT_CONNECTED", "connected": connected, "account_present": ai is not None, "resolved_symbol": resolved, "symbol_candidates": [_name(x) for x in candidates[:20]], "package_version": getattr(mt5, "__version__", None), "build": int(getattr(ti, "build", 0)) if ti is not None else None, "trade_allowed": bool(getattr(ti, "trade_allowed", False)) if ti is not None else None, "_login": int(getattr(ai, "login", 0)) if ai is not None else None, "_server": str(getattr(ai, "server", "")) if ai is not None else None}
        finally:
            if initialized:
                try: mt5.shutdown()
                except Exception: pass


def public_preflight(data: dict | None) -> dict | None:
    if data is None:
        return None
    return {k: v for k, v in data.items() if not k.startswith("_")}
