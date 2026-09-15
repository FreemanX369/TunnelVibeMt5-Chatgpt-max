from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

_FATAL = [re.compile(p, re.I) for p in [
    r"critical error", r"fatal", r"access violation", r"cannot load expert",
    r"failed to load", r"not enough memory", r"tester stopped because",
]]
_ERROR = re.compile(r"\b(error|failed|invalid)\b", re.I)
_KNOWN = [
    ("TRADE_SERVER_NOT_SYNCHRONIZED", re.compile(r"not synchroni[sz]ed with (?:the )?trade server", re.I)),
    ("TESTER_NOT_STARTED", re.compile(r"tester (?:didn't|did not) start|tester not started", re.I)),
    ("SYMBOL_NOT_AVAILABLE", re.compile(r"cannot select symbol in market watch", re.I)),
    ("AUTHORIZATION_FAILED", re.compile(r"authorization .* failed|invalid account", re.I)),
]
_PROGRESS = re.compile(r"(?<!\d)(100|[0-9]{1,2})\s*%")
_NATIVE_TS_TEXT = r"20\d{2}[./-]\d{2}[./-]\d{2}\s+\d{2}:\d{2}(?::\d{2})?"
_NATIVE_TS = re.compile(rf"\b({_NATIVE_TS_TEXT})\b")
_TESTER_SELECTED = re.compile(rf"\btesting\s+of\s+.+?\s+from\s+({_NATIVE_TS_TEXT})\s+to\s+({_NATIVE_TS_TEXT})\s+started\b", re.I)
_SELECTED_PREFIX = re.compile(r"\b[^\s,:]+,(M\d+|H\d+|D1|W1|MN1)\s*:\s*testing\s+of\b", re.I)
_TESTER_STOP = re.compile(r"TesterStop\(\)\s+called\s+on\s+(100|[0-9]{1,2})(?:\.\d+)?%\s+of\s+testing\s+interval", re.I)
_STOP_OUT = re.compile(r"\bstop[ -]?out\b|\bstopped out\b", re.I)
_STOP_OUT_INTERVAL = re.compile(r"stop[ -]?out\s+occurred\s+on\s+(100|[0-9]{1,2})(?:\.([0-9]+))?%\s+of\s+testing\s+interval", re.I)
_NO_MONEY = re.compile(r"\[\s*no money\s*\]|\bno money\b|\bnot enough money\b", re.I)
_EXPERT_REMOVE = re.compile(r"\bExpertRemove\s*\(\s*\)|\bexpert\s+(?:was\s+)?removed\b", re.I)
_INIT_FAILED = re.compile(r"\binitiali[sz]ation\s+failed\b|\bOnInit\b.*\b(?:failed|non[- ]?zero|return(?:ed)?\s+code)\b|\bINIT_FAILED\b", re.I)
_TESTER_STOPPED = re.compile(r"\btester\s+stopped\s+because\b", re.I)
_DATA_ISSUES = [
    ("NO_DATA", re.compile(r"\bno\s+(?:history\s+)?data\b|\bno\s+ticks?\b", re.I)),
    ("HISTORY_SYNC_FAILED", re.compile(r"history.*(?:failed|cannot|could not).*synchron", re.I)),
    ("TICKS_SYNC_FAILED", re.compile(r"ticks?.*(?:failed|cannot|could not).*synchron", re.I)),
]
_NORMAL_FINISH = [
    re.compile(r"automatic testing finished", re.I),
    re.compile(r"\btest passed in\b", re.I),
    re.compile(r"\btest\s+.+?\s+thread finished\b", re.I),
    re.compile(r"\blast test passed with result\b.*\bsuccessfully finished\b", re.I),
]
_INFRA_COMPONENTS = {"tester", "history", "ticks", "network", "terminal", "core", "journal", "mail", "experts", "market", "signals", "virtual hosting", "mql5.community"}
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_CORE_EXECUTION_COMPONENT = re.compile(r"^core\s+\d+$", re.I)
_CORE_MODEL_TS_PREFIX = re.compile(rf"^\s*({_NATIVE_TS_TEXT})\b")


