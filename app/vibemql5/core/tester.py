from __future__ import annotations
import ctypes, hashlib, json, os, shutil, subprocess, time
from pathlib import Path
from typing import Callable
from .inventory import TerminalInventory
from .workspace import WorkspaceManager
from .tester_config import render_tester_ini
from .release import write_normalized_report_xml
from ..config import default_root
from ..parsers.report import parse_report
from ..parsers.tester_log import parse_tester_log, detect_text_encoding, parse_native_execution_evidence


class TesterDriver:
    @staticmethod
    def _timeframe_tolerance_seconds(timeframe: str | None) -> int:
        tf = str(timeframe or "").upper()
        if tf.startswith("M") and tf[1:].isdigit(): return max(1, int(tf[1:])) * 60
        if tf.startswith("H") and tf[1:].isdigit(): return max(1, int(tf[1:])) * 3600
        if tf == "D1": return 86400
        if tf == "W1": return 7 * 86400
        if tf == "MN1": return 31 * 86400
        return 1

    @staticmethod
    def _capture_integrity(logs: dict, log_receipts: list[dict] | None) -> dict:
        reasons=[]; decoding=dict(logs.get("decoding") or {})
        if int(decoding.get("raw_bytes") or 0)<=0: reasons.append("NATIVE_LOG_MISSING_OR_EMPTY")
        if bool(decoding.get("lossy")) or int(decoding.get("replacement_characters") or 0)>0: reasons.append("NATIVE_LOG_LOSSY_DECODE")
        receipts=list(log_receipts or [])
        if any(bool(r.get("lossy")) for r in receipts): reasons.append("SOURCE_CAPTURE_LOSSY_DECODE")
        if any(bool(r.get("truncated_or_rotated")) for r in receipts): reasons.append("SOURCE_LOG_TRUNCATED_OR_ROTATED")
        latest_by_source={}
        for receipt in receipts:
            source=str(receipt.get("source_id") or receipt.get("source") or "")
            if source: latest_by_source[source]=receipt
        if any(int(r.get("trailing_bytes_deferred") or 0)>0 for r in latest_by_source.values()): reasons.append("SOURCE_CAPTURE_TRAILING_BYTES_DEFERRED")
        return {"status":"PASS" if not reasons else "UNVERIFIED","reasons":sorted(set(reasons))}

    @staticmethod
    def _classify_executed_coverage(*, logs: dict, effective_period: dict, native_period: dict, completion_reason: str | None, timed_out: bool, log_receipts: list[dict] | None = None) -> dict:
        from datetime import datetime, timedelta
        evidence=dict(logs.get("execution_evidence") or {}) or parse_native_execution_evidence("")
        capture=TesterDriver._capture_integrity(logs,log_receipts)
        base={"from_date":native_period.get("from_date"),"to_date":native_period.get("to_date"),"effective_period":dict(effective_period or {}),"native_last_model_timestamp":evidence.get("last_model_timestamp"),"native_termination":evidence.get("termination"),"native_tester_stop_pct":evidence.get("tester_stop_pct"),"native_data_issues":list(evidence.get("data_issues") or []),"capture_integrity":capture}
        if completion_reason=="CANCEL_REQUESTED": return {**base,"status":"CANCELLED","basis":"explicit_cancel_observed_before_native_finish"}
        if timed_out or completion_reason=="EXPLICIT_OPERATOR_TIMEOUT": return {**base,"status":"TIMEOUT","basis":"explicit_operator_timeout"}
        term=dict(evidence.get("termination") or {})
        if term.get("kind")=="EARLY_TERMINATION": return {**base,"status":"EARLY_TERMINATION","basis":"native_termination_reason"}
        period_ok=native_period.get("status")=="OBSERVED" and native_period.get("from_date")==effective_period.get("from_date") and native_period.get("to_date")==effective_period.get("to_date")
        if not period_ok: return {**base,"status":"UNVERIFIED","basis":"native_selected_period_not_conformant"}
        if capture.get("status")!="PASS": return {**base,"status":"UNVERIFIED","basis":"native_log_capture_integrity_unverified"}
        if evidence.get("data_issues"): return {**base,"status":"UNVERIFIED","basis":"native_data_coverage_issue"}
        if not logs.get("native_test_finished") or not evidence.get("normal_finish_seen"): return {**base,"status":"UNVERIFIED","basis":"generic_native_finish_not_observed"}
        if int(evidence.get("tester_stop_pct") or -1)==100: return {**base,"status":"COMPLETED_SELECTED_PERIOD","basis":"native_tester_stop_100pct"}
        last_model=evidence.get("last_model_timestamp"); selected_to=native_period.get("to_timestamp")
        if not last_model or not selected_to: return {**base,"status":"UNVERIFIED","basis":"native_model_boundary_evidence_missing"}
        try: model_dt=datetime.strptime(str(last_model),"%Y.%m.%d %H:%M:%S"); selected_to_dt=datetime.strptime(str(selected_to),"%Y.%m.%d %H:%M:%S")
        except ValueError: return {**base,"status":"UNVERIFIED","basis":"native_model_boundary_timestamp_invalid"}
        tolerance_seconds=TesterDriver._timeframe_tolerance_seconds(native_period.get("timeframe")); threshold=selected_to_dt-timedelta(seconds=tolerance_seconds); base["boundary_tolerance_seconds"]=tolerance_seconds; base["native_selected_to_timestamp"]=selected_to
        if model_dt>=threshold: return {**base,"status":"COMPLETED_SELECTED_PERIOD","basis":"native_model_timestamp_reached_selected_end_boundary"}
        return {**base,"status":"UNVERIFIED","basis":"native_last_model_before_selected_end_without_termination_reason"}

    def __init__(self, root: Path | None = None):
        self.root=Path(root or default_root()); self.inventory=TerminalInventory(self.root); self.workspace=WorkspaceManager(self.root)

    def _copy_set(self, workspace:str, set_rel:str|None, terminal_alias:str, job_id:str)->str|None:
        if not set_rel:return None
        src=self.workspace.resolve(workspace,set_rel,must_exist=True);t=self.inventory.get(terminal_alias);name=f"VibeMQL5-{job_id}.set";destinations=[Path(t.terminal_path).parent/"MQL5"/"Profiles"/"Tester"/name,Path(t.data_root)/"MQL5"/"Profiles"/"Tester"/name];copied=False
        for dst in destinations:
            try: dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);copied=True
            except OSError: pass
        if not copied: raise OSError("Could not deploy ExpertParameters .set to terminal tester profile")
        return name

    def _log_files(self,terminal_alias:str)->list[Path]:
        t=self.inventory.get(terminal_alias);bases=[Path(t.data_root)/"Tester"/"logs",Path(t.data_root)/"Logs",Path(t.terminal_path).parent/"Tester"/"logs",Path(t.terminal_path).parent/"Logs"];files=[]
        for base in bases:
            if base.exists(): files.extend(base.glob("*.log"))
        return sorted(set(files),key=lambda x:str(x).lower())

    def _snapshot_log_lengths(self,terminal_alias:str)->dict[str,int]:
        snap={}
        for p in self._log_files(terminal_alias):
            try:snap[str(p)]=int(p.stat().st_size)
            except OSError:pass
        return snap

    @staticmethod
    def _decode_delta(full_data:bytes,start:int)->tuple[str,dict]:
        encoding,_=detect_text_encoding(full_data);chunk=full_data[start:];candidate=chunk
        if encoding in {"utf-16-le","utf-16-be"} and len(candidate)%2:candidate=candidate[:-1]
        lossy=False;replacements=0;text="";consumed=len(candidate)
        try:text=candidate.decode(encoding,errors="strict")
        except UnicodeDecodeError as exc:
            recovered=False
            if encoding in {"utf-8","utf-8-sig"} and exc.end>=max(0,len(candidate)-4):
                for deferred in range(1,min(4,len(candidate))+1):
                    trial=candidate[:-deferred]
                    try:text=trial.decode(encoding,errors="strict");candidate=trial;consumed=len(candidate);recovered=True;break
                    except UnicodeDecodeError:continue
            if not recovered:text=candidate.decode(encoding,errors="replace");replacements=text.count("\ufffd");lossy=replacements>0;consumed=len(candidate)
        if start==0 and text.startswith("\ufeff"):text=text[1:]
        return text,{"encoding":encoding,"lossy":lossy,"replacement_characters":replacements,"consumed_bytes":consumed,"trailing_bytes_deferred":len(chunk)-consumed}

    def _capture_log_deltas(self,terminal_alias:str,run_dir:Path,cursors:dict[str,int],*,since:float)->tuple[bool,list[dict]]:
        run_dir.mkdir(parents=True,exist_ok=True);normalized=run_dir/"tester.log";changed=False;receipts=[]
        for path in self._log_files(terminal_alias):
            key=str(path)
            try:st=path.stat()
            except OSError:continue
            if st.st_mtime<since-3 and key not in cursors:continue
            try:data=path.read_bytes()
            except OSError:continue
            previous=int(cursors.get(key,0));truncated=len(data)<previous
            if truncated:previous=0
            if len(data)<=previous:cursors[key]=len(data);continue
            text,decoding=self._decode_delta(data,previous);consumed=int(decoding.get("consumed_bytes",0));end_offset=previous+consumed
            if end_offset<=previous:continue
            source_id=hashlib.sha256(key.lower().encode("utf-8","replace")).hexdigest()[:16];raw_path=run_dir/f"tester-log-{source_id}.bin"
            with raw_path.open("ab") as raw_out:raw_out.write(data[previous:end_offset])
            with normalized.open("a",encoding="utf-8",errors="strict") as out:
                out.write(f"===== {path} bytes {previous}:{end_offset} =====\n");out.write(text)
                if text and not text.endswith("\n"):out.write("\n")
            cursors[key]=end_offset;changed=True;raw=raw_path.read_bytes();receipts.append({"source":key,"source_id":source_id,"start_offset":previous,"end_offset":end_offset,"truncated_or_rotated":truncated,"capture_path":raw_path.name,"captured_bytes":len(raw),"captured_sha256":hashlib.sha256(raw).hexdigest(),**decoding})
        (run_dir/"tester-log-cursor.json").write_text(json.dumps({"schema_version":"1.0","captured_at_unix":time.time(),"sources":receipts,"cursors":cursors},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        return changed,receipts

    def _collect_logs_since(self,terminal_alias:str,since:float,run_dir:Path,snapshot:dict[str,int]|None=None)->Path:
        cursors=dict(snapshot or {});self._capture_log_deltas(terminal_alias,run_dir,cursors,since=since);out=run_dir/"tester.log"
        if not out.exists():out.write_text("",encoding="utf-8")
        return out

    @staticmethod
    def _usable_file(p:Path)->bool:
        try:return p.exists() and p.is_file() and p.stat().st_size>0
        except OSError:return False

    @staticmethod
    def _execution_context()->dict:
        out={"pid":os.getpid(),"session_id":None,"interactive_session":None}
        if os.name!="nt":return out
        try:
            sid=ctypes.c_ulong();ok=ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(),ctypes.byref(sid))
            if ok:out["session_id"]=int(sid.value);out["interactive_session"]=int(sid.value)!=0
        except Exception as exc:out["session_error"]=str(exc)
        return out

    @staticmethod
    def _report_candidates(install_dir:Path,data_root:Path,job_id:str)->list[Path]:
        stem=f"VibeMQL5-{job_id}";legacy_rel=Path("VibeMQL5Reports")/job_id/"report.htm";names=[f"{stem}.htm",f"{stem}.html",f"{stem}.htm.htm"];out=[install_dir/names[0],data_root/names[0]]
        for root in (install_dir,data_root):out.extend(root/name for name in names[1:]);out.extend((root/"Reports"/name) for name in names)
        out.extend([install_dir/legacy_rel,data_root/legacy_rel]);return out

    @classmethod
    def _find_report(cls,exact_candidates:list[Path],started_wall:float)->Path|None:
        for p in exact_candidates:
            if cls._usable_file(p):
                try:
                    if p.stat().st_mtime>=started_wall-3:return p
                except OSError:pass
        if not exact_candidates:return None
        stem=exact_candidates[0].name
        for suffix in (".htm.htm",".html",".htm"):
            if stem.lower().endswith(suffix):stem=stem[:-len(suffix)];break
        dirs=[];seen=set()
        for p in exact_candidates:
            parent=p.parent;key=str(parent).lower()
            if key not in seen:seen.add(key);dirs.append(parent)
        matches=[]
        for d in dirs:
            try:
                if not d.exists():continue
                for p in d.glob(stem+"*"):
                    if cls._usable_file(p):
                        try:
                            if p.stat().st_mtime>=started_wall-3:matches.append(p)
                        except OSError:pass
            except OSError:pass
        if not matches:return None
        matches.sort(key=lambda p:p.stat().st_mtime,reverse=True);return matches[0]

    @classmethod
    def _report_scan(cls,exact_candidates:list[Path],started_wall:float)->list[dict]:
        out=[];seen=set()
        for p in exact_candidates:
            parent=p.parent;key=str(parent).lower()
            if key in seen or not parent.exists():continue
            seen.add(key)
            try:
                for item in parent.iterdir():
                    if not item.is_file():continue
                    low=item.name.lower()
                    if "vibemql5" not in low and "report" not in low:continue
                    st=item.stat();out.append({"path":str(item),"size":int(st.st_size),"mtime":float(st.st_mtime),"new_for_job":bool(st.st_mtime>=started_wall-3)})
            except OSError:pass
        out.sort(key=lambda x:x["mtime"],reverse=True);return out[:40]

    @staticmethod
    def _prepare_report_targets(candidates:list[Path])->None:
        for p in candidates:
            try:p.parent.mkdir(parents=True,exist_ok=True);p.exists() and p.unlink()
            except OSError:pass

    @staticmethod
    def _copy_report(actual_report:Path,run_dir:Path)->Path:
        name="report.native.xml" if actual_report.suffix.lower()==".xml" else "report.htm";captured=run_dir/name;shutil.copy2(actual_report,captured);return captured

    @staticmethod
    def _extract_native_period(text:str)->dict:
        return dict(parse_native_execution_evidence(text).get("selected_period") or {"status":"UNVERIFIED","from_date":None,"to_date":None})

    @staticmethod
    def _native_period_from_parsed_logs(logs:dict)->dict:
        evidence=dict(logs.get("execution_evidence") or {});return dict(evidence.get("selected_period") or {"status":"UNVERIFIED","from_date":None,"to_date":None})

    def run(self,job_id:str,workspace:str,source_rel:str,terminal_alias:str,expert_name:str,preset:str,run_dir:Path,set_rel:str|None=None,overrides:dict|None=None,timeout:int=0,mock:bool=False,on_pid:Callable[[int],None]|None=None,login:int|None=None,on_event:Callable[[str,dict],None]|None=None,resolved_config:dict|None=None,request_normalization:dict|None=None,should_cancel:Callable[[],bool]|None=None)->dict:
        run_dir.mkdir(parents=True,exist_ok=True);started_wall=time.time();started=time.monotonic();request_normalization=dict(request_normalization or {});emitted=set()
        def emit(kind,payload=None,*,once_key=None):
            key=once_key or ""
            if key and key in emitted:return
            if key:emitted.add(key)
            if on_event:on_event(kind,dict(payload or {}))
        if mock:
            ini,resolved=render_tester_ini(self.root,run_dir,expert_name,preset,set_rel,overrides,report_path=run_dir/"report.json",resolved_config=resolved_config);report={"strategy":{"trades":27,"net_profit":421.31,"profit_factor":1.31,"max_drawdown_pct":4.8}};(run_dir/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8");(run_dir/"tester.log").write_text("VibeMQL5 mock tester completed successfully\n",encoding="utf-8");parsed=parse_report(run_dir/"report.json");logs=parse_tester_log(run_dir/"tester.log");emit("TESTER_NATIVE_FINISHED",{"mock":True},once_key="finished");return {"status":"COMPLETED","execution_status":"PASSED","report_status":"PARSED","duration_seconds":round(time.monotonic()-started,3),"process_exit_code":0,"report":parsed,"logs":logs,"preset":resolved,"tester_ini":str(ini),"mock":True,"diagnostics":[],"request_normalization":request_normalization,"native_selected_period":{"status":"MOCK",**(request_normalization.get("effective_period") or {})},"period_conformance":{"status":"PASS","basis":"mock_effective_period"},"executed_coverage":{"status":"MOCK_COMPLETED"},"completion_reason":"MOCK_COMPLETED"}
        t=self.inventory.get(terminal_alias);set_name=self._copy_set(workspace,set_rel,terminal_alias,job_id);install_dir=Path(t.terminal_path).parent;data_root=Path(t.data_root);execution_context=self._execution_context()
        if os.name=="nt" and execution_context.get("interactive_session") is False:
            diagnostic={"code":"MT5_INTERACTIVE_SESSION_REQUIRED","message":"Native MT5 execution was requested from Windows Session 0. Install/start the VibeMQL5 tunnel Scheduled Task with Interactive logon so MetaTrader, report generation and GUI/profile operations run in the logged-in desktop session.","execution_context":execution_context};emit("TESTER_PRESTART_FAILED",diagnostic,once_key="prestart-failed");return {"status":"FAILED","execution_status":"NOT_RUN","report_status":"NOT_RUN","duration_seconds":round(time.monotonic()-started,3),"process_exit_code":None,"report":{"status":"NOT_RUN","metrics":{}},"logs":{"native_test_started":False,"native_test_finished":False,"native_test_passed":False},"preset":dict(resolved_config or overrides or {}),"tester_ini":None,"mock":False,"diagnostics":[diagnostic],"execution_context":execution_context,"request_normalization":request_normalization,"native_selected_period":{"status":"NOT_RUN"},"period_conformance":{"status":"NOT_RUN"},"executed_coverage":{"status":"NOT_RUN"},"completion_reason":"PRESTART_FAILED"}
        report_stem=f"VibeMQL5-{job_id}";report_candidates=self._report_candidates(install_dir,data_root,job_id);self._prepare_report_targets(report_candidates);ini,resolved=render_tester_ini(self.root,run_dir,expert_name,preset,set_name,overrides,report_value=report_stem,shutdown_terminal=True,tester_login=login,resolved_config=resolved_config);log_cursors=self._snapshot_log_lengths(terminal_alias);(run_dir/"tester.log").write_text("",encoding="utf-8");cmd=[t.terminal_path]
        if login:cmd.append(f"/login:{int(login)}")
        cmd.append(f"/config:{ini}");proc=subprocess.Popen(cmd,cwd=str(install_dir),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if on_pid:on_pid(proc.pid)
        emit("TESTER_PROCESS_STARTED",{"pid":proc.pid,"timeout_seconds":int(timeout)},once_key="process-started")
        actual_report=None;explicit_deadline=(time.monotonic()+int(timeout)) if int(timeout)>0 else None;report_grace_seconds=60.0;no_activity_notice_seconds=600.0;last_size=None;stable_since=None;terminal_exit_at=None;native_finished_at=None;last_activity=time.monotonic();last_progress=None;fatal_count=0;completion_reason=None;timed_out=False;log_receipts=[]
        while True:
            now=time.monotonic()
            if should_cancel is not None:
                try:cancel_now=bool(should_cancel())
                except Exception:cancel_now=False
                if cancel_now:completion_reason="CANCEL_REQUESTED_AFTER_NATIVE_FINISH" if native_finished_at is not None else "CANCEL_REQUESTED";emit("TESTER_CANCEL_OBSERVED",{"process_alive":proc.poll() is None,"after_native_finish":native_finished_at is not None},once_key="cancel-observed");break
            changed,receipts=self._capture_log_deltas(terminal_alias,run_dir,log_cursors,since=started_wall)
            if receipts:log_receipts.extend(receipts)
            if changed:last_activity=now
            logs_live=parse_tester_log(run_dir/"tester.log");progress=logs_live.get("progress_pct")
            if progress is not None and progress!=last_progress:last_progress=progress;last_activity=now;emit("TESTER_PROGRESS",{"progress_pct":progress})
            if logs_live.get("native_test_finished") and native_finished_at is None:native_finished_at=now;last_activity=now;emit("TESTER_NATIVE_FINISHED",{"progress_pct":progress},once_key="native-finished")
            current_fatals=list(logs_live.get("fatal_errors") or [])
            if len(current_fatals)>fatal_count:
                for message in current_fatals[fatal_count:]:emit("TESTER_FATAL",{"message":message})
                fatal_count=len(current_fatals);last_activity=now
            report=self._find_report(report_candidates,started_wall)
            if report is not None:
                try:size=report.stat().st_size
                except OSError:size=None
                if size and size==last_size:
                    stable_since=stable_since or now
                    if now-stable_since>=0.75 and actual_report is None:actual_report=report;last_activity=now;emit("TESTER_REPORT_READY",{"path":str(report),"bytes":size},once_key="report-ready")
                else:last_size=size;stable_since=None;last_activity=now if size else last_activity
            code_now=proc.poll()
            if code_now is not None and terminal_exit_at is None:terminal_exit_at=now;last_activity=now;emit("TESTER_TERMINAL_EXIT",{"exit_code":code_now},once_key="terminal-exit")
            if actual_report is not None and (terminal_exit_at is not None or native_finished_at is not None):
                anchor=terminal_exit_at if terminal_exit_at is not None else native_finished_at
                if anchor is not None and now-anchor>=1.0:completion_reason="NATIVE_FINISHED_REPORT_READY" if native_finished_at is not None else "TERMINAL_EXIT_REPORT_READY";break
            finish_anchor=terminal_exit_at if terminal_exit_at is not None else native_finished_at
            if finish_anchor is not None and actual_report is None and now-finish_anchor>=report_grace_seconds:completion_reason="TERMINAL_EXIT_REPORT_MISSING" if terminal_exit_at is not None else "NATIVE_FINISHED_REPORT_MISSING";break
            if explicit_deadline is not None and now>=explicit_deadline:timed_out=True;completion_reason="EXPLICIT_OPERATOR_TIMEOUT";emit("TESTER_EXPLICIT_TIMEOUT",{"timeout_seconds":int(timeout)},once_key="explicit-timeout");break
            if now-last_activity>=no_activity_notice_seconds:emit("TESTER_NO_RECENT_PROGRESS",{"inactive_seconds":round(now-last_activity,1),"process_alive":proc.poll() is None},once_key=f"no-progress-{int((now-started)//no_activity_notice_seconds)}")
            time.sleep(0.5)
        time.sleep(0.5);_,receipts=self._capture_log_deltas(terminal_alias,run_dir,log_cursors,since=started_wall)
        if receipts:log_receipts.extend(receipts)
        if actual_report is None:actual_report=self._find_report(report_candidates,started_wall)
        launcher_code=proc.poll()
        if proc.poll() is None and completion_reason is not None:
            try:proc.terminate();proc.wait(timeout=10)
            except Exception:
                try:proc.kill();proc.wait(timeout=5)
                except Exception:pass
        code=proc.returncode if proc.returncode is not None else launcher_code;logs=parse_tester_log(run_dir/"tester.log");diagnostics=list(logs.get("diagnostics",[]));native_pass=bool(logs.get("native_test_passed"));native_period=self._native_period_from_parsed_logs(logs);effective_period=dict(request_normalization.get("effective_period") or {})
        if native_period.get("status")=="OBSERVED":
            period_match=native_period.get("from_date")==effective_period.get("from_date") and native_period.get("to_date")==effective_period.get("to_date");period_conformance={"status":"PASS" if period_match else "MISMATCH","effective_period":effective_period,"native_selected_period":native_period};diagnostics_period=None if period_match else {"code":"NATIVE_PERIOD_MISMATCH","message":"MT5 native selected period differs from the effective validated request","effective_period":effective_period,"native_selected_period":native_period}
        else:period_conformance={"status":"UNVERIFIED","effective_period":effective_period,"native_selected_period":native_period};diagnostics_period={"code":"NATIVE_PERIOD_UNVERIFIED","message":"Native tester period could not be proven from the captured MT5 journal","effective_period":effective_period}
        normalized_xml=None
        if actual_report is not None:
            captured_report=self._copy_report(actual_report,run_dir);parsed=parse_report(captured_report);report_status=parsed.get("status","UNKNOWN")
            if parsed.get("status")=="PARSED":
                try:normalized_xml=write_normalized_report_xml(run_dir,captured_report,parsed.get("metrics") or {})
                except Exception as exc:diagnostics.append({"code":"RELEASE_XML_DERIVATION_FAILED","message":str(exc)})
        else:
            captured_report=run_dir/"report.htm";parsed=parse_report(captured_report);report_status="MISSING";diagnostics.insert(0,{"code":"EXPLICIT_TEST_TIMEOUT" if timed_out else "REPORT_MISSING_AFTER_NATIVE_TEST" if native_pass else "NO_REPORT_AFTER_TERMINAL_EXIT","message":f"Explicit operator timeout reached after {timeout}s" if timed_out else "Native MT5 test passed/finished but the configured HTML report was not found" if native_pass or logs.get("native_test_finished") else "MT5 terminal exited/returned without creating the configured tester report","report_candidates":[str(x) for x in report_candidates],"report_scan":self._report_scan(report_candidates,started_wall),"launcher_exit_code":launcher_code,"terminal_alias":terminal_alias,"execution_context":execution_context,"report_value":report_stem})
        if diagnostics_period is not None:diagnostics.append(diagnostics_period)
        if native_pass:execution_status="PASSED"
        elif timed_out:execution_status="TIMEOUT"
        elif logs.get("fatal_errors"):execution_status="FAILED"
        else:execution_status=logs.get("native_test_status","UNKNOWN")
        if timed_out:status="TIMEOUT"
        elif period_conformance.get("status")=="MISMATCH":status="FAILED"
        elif actual_report is not None and parsed.get("status")=="PARSED" and execution_status=="PASSED":status="COMPLETED"
        elif native_pass and actual_report is None:status="TEST_PASSED_REPORT_MISSING"
        else:status="FAILED"
        if actual_report is not None and parsed.get("status")!="PARSED":diagnostics.append({"code":"REPORT_PARSE_ERROR","message":parsed.get("error") or "MT5 report could not be parsed"})
        executed_coverage=self._classify_executed_coverage(logs=logs,effective_period=effective_period,native_period=native_period,completion_reason=completion_reason,timed_out=timed_out,log_receipts=log_receipts)
        if executed_coverage.get("status")=="EARLY_TERMINATION":diagnostics.append({"code":"NATIVE_EARLY_TERMINATION","message":"Native execution ended before the effective selected-period end","executed_coverage":executed_coverage})
        elif executed_coverage.get("status")=="UNVERIFIED" and status=="COMPLETED":diagnostics.append({"code":"EXECUTED_COVERAGE_UNVERIFIED","message":"Generic native finish/report evidence is insufficient to prove full selected-period execution","executed_coverage":executed_coverage})
        return {"status":status,"execution_status":execution_status,"report_status":report_status,"duration_seconds":round(time.monotonic()-started,3),"process_exit_code":code,"launcher_exit_code":launcher_code,"report":parsed,"logs":logs,"preset":resolved,"tester_ini":str(ini),"command":cmd,"source":"windows_native_mt5_strategy_tester" if os.name=="nt" else "native_mt5_strategy_tester_nonwindows","mock":False,"diagnostics":diagnostics,"terminal_report_path":str(actual_report) if actual_report else str(report_candidates[0]),"report_candidates":[str(x) for x in report_candidates],"report_value":report_stem,"report_scan":self._report_scan(report_candidates,started_wall),"execution_context":execution_context,"normalized_xml":normalized_xml,"request_normalization":request_normalization,"requested_period":request_normalization.get("requested_period"),"effective_period":request_normalization.get("effective_period"),"native_selected_period":native_period,"period_conformance":period_conformance,"executed_coverage":executed_coverage,"completion_reason":completion_reason,"explicit_timeout_seconds":int(timeout),"log_capture":{"cursor_path":"tester-log-cursor.json","receipts":log_receipts[-100:]}}
