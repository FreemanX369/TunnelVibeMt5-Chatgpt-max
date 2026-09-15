from __future__ import annotations
import html, json, re, xml.etree.ElementTree as ET
from pathlib import Path

KEYS = {
    "history_quality_pct": ["history quality"],
    "bars": ["bars"],
    "ticks": ["ticks"],
    "symbols": ["symbols"],
    "trades": ["total trades", "trades"],
    "deals": ["total deals", "deals"],
    "net_profit": ["total net profit", "net profit"],
    "gross_profit": ["gross profit"],
    "gross_loss": ["gross loss"],
    "profit_factor": ["profit factor"],
    "expected_payoff": ["expected payoff"],
    "recovery_factor": ["recovery factor"],
    "sharpe_ratio": ["sharpe ratio"],
    "max_drawdown_pct": ["balance drawdown maximal", "equity drawdown maximal", "maximal drawdown", "max drawdown"],
}

def _read_auto(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe"): return data.decode("utf-16-le", errors="replace")
    if data.startswith(b"\xfe\xff"): return data.decode("utf-16-be", errors="replace")
    if b"\x00" in data[:400]:
        try: return data.decode("utf-16-le", errors="replace")
        except Exception: pass
    return data.decode("utf-8-sig", errors="replace")

def _clean(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip()

def _num(value: str):
    s = _clean(value); pct = "%" in s
    m_pct = re.search(r"\(([-+]?\d+(?:[.,]\d+)?)%\)", s)
    if m_pct: return float(m_pct.group(1).replace(",", "."))
    if pct:
        m_direct_pct = re.search(r"([-+]?\d+(?:[.,]\d+)?)\s*%", s)
        if m_direct_pct: return float(m_direct_pct.group(1).replace(",", "."))
    m = re.search(r"[-+]?\d[\d\s]*(?:[.,]\d+)?", s)
    if not m: return None
    token = m.group(0).replace(" ", "")
    if token.count(",") == 1 and "." not in token: token = token.replace(",", ".")
    else: token = token.replace(",", "")
    try:
        n = float(token); return int(n) if n.is_integer() and not pct else n
    except ValueError: return None

def _xml_payload(path: Path) -> tuple[list[tuple[str,str]], dict]:
    raw = _read_auto(path)
    root = ET.fromstring(raw)
    if root.tag.split("}")[-1] == "vibemql5_backtest_report":
        metrics = {}
        metrics_el = root.find("metrics")
        if metrics_el is not None:
            for item in metrics_el.findall("metric"):
                name = str(item.attrib.get("name") or "").strip()
                if name:
                    metrics[name] = _num(item.text or "")
        provenance = {
            "source_kind": root.attrib.get("source_kind"),
            "schema_version": root.attrib.get("schema_version"),
        }
        prov_el = root.find("provenance")
        if prov_el is not None:
            native = prov_el.find("native_report")
            if native is not None:
                provenance["native_report"] = {
                    "path": native.attrib.get("path"),
                    "sha256": native.attrib.get("sha256"),
                    "bytes": int(native.attrib.get("bytes") or 0),
                }
            generated = prov_el.find("generated_at_utc")
            if generated is not None:
                provenance["generated_at_utc"] = _clean(generated.text or "")
        return [], {"metrics": metrics, "provenance": provenance}
    texts = [_clean(x.text or "") for x in root.iter() if _clean(x.text or "")]
    return list(zip(texts, texts[1:])), {}

def _pairs_from_xml(path: Path) -> list[tuple[str,str]]:
    return _xml_payload(path)[0]

def _pairs_from_html(path: Path) -> list[tuple[str,str]]:
    text = _read_auto(path)
    cells = [_clean(x) for x in re.findall(r"<(?:td|th)[^>]*>(.*?)</(?:td|th)>", text, re.I|re.S)]
    cells = [x for x in cells if x]
    return list(zip(cells, cells[1:]))

def parse_report(path: Path) -> dict:
    if not path.exists(): return {"status":"MISSING", "metrics":{}, "report_path":str(path)}
    if path.suffix.lower() == ".json":
        data = json.loads(_read_auto(path)); return {"status":"PARSED", "metrics":data.get("strategy", data), "report_path":str(path)}
    try:
        if path.suffix.lower() == ".xml":
            pairs, special = _xml_payload(path)
            if special:
                metrics = special.get("metrics") or {}
                return {
                    "status": "PARSED" if metrics else "PARSE_ERROR",
                    "metrics": metrics,
                    "provenance": special.get("provenance") or {},
                    "report_path": str(path),
                }
        else:
            pairs = _pairs_from_html(path)
    except Exception as exc:
        return {"status":"PARSE_ERROR", "metrics":{}, "report_path":str(path), "error":str(exc)}
    metrics = {}
    for label, value in pairs:
        low = _clean(label).lower().rstrip(":")
        for key, labels in KEYS.items():
            if key in metrics: continue
            if any(x == low or x in low for x in labels):
                n = _num(value)
                if n is not None: metrics[key] = n
    return {"status":"PARSED" if metrics else "PARSE_ERROR", "metrics":metrics, "report_path":str(path)}