def detect_text_encoding(data: bytes) -> tuple[str, int]:
    if data.startswith(b"\xff\xfe"): return "utf-16-le", 2
    if data.startswith(b"\xfe\xff"): return "utf-16-be", 2
    sample = data[:2048]
    if b"\x00" in sample:
        even_nuls = sum(1 for i in range(0, len(sample), 2) if sample[i] == 0)
        odd_nuls = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
        if odd_nuls > even_nuls * 2: return "utf-16-le", 0
        if even_nuls > odd_nuls * 2: return "utf-16-be", 0
        return "utf-16-le", 0
    if data.startswith(b"\xef\xbb\xbf"): return "utf-8-sig", 3
    return "utf-8", 0


def decode_text_bytes(data: bytes) -> tuple[str, dict[str, Any]]:
    encoding, bom_bytes = detect_text_encoding(data)
    try:
        text = data.decode(encoding, errors="strict"); lossy = False; replacements = 0
    except UnicodeDecodeError:
        text = data.decode(encoding, errors="replace"); replacements = text.count("\ufffd"); lossy = replacements > 0
    if bom_bytes and text.startswith("\ufeff"): text = text[1:]
    return text, {"encoding": encoding, "bom_bytes": bom_bytes, "lossy": lossy, "replacement_characters": replacements, "raw_bytes": len(data)}


def read_text_auto(path: Path) -> str:
    if not path.exists(): return ""
    return decode_text_bytes(path.read_bytes())[0]


def _norm_ts(value: str) -> str | None:
    value = value.strip().replace("/", ".").replace("-", ".")
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try: return datetime.strptime(value, fmt).strftime("%Y.%m.%d %H:%M:%S")
        except ValueError: continue
    return None


def _split_native_line(raw: str) -> tuple[str, str]:
    parts = raw.rstrip("\r\n").split("\t")
    if len(parts) >= 5: return parts[3].strip(), "\t".join(parts[4:]).strip()
    return "", raw.strip()


def _is_tester_execution_component(component: str) -> bool:
    low = component.strip().lower(); return low == "tester" or bool(_CORE_EXECUTION_COMPONENT.fullmatch(low))


def _is_model_component(component: str) -> bool:
    low = component.strip().lower()
    if not low: return False
    if low in {"trade", "trades"}: return True
    if low in _INFRA_COMPONENTS or _CORE_EXECUTION_COMPONENT.fullmatch(low) or _IPV4.fullmatch(low): return False
    return True


