from __future__ import annotations
import base64, hashlib, json, os, re, time, uuid
from pathlib import Path
from ..config import default_root, load_settings
from .workspace import WorkspaceManager
from .inventory import TerminalInventory
from .resources import ResourceGuard
from .jobs import JobManager
from .compiler import CompilerDriver
from .artifacts import ArtifactManager
from .baseline import BaselineManager
from .revisions import RevisionManager
from .project_sessions import ProjectSessionManager
from .continuity import ContinuityManager
from .iterations import IterationManager
from .observability import ObservabilityManager
from .provenance import validate_state_provenance
from .release import ReleaseEvidenceManager
from .forward import ForwardQualificationManager
from .live_readiness import LiveReadinessManager
from .tester_config import normalize_tester_request
from .file_export import FileExportManager
from .binary_ingress import BinaryIngressManager
from .concurrency import ConcurrencyManager, current_actor
from ..runtime_forensics.service import RuntimeForensicsManager

class ToolFacade:
    def __init__(self, root: Path | None = None):
        self.root=Path(root or default_root())
        self.ws=WorkspaceManager(self.root); self.inv=TerminalInventory(self.root); self.jobs=JobManager(self.root)
        self.revisions=RevisionManager(self.root)
        self.project_sessions=ProjectSessionManager(self.root)
        self.continuity=ContinuityManager(self.root)
        self.iterations=IterationManager(self.root)
        self.observability=ObservabilityManager(self.root); self.release=ReleaseEvidenceManager(self.root); self.forward=ForwardQualificationManager(self.root); self.live=LiveReadinessManager(self.root)
        self.file_exports=FileExportManager(self.root)
        self.binary_ingress=BinaryIngressManager(self.root)
        self.concurrency=ConcurrencyManager(self.root)
        self.runtime_forensics=RuntimeForensicsManager(self.root, self.jobs)

    def health(self):
        r=ResourceGuard(self.root).status(); vals=self.inv.validate()
        active=None; q=0
        for p in (self.root/'runs').glob('*/job.json'):
            try:
                j=json.loads(p.read_text(encoding='utf-8'))
                if j['state'] not in {"PASSED","ANOMALY","FAILED","TIMEOUT","CANCELLED","INTERRUPTED","RESOURCE_LIMIT"}:
                    q+=1; active=active or j['job_id']
            except Exception: pass
        return {"service":"READY" if r['state']!='BLOCKED' else 'RESOURCE_BLOCKED', **r, "queue_length":q,"active_job":active,
                "terminals_valid":sum(1 for x in vals if x['ok']),"terminals_registered":len(vals),
                "concurrency":self.concurrency.status(include_recent=False)}

    def diagnose(self):
        return {"health":self.health(),"terminals":self.inv.validate(),"workspaces":self.ws.list_workspaces(),
                "terminal_policy":(load_settings(self.root).get("terminal_policy") or {}),
                "paths":{"root":str(self.root),"config":str(self.root/'config'),"runs":str(self.root/'runs')},
                "core_files_ok":all((self.root/x).exists() for x in ['config/settings.json','config/terminals.json','pyproject.toml']),
                "concurrency":self.concurrency.status(include_recent=True)}

    def runtime_status(self):
        def read_json(path):
            try:
                if path.exists():
                    data=json.loads(path.read_text(encoding='utf-8-sig'))
                    return data if isinstance(data,dict) else {"status":"INVALID","path":str(path)}
            except Exception as exc:
                return {"status":"INVALID","path":str(path),"error":str(exc)}
            return {"status":"MISSING","path":str(path)}
        supervisor = read_json(self.root/'state'/'tunnel-supervisor.json')
        watchdog = read_json(self.root/'state'/'tunnel-watchdog.json')
        if supervisor.get("status") not in {"MISSING", "INVALID"}:
            supervisor.setdefault("component", "tunnel-supervisor")
            supervisor["provenance"] = validate_state_provenance(
                self.root, supervisor, self.root/'ops'/'windows'/'Start-VibeMQL5TunnelSupervisor.ps1', 'tunnel-supervisor'
            )
        if watchdog.get("status") not in {"MISSING", "INVALID"}:
            watchdog.setdefault("component", "watchdog")
            watchdog["provenance"] = validate_state_provenance(
                self.root, watchdog, self.root/'ops'/'windows'/'Invoke-VibeMQL5Watchdog.ps1', 'watchdog'
            )
        resilience = read_json(self.root/'state'/'tip013-resilience.json')
        if resilience.get("status") not in {"MISSING", "INVALID"}:
            resilience = {
                **resilience,
                "evidence_role": "HISTORICAL_QUALIFICATION",
                "current_runtime_certification": False,
            }
        return {
            "runtime_mode": os.environ.get("VIBEMQL5_RUNTIME_MODE","manual"),
            "supervisor_generation": os.environ.get("VIBEMQL5_SUPERVISOR_GENERATION",""),
            "supervisor_session_id": os.environ.get("VIBEMQL5_SUPERVISOR_SESSION_ID",""),
            "supervisor": supervisor,
            "watchdog": watchdog,
            "resilience": resilience,
        }

    @staticmethod
    def _require_mt5_capable_runtime():
        mode=os.environ.get("VIBEMQL5_RUNTIME_MODE","manual").strip().lower()
        if mode == "background":
            raise RuntimeError("MT5_INTERACTIVE_SESSION_REQUIRED: background boot-tunnel is read/control-plane only; log on to Windows to activate interactive MT5 mode")

    def get_continuity(self, project_id): return self.continuity.get(project_id)
    def read_continuity_events(self, project_id, after_seq=0, limit=100):
        return self.continuity.read_events(project_id, after_seq, limit)
    def verify_continuity(self, project_id): return self.continuity.verify(project_id)
    def append_continuity_event(self, project_id, event_type, payload, operation_id, expected_manifest_revision, expected_manifest_sha256):
        with self.concurrency.mutation("append_continuity_event", project_id=project_id):
            self.concurrency.note_project_actor(project_id)
            return self.continuity.append_event(
                project_id, event_type, payload, operation_id, expected_manifest_revision,
                expected_manifest_sha256, current_actor(),
            )
    def create_continuity_checkpoint(self, project_id, label, operation_id, expected_manifest_revision, expected_manifest_sha256):
        with self.concurrency.mutation("create_continuity_checkpoint", project_id=project_id):
            self.concurrency.note_project_actor(project_id)
            return self.continuity.create_checkpoint(
                project_id, label, operation_id, expected_manifest_revision, expected_manifest_sha256,
            )
    def reconcile_continuity(self, project_id, operation_id, expected_manifest_revision, expected_manifest_sha256):
        with self.concurrency.mutation("reconcile_continuity", project_id=project_id):
            self.concurrency.note_project_actor(project_id)
            return self.continuity.reconcile(
                project_id, operation_id, expected_manifest_revision, expected_manifest_sha256,
            )

    def list_project_sessions(self): return self.project_sessions.list()
    def get_project_session(self, project_id): return self.project_sessions.get(project_id)
    def create_project_session(self, project_id, workspace, ea, active_goal="", decision_refs=None, phase="IDLE", checkpoint_id="", baseline_job_id="", last_job_id=""):
        with self.concurrency.mutation("create_project_session", resource=f"{workspace}:{ea}", project_id=project_id):
            out = self.project_sessions.create(project_id, workspace, ea, active_goal, decision_refs or [], phase, checkpoint_id, baseline_job_id, last_job_id)
            self.concurrency.note_project_actor(project_id)
            return out
    def update_project_session(
        self, project_id, expected_revision, active_goal=None, decision_refs=None,
        phase=None, checkpoint_id=None, baseline_job_id=None, last_job_id=None,
        operation_id="", expected_revision_sha256="",
    ):
        with self.concurrency.mutation("update_project_session", project_id=project_id):
            out = self.project_sessions.update(
                project_id, expected_revision,
                active_goal=active_goal, decision_refs=decision_refs, phase=phase,
                checkpoint_id=checkpoint_id, baseline_job_id=baseline_job_id, last_job_id=last_job_id,
                operation_id=operation_id, expected_revision_sha256=expected_revision_sha256,
            )
            self.concurrency.note_project_actor(project_id)
            return out
    def resume_project_session(self, project_id): return self.project_sessions.resume(project_id)

    def start_iteration(self, project_id, expected_session_revision, expected_session_revision_sha256, expected_source_sha256, expected_source_bytes, mutation, preset="smoke", set_file="", overrides=None, timeout_seconds=0):
        # TUN-01: reject tester-contract errors before iteration/source/job side effects.
        normalize_tester_request(self.root, preset, overrides or {})
        with self.concurrency.mutation("start_iteration", project_id=project_id):
            out = self.iterations.start(
                project_id, expected_session_revision, expected_session_revision_sha256,
                expected_source_sha256, int(expected_source_bytes), mutation,
                preset=preset, set_file=set_file, overrides=overrides or {}, timeout_seconds=timeout_seconds,
            )
            self.concurrency.note_project_actor(project_id)
            self.concurrency.note_iteration_actor(out.get("iteration_id", ""))
            return out
    def get_iteration(self, iteration_id): return self.iterations.get(iteration_id)
    def list_iterations(self): return self.iterations.list()
    def resume_iteration(self, iteration_id, expected_revision, expected_revision_sha256):
        current = self.iterations.get(iteration_id)
        pre_native_states = {"SESSION_BOUND", "PRECHECK", "CHECKPOINTED", "MUTATED"}
        with self.concurrency.mutation("resume_iteration", resource=iteration_id, project_id=str(current.get("project_id") or "")):
            self.concurrency.note_iteration_actor(iteration_id)
            if current.get("state") in pre_native_states:
                with self.concurrency.native_execution(f"ITERATION-{iteration_id}", kind="iteration_compile", wait_seconds=300):
                    return self.iterations.resume(iteration_id, expected_revision, expected_revision_sha256)
            return self.iterations.resume(iteration_id, expected_revision, expected_revision_sha256)
    def accept_iteration(self, iteration_id, expected_revision, expected_revision_sha256):
        current = self.iterations.get(iteration_id)
        with self.concurrency.mutation("accept_iteration", resource=iteration_id, project_id=str(current.get("project_id") or "")):
            self.concurrency.note_iteration_actor(iteration_id)
            return self.iterations.accept(iteration_id, expected_revision, expected_revision_sha256)
    def reject_iteration(self, iteration_id, expected_revision, expected_revision_sha256):
        current = self.iterations.get(iteration_id)
        with self.concurrency.mutation("reject_iteration", resource=iteration_id, project_id=str(current.get("project_id") or "")):
            self.concurrency.note_iteration_actor(iteration_id)
            return self.iterations.reject(iteration_id, expected_revision, expected_revision_sha256)
    def cancel_iteration(self, iteration_id, expected_revision, expected_revision_sha256):
        current = self.iterations.get(iteration_id)
        with self.concurrency.mutation("cancel_iteration", resource=iteration_id, project_id=str(current.get("project_id") or "")):
            self.concurrency.note_iteration_actor(iteration_id)
            return self.iterations.cancel(iteration_id, expected_revision, expected_revision_sha256)
    def read_iteration_history(self, iteration_id, limit=100, newest_first=True):
        return self.observability.iteration_history(iteration_id, limit, newest_first)
    def list_fault_receipts(self, limit=100, newest_first=True):
        return self.observability.fault_receipts(limit, newest_first)
    def list_job_history(self, limit=100, newest_first=True, workspace="", state=""):
        return self.observability.job_history(limit, newest_first, workspace, state)

    def release_check_all(self, project_id, job_id): return self.release.check_all(project_id, job_id)
    def release_attest(self, project_id, job_id): return self.release.attest(project_id, job_id)
    def release_ship(self, project_id, job_id): return self.release.ship(project_id, job_id)
    def forward_check(self, project_id, jobs_payload): return self.forward.check(project_id, jobs_payload)
    def forward_attest(self, project_id, qualification_id): return self.forward.attest(project_id, qualification_id)
    def forward_promote(self, project_id, qualification_id): return self.forward.promote(project_id, qualification_id)
    def live_check(self, project_id, scan_evidence, capability_matrix, session_evidence=None): return self.live.check(project_id, scan_evidence, capability_matrix, session_evidence)
    def live_attest(self, project_id, qualification_id): return self.live.attest(project_id, qualification_id)
    def live_package(self, project_id, qualification_id): return self.live.package(project_id, qualification_id)

    def list_workspaces(self): return self.ws.list_workspaces()
    def list_eas(self, workspace): return self.ws.list_eas(workspace)
    def list_terminals(self): return [x.to_dict() for x in self.inv.list()]
    def list_presets(self): return sorted(p.stem for p in (self.root/'config'/'presets').glob('*.json'))
    def list_parameter_sets(self, workspace): return self.ws.list_parameter_sets(workspace)
    def read_source(self, workspace, path):
        content=self.ws.read_text(workspace,path)
        meta=self.revisions.source_hash(workspace,path)
        return {"path":path,"content":content,"sha256":meta["sha256"],"bytes":meta["bytes"]}

    def get_source_hash(self, workspace, path):
        return self.revisions.source_hash(workspace,path)

    def create_checkpoint(self, workspace, path, label=""):
        with self.concurrency.mutation("create_checkpoint", resource=f"{workspace}:{path}"):
            return self.revisions.create_checkpoint(workspace,path,label)

    def list_checkpoints(self, workspace, path=""):
        return self.revisions.list_checkpoints(workspace,path)

    def diff_checkpoint(self, workspace, checkpoint_id, context_lines=3):
        return self.revisions.diff_checkpoint(workspace,checkpoint_id,context_lines)

    def restore_checkpoint(self, workspace, checkpoint_id, expected_current_sha256=""):
        if not str(expected_current_sha256 or "").strip():
            raise ValueError("MULTI_CLIENT_CAS_REQUIRED: restore_checkpoint requires expected_current_sha256")
        with self.concurrency.mutation("restore_checkpoint", resource=f"{workspace}:{checkpoint_id}"):
            return self.revisions.restore_checkpoint(workspace,checkpoint_id,expected_current_sha256)

    def write_source(self, workspace, path, content, expected_sha256="", checkpoint_id=""):
        target = self.ws.resolve(workspace, path)
        if target.is_file():
            if not str(expected_sha256 or "").strip():
                raise ValueError("MULTI_CLIENT_CAS_REQUIRED: existing source requires expected_sha256")
            if not str(checkpoint_id or "").strip():
                raise ValueError("MULTI_CLIENT_CHECKPOINT_REQUIRED: existing source requires checkpoint_id")
        with self.concurrency.mutation("write_source", resource=f"{workspace}:{path}"):
            return self.ws.write_text(workspace,path,content,expected_sha256,checkpoint_id)

    def apply_patch(self, workspace, path, replacements, expected_sha256="", checkpoint_id=""):
        if not str(expected_sha256 or "").strip():
            raise ValueError("MULTI_CLIENT_CAS_REQUIRED: apply_patch requires expected_sha256")
        if not str(checkpoint_id or "").strip():
            raise ValueError("MULTI_CLIENT_CHECKPOINT_REQUIRED: apply_patch requires checkpoint_id")
        with self.concurrency.mutation("apply_patch", resource=f"{workspace}:{path}"):
            return self.ws.apply_patch(workspace,path,replacements,expected_sha256,checkpoint_id)

    def _fixed_terminal(self):
        settings=load_settings(self.root); policy=settings.get("terminal_policy") or {}
        return str(policy.get("alias") or settings.get("defaults",{}).get("terminal") or "MT5-2")

    def compile_ea(self, workspace, ea, terminal=None, mock=False):
        self._require_mt5_capable_runtime()
        fixed=self._fixed_terminal()
        artifacts=ArtifactManager(self.root)
        job_id=f'COMPILE-{int(time.time()*1000)}-{uuid.uuid4().hex[:8].upper()}'; rd=artifacts.run_dir(job_id)
        # Standard lock order: mutation/source guard -> native MT5 lease. This
        # prevents another client from editing the compile target mid-MetaEditor run.
        with self.concurrency.mutation("direct_compile_source_guard", resource=f"{workspace}:{ea}", wait_seconds=300):
            inputs = artifacts.capture_build_inputs(job_id, workspace, self.ws.workspace_root(workspace), ea)
            with self.concurrency.native_execution(job_id, kind="direct_compile", wait_seconds=300) as lease:
                out = CompilerDriver(self.root).compile(workspace,ea,fixed,rd,mock=mock)
                outputs = artifacts.write_build_output_manifest(job_id, out)
                return {
                    **out,
                    "operation_id": job_id,
                    "build_provenance": {
                        "input_manifest": "build-input-manifest.json",
                        "input_manifest_sha256": inputs["manifest_sha256"],
                        "output_manifest": "build-output-manifest.json",
                        "output_manifest_sha256": outputs["manifest_sha256"],
                    },
                    "orchestration": {"actor": current_actor(), "native_execution": lease.to_dict()},
                }

    def import_ex5(self, workspace, file_param, destination_path='', expected_sha256='', overwrite=False):
        name = destination_path or str((file_param or {}).get("file_name") or "external.ex5")
        with self.concurrency.mutation("import_ex5", resource=f"{workspace}:{name}", wait_seconds=300) as lease:
            return self.binary_ingress.import_file_param(
                workspace, file_param, destination_path, expected_sha256, bool(overwrite),
                mutation_operation_id=lease.operation_id,
            )

    def import_ex5_authorized_file(
        self, workspace, file_id, download_url, file_name, mime_type='application/octet-stream',
        destination_path='', expected_sha256='', overwrite=False,
    ):
        name = destination_path or str(file_name or 'external.ex5')
        with self.concurrency.mutation("import_ex5_authorized_file", resource=f"{workspace}:{name}", wait_seconds=300) as lease:
            return self.binary_ingress.import_authorized_file(
                workspace,
                file_id=file_id,
                download_url=download_url,
                file_name=file_name,
                mime_type=mime_type,
                destination_path=destination_path,
                expected_sha256=expected_sha256,
                overwrite=bool(overwrite),
                mutation_operation_id=lease.operation_id,
            )

    def get_ex5_import_receipt(self, mutation_operation_id='', import_id='', ea_binary_ref=''):
        return self.binary_ingress.get_import_receipt(
            mutation_operation_id=mutation_operation_id, import_id=import_id, ea_binary_ref=ea_binary_ref
        )

    def _import_ex5_local_for_qualification(self, workspace, source_path, destination_path='', expected_sha256='', overwrite=False):
        """Windows qualification helper; intentionally not registered as an MCP tool."""
        name = destination_path or Path(source_path).name
        with self.concurrency.mutation("import_ex5", resource=f"{workspace}:{name}", wait_seconds=300) as lease:
            return self.binary_ingress.import_local_file(
                workspace, Path(source_path), destination_path, expected_sha256, bool(overwrite),
                source="WINDOWS_NATIVE_QUALIFICATION_FILE", mutation_operation_id=lease.operation_id,
            )

    def launch_test(self, workspace, ea, terminal=None, preset='smoke', set_file=None, overrides=None, mock=False, test_timeout=0, ea_binary_ref='', operation_id=''):
        self._require_mt5_capable_runtime()
        # TUN-01 boundary validation: invalid overrides/date/delay fail before a
        # job id, lock, compile artifact, terminal handoff, or MT5 process exists.
        normalize_tester_request(self.root, preset, overrides or {})
        binary_ref = str(ea_binary_ref or '').strip()
        if binary_ref:
            # Resolve before job creation so invalid/stale references fail without a
            # durable job or native MT5 side effect. Worker resolves it again later.
            self.binary_ingress.resolve_for_launch(workspace, ea, binary_ref)
        fixed=self._fixed_terminal()
        actor = current_actor()
        return self.jobs.launch_test({"workspace":workspace,"ea":ea,"terminal":fixed,"preset":preset,"set_file":set_file,
                                      "overrides":overrides or {},"mock":bool(mock),"test_timeout":int(test_timeout),
                                      "ea_binary_ref":binary_ref or None,
                                      "orchestration_actor":actor}, operation_id=operation_id)
    def get_job(self, job_id, wait_seconds=0, after_event_seq=-1):
        return self.jobs.get_job(job_id, wait_seconds=wait_seconds, after_event_seq=after_event_seq)
    def cancel_job(self, job_id):
        self.concurrency._audit("JOB_CANCEL_REQUEST", job_id=job_id, actor=current_actor())
        return self.jobs.cancel_job(job_id)
    def reconcile_cancelled_jobs(self, wait_seconds=0.5): return self.jobs.reconcile_cancelled_jobs(wait_seconds=wait_seconds)
    def read_result(self, job_id): return self.jobs.read_result(job_id)
    def read_compile_diagnostics(self, job_id):
        p=self.root/'runs'/job_id/'compile.json'; return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {"status":"NOT_READY"}
    def read_tester_events(self, job_id):
        from ..parsers.tester_log import parse_tester_log
        return parse_tester_log(self.root/'runs'/job_id/'tester.log')
    def read_artifact(self, job_id, name, offset=0, max_bytes=262144):
        """Read a bounded job-scoped logical artifact; binary data is base64 chunks."""
        from ..parsers.tester_log import decode_text_bytes
        # Prove the job exists before resolving any artifact.
        job = self.jobs.get_job(job_id)
        job_terminal = job.get("state") in {"PASSED","ANOMALY","FAILED","TIMEOUT","CANCELLED","INTERRUPTED","RESOURCE_LIMIT"}
        run_dir = self.root/'runs'/job_id
        text_allowed = {
            'job.json','request.json','environment.json','compile.log','compile.json',
            'tester.log','tester-log-cursor.json','result.json','summary.md','tester.ini',
            'report.htm','report.html','report.native.xml','report.xml','worker-error.log',
            'phase-config.json','phase-compile.json','phase-handoff.json','phase-tester.json','phase-cleanup.json',
            'build-input-manifest.json','build-output-manifest.json',
        }
        binary_map = {'compiled.ex5': run_dir/'compiled.ex5'}
        raw_match = re.fullmatch(r'rawlog:([0-9a-fA-F]{16})', str(name or ''))
        if raw_match:
            binary_map[name] = run_dir/f"tester-log-{raw_match.group(1).lower()}.bin"

        immutable_names = {"compiled.ex5", "phase-config.json", "phase-compile.json", "phase-handoff.json", "phase-tester.json", "phase-cleanup.json"}
        def meta(logical, path, kind):
            complete = bool(logical in immutable_names or job_terminal)
            base = {
                "name": logical, "kind": kind, "job_id": job_id,
                "job_state": job.get("state"), "source_relation": "job_scoped_run_artifact",
                "complete": False,
            }
            if not path.is_file():
                return {**base, "exists": False, "bytes": 0, "sha256": None}
            raw = path.read_bytes()
            return {**base, "exists": True, "complete": complete, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

        if name == 'manifest':
            items = []
            for logical in sorted(text_allowed):
                items.append(meta(logical, run_dir/logical, 'text'))
            items.append(meta('compiled.ex5', run_dir/'compiled.ex5', 'binary'))
            for p in sorted(run_dir.glob('tester-log-*.bin')):
                m = re.fullmatch(r'tester-log-([0-9a-fA-F]{16})\.bin', p.name)
                if m:
                    items.append(meta(f"rawlog:{m.group(1).lower()}", p, 'binary'))
            payload = json.dumps(items, sort_keys=True, separators=(",", ":")).encode("utf-8")
            return {
                "schema_version": "1.0", "job_id": job_id, "job_state": job.get("state"),
                "name": "manifest", "artifacts": items,
                "catalog_sha256": hashlib.sha256(payload).hexdigest(),
            }

        if name in text_allowed:
            p = run_dir/name
            if not p.is_file():
                return {"status":"MISSING","name":name}
            raw = p.read_bytes()
            text, decoding = decode_text_bytes(raw)
            return {
                "name": name, "kind": "text", "content": text,
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "decoding": decoding,
            }

        if name in binary_map:
            p = binary_map[name]
            if not p.is_file():
                return {"status":"MISSING","name":name}
            raw = p.read_bytes()
            start = max(0, int(offset or 0))
            limit = max(1, min(int(max_bytes or 262144), 262144))
            if start > len(raw):
                raise ValueError('Artifact offset beyond end')
            chunk = raw[start:start+limit]
            end = start + len(chunk)
            return {
                "name": name, "kind": "binary", "encoding": "base64",
                "offset": start, "next_offset": end, "eof": end >= len(raw),
                "chunk_bytes": len(chunk), "content_base64": base64.b64encode(chunk).decode('ascii'),
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            }
        raise ValueError('Artifact not allowed')
    def prepare_file_export(self, scope, source_id, name="", expected_sha256=""):
        return self.file_exports.prepare(scope, source_id, name, expected_sha256)

    def read_file_export_resource(self, token):
        return self.file_exports.read_token(token)

    def capture_runtime_snapshot(self, job_id, profile="private", label=""):
        return self.runtime_forensics.capture(job_id, profile, label)

    def compare_runtime_snapshots(self, capture_a, capture_b, mode="delta", known_values=None):
        return self.runtime_forensics.compare(capture_a, capture_b, mode, known_values or [])

    def compare_baseline(self, workspace, baseline, job_id): return BaselineManager(self.root).compare(workspace,baseline,self.read_result(job_id))
