from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import load_preset
from ..contracts import EXECUTION_MODE_MAX_DELAY_MS, EXECUTION_MODE_RANDOM

_ALLOWED = {
    "symbol", "period", "model", "from_date", "to_date", "deposit",
    "currency", "leverage", "visual", "execution_delay_ms",
}
_DATE_FMT = "%Y.%m.%d"


def _ini_bool(v: Any) -> str:
    return "1" if bool(v) else "0"


def _leverage(v: Any) -> str:
    s = str(v).strip()
    return s if ":" in s else f"1:{s}"


def _parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be YYYY.MM.DD")
    try:
        return datetime.strptime(value.strip(), _DATE_FMT).date()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY.MM.DD") from exc


def _validate_leverage(value: Any) -> None:
    text = str(value).strip()
    if not text:
        raise ValueError("leverage must be positive")
    if ":" in text:
        left, right = text.split(":", 1)
        try:
            numerator = int(left)
            denominator = int(right)
        except ValueError as exc:
            raise ValueError("leverage must be N or A:B using positive integers") from exc
        if numerator <= 0 or denominator <= 0:
            raise ValueError("leverage must be positive")
    else:
        try:
            if int(text) <= 0:
                raise ValueError
        except ValueError as exc:
            raise ValueError("leverage must be a positive integer or A:B") from exc


def _validate_boolish(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value in (0, 1):
        return bool(value)
    raise ValueError(f"{field} must be boolean or 0/1")


def _validate_execution_delay(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("execution_delay_ms must be an integer")
    if value < EXECUTION_MODE_RANDOM or value > EXECUTION_MODE_MAX_DELAY_MS:
        raise ValueError(
            "execution_delay_ms must be -1 (MT5 random delay) or 0..600000 milliseconds"
        )
    return int(value)


def normalize_tester_request(
    root: Path,
    preset_name: str,
    overrides: dict | None = None,
    *,
    today: date | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Purely validate and normalize one tester request before side effects.

    D-021R-01: execution_delay_ms maps 1:1 to MT5 [Tester] ExecutionMode:
      -1 random delay, 0 no delay, 1..600000 fixed milliseconds.
    D-021R-02: a requested future to_date is preserved as evidence but the
    effective native ToDate is clamped to the host's current date.
    """
    preset = dict(load_preset(preset_name, root))
    overrides = dict(overrides or {})
    unknown = sorted(set(overrides) - _ALLOWED)
    if unknown:
        raise ValueError(f"Unsupported tester overrides: {unknown}")
    preset.update(overrides)

    effective_today = today or date.today()
    if not preset.get("from_date"):
        preset["from_date"] = (effective_today - timedelta(days=14)).strftime(_DATE_FMT)
    if not preset.get("to_date"):
        preset["to_date"] = effective_today.strftime(_DATE_FMT)

    for field in ("symbol", "period", "currency"):
        value = preset.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
        preset[field] = value.strip()

    model = preset.get("model")
    if isinstance(model, bool) or not isinstance(model, int) or model not in {0, 1, 2, 3, 4}:
        raise ValueError("model must be one of 0,1,2,3,4")

    deposit = preset.get("deposit")
    if isinstance(deposit, bool) or not isinstance(deposit, (int, float)) or float(deposit) <= 0:
        raise ValueError("deposit must be a positive number")

    _validate_leverage(preset.get("leverage"))
    preset["visual"] = _validate_boolish(preset.get("visual", False), "visual")

    requested_from = str(preset["from_date"]).strip()
    requested_to = str(preset["to_date"]).strip()
    from_date = _parse_date(requested_from, "from_date")
    to_date = _parse_date(requested_to, "to_date")
    effective_to = min(to_date, effective_today)
    if from_date > effective_to:
        raise ValueError(
            "from_date must not be after the effective to_date/current date"
        )
    preset["from_date"] = from_date.strftime(_DATE_FMT)
    preset["to_date"] = effective_to.strftime(_DATE_FMT)

    delay_present = "execution_delay_ms" in preset
    if delay_present:
        preset["execution_delay_ms"] = _validate_execution_delay(preset["execution_delay_ms"])

    normalization = {
        "requested_period": {
            "from_date": requested_from,
            "to_date": requested_to,
        },
        "effective_period": {
            "from_date": preset["from_date"],
            "to_date": preset["to_date"],
        },
        "current_date": effective_today.strftime(_DATE_FMT),
        "future_to_date_clamped": bool(to_date > effective_today),
        "execution_delay": {
            "specified": delay_present,
            "execution_mode": preset.get("execution_delay_ms") if delay_present else None,
            "mode": (
                "RANDOM" if preset.get("execution_delay_ms") == -1 else
                "NO_DELAY" if preset.get("execution_delay_ms") == 0 else
                "FIXED_MS" if delay_present else
                "TERMINAL_DEFAULT"
            ),
        },
    }
    return preset, normalization


def render_tester_ini(
    root: Path,
    run_dir: Path,
    expert_name: str,
    preset_name: str,
    set_file: str | None = None,
    overrides: dict | None = None,
    report_path: Path | None = None,
    report_value: str | None = None,
    shutdown_terminal: bool = False,
    tester_login: int | None = None,
    *,
    resolved_config: dict[str, Any] | None = None,
) -> tuple[Path, dict]:
    if resolved_config is None:
        preset, _ = normalize_tester_request(root, preset_name, overrides)
    else:
        # The worker performs this validation before compile/handoff. Keep this
        # render path side-effect free with respect to request semantics.
        preset = dict(resolved_config)

    if report_value is None:
        report_value = str(Path(report_path or (run_dir / "report")))
    lines = [
        "[Tester]",
        f"Expert={expert_name}",
        f"Symbol={preset['symbol']}",
        f"Period={preset['period']}",
        f"Model={preset['model']}",
    ]
    if "execution_delay_ms" in preset:
        lines.append(f"ExecutionMode={int(preset['execution_delay_ms'])}")
    lines.extend([
        "Optimization=0",
        f"FromDate={preset['from_date']}",
        f"ToDate={preset['to_date']}",
        "ForwardMode=0",
        f"Deposit={preset['deposit']}",
        f"Currency={preset['currency']}",
        f"Leverage={_leverage(preset['leverage'])}",
        f"Report={report_value}",
        "ReplaceReport=1",
        f"ShutdownTerminal={_ini_bool(shutdown_terminal)}",
        "UseLocal=1",
        "UseRemote=0",
        "UseCloud=0",
        f"Visual={_ini_bool(preset.get('visual', False))}",
    ])
    insert_at = 2
    if set_file:
        lines.insert(insert_at, f"ExpertParameters={set_file}")
        insert_at += 1
    if tester_login:
        lines.insert(insert_at, f"Login={int(tester_login)}")
    path = run_dir / "tester.ini"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, preset