def parse_native_execution_evidence(text: str) -> dict[str, Any]:
    selected_period=None; model_timestamps=[]; tester_stop_pct=None; stop_out_pct=None; termination=None; normal_finish_seen=False; end_of_test_close_seen=False; data_issues=[]
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith("====="): continue
        component,message=_split_native_line(raw); component_low=component.lower(); low=line.lower(); tester_execution_component=_is_tester_execution_component(component)
        if selected_period is None and tester_execution_component:
            match=_TESTER_SELECTED.search(message)
            if match:
                from_ts=_norm_ts(match.group(1)); to_ts=_norm_ts(match.group(2)); tf=_SELECTED_PREFIX.search(message)
                if from_ts and to_ts: selected_period={"status":"OBSERVED","from_date":from_ts[:10],"to_date":to_ts[:10],"from_timestamp":from_ts,"to_timestamp":to_ts,"timeframe":(tf.group(1).upper() if tf else None),"source_component":component,"source_line":line[-700:]}
        stop_match=_TESTER_STOP.search(message if component_low=="tester" else line)
        if stop_match:
            pct=int(stop_match.group(1)); tester_stop_pct=pct if tester_stop_pct is None else max(tester_stop_pct,pct)
            if pct<100: termination={"kind":"EARLY_TERMINATION","code":"TESTER_STOP_INTERVAL","testing_interval_pct":pct,"source_component":component or None,"message":line[-700:]}
        stop_out_match=_STOP_OUT_INTERVAL.search(message if component_low in {"tester","trade","trades"} else line)
        if stop_out_match:
            frac=stop_out_match.group(2) or ""; pct_value=float(stop_out_match.group(1)+("."+frac if frac else "")); stop_out_pct=pct_value if stop_out_pct is None else max(stop_out_pct,pct_value)
            if pct_value<100: termination={"kind":"EARLY_TERMINATION","code":"STOP_OUT","testing_interval_pct":pct_value,"source_component":component or None,"message":line[-700:]}
        native_reason_scope=component_low in {"tester","trade","trades"}
        if termination is None and native_reason_scope and _STOP_OUT.search(message): termination={"kind":"EARLY_TERMINATION","code":"STOP_OUT","source_component":component,"message":line[-700:]}
        if termination is None and component_low=="tester" and _TESTER_STOPPED.search(message): termination={"kind":"EARLY_TERMINATION","code":"TESTER_STOPPED_BECAUSE","source_component":component,"message":line[-700:]}
        if component_low in {"tester","history","ticks"}:
            for code,pattern in _DATA_ISSUES:
                if pattern.search(message) and not any(x["code"]==code for x in data_issues): data_issues.append({"code":code,"message":line[-700:]})
        if "position closed due end of test" in low: end_of_test_close_seen=True
        if any(pattern.search(line) for pattern in _NORMAL_FINISH): normal_finish_seen=True
        if _is_model_component(component):
            matches=list(_NATIVE_TS.finditer(message))
            if matches:
                ts=_norm_ts(matches[0].group(1))
                if ts: model_timestamps.append(ts)
        elif _CORE_EXECUTION_COMPONENT.fullmatch(component_low) and selected_period is not None:
            core_match=_CORE_MODEL_TS_PREFIX.match(message)
            if core_match:
                ts=_norm_ts(core_match.group(1))
                if ts:
                    try:
                        model_dt=datetime.strptime(ts,"%Y.%m.%d %H:%M:%S"); from_dt=datetime.strptime(selected_period["from_timestamp"],"%Y.%m.%d %H:%M:%S"); to_dt=datetime.strptime(selected_period["to_timestamp"],"%Y.%m.%d %H:%M:%S")
                    except (KeyError,TypeError,ValueError): pass
                    else:
                        if from_dt<=model_dt<=to_dt: model_timestamps.append(ts)
    last_model=max(model_timestamps) if model_timestamps else None
    if termination is None and normal_finish_seen: termination={"kind":"NORMAL_FINISH","code":"GENERIC_NATIVE_FINISH"}
    return {"selected_period":selected_period or {"status":"UNVERIFIED","from_date":None,"to_date":None},"last_model_timestamp":last_model,"model_timestamp_count":len(model_timestamps),"tester_stop_pct":tester_stop_pct,"stop_out_pct":stop_out_pct,"termination":termination,"normal_finish_seen":normal_finish_seen,"end_of_test_close_seen":end_of_test_close_seen,"data_issues":data_issues}

_MAX_STRUCTURED_EVENTS=500

def _event_model_time(component:str,message:str)->str|None:
    match=_NATIVE_TS.search(message)
    if not match:return None
    return _norm_ts(match.group(1))

def parse_structured_tester_events(text:str,execution_evidence:dict[str,Any]|None=None)->dict[str,Any]:
    evidence=dict(execution_evidence or parse_native_execution_evidence(text));events=[];counts={};seen=set()
    def emit(kind,raw,component,message,**extra):
        key=(kind,raw.strip())
        if key in seen:return
        seen.add(key);counts[kind]=counts.get(kind,0)+1
        if len(events)>=_MAX_STRUCTURED_EVENTS:return
        event={"kind":kind,"source_component":component or None,"message":raw.strip()[-700:],"model_time":_event_model_time(component,message)};event.update({k:v for k,v in extra.items() if v is not None});events.append(event)
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith("====="):continue
        component,message=_split_native_line(raw);low_component=component.lower();reason_scope=low_component in {"tester","trade","trades"} or _is_model_component(component)
        stop_out_interval=_STOP_OUT_INTERVAL.search(message if reason_scope else line)
        if stop_out_interval:
            frac=stop_out_interval.group(2) or "";pct=float(stop_out_interval.group(1)+("."+frac if frac else ""));emit("TESTER_STOP_OUT",raw,component,message,coverage_percent=pct)
        elif reason_scope and _STOP_OUT.search(message):emit("TESTER_STOP_OUT",raw,component,message,coverage_percent=evidence.get("stop_out_pct"))
        if _NO_MONEY.search(message if reason_scope else line):emit("NO_MONEY",raw,component,message)
        stop=_TESTER_STOP.search(message if low_component=="tester" else line)
        if stop:emit("TESTER_STOP",raw,component,message,coverage_percent=float(stop.group(1)))
        elif low_component=="tester" and _TESTER_STOPPED.search(message):emit("TESTER_STOP",raw,component,message)
        if _EXPERT_REMOVE.search(message if reason_scope else line):emit("EXPERT_REMOVE",raw,component,message)
        if _INIT_FAILED.search(message if reason_scope else line):emit("INIT_FAILED",raw,component,message)
        if "position closed due end of test" in line.lower():emit("END_OF_TEST",raw,component,message)
    termination=dict(evidence.get("termination") or {})
    if termination.get("kind")=="EARLY_TERMINATION":
        synthetic={"kind":"EARLY_END","source_component":termination.get("source_component"),"message":termination.get("message") or termination.get("code") or "Native tester ended before full selected-period proof","model_time":evidence.get("last_model_timestamp"),"termination_reason":termination.get("code"),"coverage_percent":termination.get("testing_interval_pct")};counts["EARLY_END"]=counts.get("EARLY_END",0)+1
        if len(events)<_MAX_STRUCTURED_EVENTS:events.append(synthetic)
    elif evidence.get("normal_finish_seen") and not any(x.get("kind")=="END_OF_TEST" for x in events):
        counts["END_OF_TEST"]=counts.get("END_OF_TEST",0)+1
        if len(events)<_MAX_STRUCTURED_EVENTS:events.append({"kind":"END_OF_TEST","source_component":None,"message":"Native tester normal finish observed","model_time":evidence.get("last_model_timestamp")})
    total=sum(counts.values());return {"schema_version":"1.0","events":events,"counts":dict(sorted(counts.items())),"total_events":total,"truncated":total>len(events),"max_events":_MAX_STRUCTURED_EVENTS}


def parse_tester_text(text:str)->dict:
    events=[];fatals=[];diagnostics=[];seen_codes=set();started=False;finished=False;passed=False;max_progress=None
    for raw in text.splitlines():
        line=raw.strip()
        if not line:continue
        low=line.lower()
        if "automatic testing started" in low or ("testing of" in low and " started" in low):started=True
        if "automatic testing finished" in low or ("test " in low and " thread finished" in low) or ("last test passed with result" in low and "successfully finished" in low):finished=True
        if "test passed in" in low or ("last test passed with result" in low and "successfully finished" in low):passed=True
        for match in _PROGRESS.finditer(line):
            value=int(match.group(1));max_progress=value if max_progress is None else max(max_progress,value)
        for code,pattern in _KNOWN:
            if pattern.search(line) and code not in seen_codes:seen_codes.add(code);diagnostics.append({"code":code,"message":line})
        if any(p.search(line) for p in _FATAL):fatals.append(line);events.append({"severity":"fatal","message":line})
        elif _ERROR.search(line):events.append({"severity":"error","message":line})
    if passed and not fatals:native_status="PASSED"
    elif started and not finished:native_status="STARTED_NOT_FINISHED"
    elif fatals:native_status="FAILED"
    else:native_status="UNKNOWN"
    execution_evidence=parse_native_execution_evidence(text)
    return {"fatal_errors":fatals,"events":events,"diagnostics":diagnostics,"native_test_started":started,"native_test_finished":finished,"native_test_passed":passed and not fatals,"native_test_status":native_status,"progress_pct":max_progress,"execution_evidence":execution_evidence,"structured_events":parse_structured_tester_events(text,execution_evidence)}


def parse_tester_log(path:Path)->dict:
    if path.exists():raw=path.read_bytes();text,decoding=decode_text_bytes(raw)
    else:text,decoding="",{"encoding":None,"lossy":False,"replacement_characters":0,"raw_bytes":0}
    out=parse_tester_text(text);out["log_path"]=str(path);out["decoding"]=decoding;return out
