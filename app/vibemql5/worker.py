from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .config import load_preset, load_settings
from .contracts import RESULT_SCHEMA_VERSION
from .core.artifacts import ArtifactManager
from .core.binary_ingress import BinaryIngressManager
from .core.compiler import CompilerDriver
from .core.inventory import TerminalInventory
from .core.jobs import JobManager, JobStore, _pid_exists
from .core.concurrency import ConcurrencyManager, acquire_native_execution, actor_scope
from .core.mt5_preflight import MT5Preflight, public_preflight
from .core.resources import ResourceGuard
from .core.revisions import RevisionManager
from .core.terminal_handoff import exclusive_live_terminal_handoff
from .core.tester import TesterDriver
from .core.tester_config import normalize_tester_request
from .core.workspace import WorkspaceManager

TERMINALS = {"PASSED", "ANOMALY", "FAILED", "TIMEOUT", "CANCELLED", "INTERRUPTED", "RESOURCE_LIMIT"}


def _process_exists(pid: int) -> bool:
    # Reuse the side-effect-free cross-platform probe from JobManager. On Windows
    # os.kill(pid, 0) would terminate the process instead of merely probing it.
    return _pid_exists(int(pid))


def acquire_lock(
    root: Path,
    job_id: str,
    wait_seconds: int = 300,
    actor: dict | None = None,
):
    """Acquire the shared FIFO native-execution lease.

    TIP-024 keeps the historical ``runs/.active.lock`` path so startup/recovery
    tooling remains compatible, while direct compile and Strategy Tester workers
    now contend on the same cross-process queue.
    """
    return acquire_native_execution(
        root,
        job_id,
        kind="strategy_test",
        actor=actor,
        wait_seconds=float(wait_seconds),
    )


def _requested_symbol(root: Path, req: dict) -> str:
    overrides = req.get("overrides") or {}
    if overrides.get("symbol"):
        return str(overrides["symbol"])
    preset = load_preset(req.get("preset", "smoke"), root)
    return str(preset.get("symbol", "EURUSD"))


def _read_env(run_dir: Path) -> dict:
    path = run_dir / "environment.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        return {}


def _publish_terminal(store: JobStore, job_id: str, state: str, payload: dict | None = None) -> None:
    try:
        store.publish_event(job_id, "JOB_TERMINAL", {"state": state, **dict(payload or {})})
    except Exception:
        pass


def run_job(root: Path, job_id: str) -> None:
    store = JobStore(root)
    manager = JobManager(root)
    artifacts = ArtifactManager(root)
    job = store.load(job_id)
    req = job["request"]
    run_dir = artifacts.run_dir(job_id)
    lock = None
    comp: dict | None = None
    tst: dict | None = None
    handoff_meta: dict | None = None
    normalized_config: dict | None = None
    request_normalization: dict | None = None
    actor = req.get("orchestration_actor") if isinstance(req.get("orchestration_actor"), dict) else None
    concurrency = ConcurrencyManager(root)
    if actor is None and req.get("iteration_id"):
        actor = concurrency.iteration_actor(str(req.get("iteration_id")))
    actor_cm = actor_scope(actor)
    actor_cm.__enter__()
    source_guard_cm = None
    binary_binding: dict | None = None
    binary_deployment: dict | None = None

    try:
        # Lock order is always mutation -> native. Hold the mutation guard only
        # through source CAS/snapshot/compile; the Strategy Tester then runs on
        # the immutable EX5/source evidence while unrelated source work may continue.
        source_guard_cm = concurrency.mutation(
            "worker_source_compile_guard",
            resource=f"{req.get('workspace','')}:{req.get('ea','')}",
            project_id=str(req.get("project_id") or ""),
            wait_seconds=float(req.get("queue_wait_seconds", 300)),
        )
        source_guard_cm.__enter__()
        lock = acquire_lock(root, job_id, int(req.get("queue_wait_seconds", 300)), actor=actor)
        store.update_fields(
            job_id,
            orchestration_actor=dict(actor or {}),
            native_execution_lease=lock.to_dict(),
            native_execution_wait_seconds=lock.wait_elapsed_seconds,
        )
        if store.load(job_id).get("cancel_requested"):
            store.transition(store.load(job_id), "CANCELLED")
            _publish_terminal(store, job_id, "CANCELLED")
            return

        binary_ref = str(req.get("ea_binary_ref") or "").strip()
        expected_source_sha = str(req.get("expected_source_sha256") or "").strip().lower()
        expected_source_bytes = req.get("expected_source_bytes")
        if binary_ref and expected_source_sha:
            raise RuntimeError("IMPORTED_EX5_SOURCE_CAS_CONFLICT: source SHA constraints do not apply to ea_binary_ref jobs")
        if expected_source_sha:
            source = RevisionManager(root).source_hash(req["workspace"], req["ea"])
            source_ok = source["sha256"] == expected_source_sha
            if expected_source_bytes not in (None, ""):
                source_ok = source_ok and int(source["bytes"]) == int(expected_source_bytes)
            store.update_fields(job_id, candidate_source_preflight={
                "expected_sha256": expected_source_sha,
                "expected_bytes": expected_source_bytes,
                "actual_sha256": source["sha256"],
                "actual_bytes": source["bytes"],
                "match": bool(source_ok),
            })
            if not source_ok:
                raise RuntimeError("CANDIDATE_SOURCE_DRIFT: current source does not match the iteration-bound candidate")

        store.transition(store.load(job_id), "RESOURCE_CHECK")
        health = ResourceGuard(root).status()

        # TUN-01 / D-021R-01 / D-021R-02: all tester request semantics are
        # validated and normalized before compile, report deletion, handoff or launch.
        normalized_config, request_normalization = normalize_tester_request(
            root, req.get("preset", "smoke"), dict(req.get("overrides") or {})
        )
        requested_symbol = str(normalized_config["symbol"])
        artifacts.write_phase_receipt(job_id, "config", {
            "schema_version": "1.0",
            "phase": "CONFIG_VALIDATION",
            "status": "PASSED",
            "resolved_config": normalized_config,
            "normalization": request_normalization,
        })
        store.update_fields(
            job_id,
            tester_request_normalization=request_normalization,
            tester_resolved_config=normalized_config,
        )
        store.publish_event(job_id, "TESTER_REQUEST_VALIDATED", {
            "future_to_date_clamped": bool(request_normalization.get("future_to_date_clamped")),
            "execution_delay": request_normalization.get("execution_delay"),
        })

        if health["state"] == "BLOCKED" and not req.get("mock"):
            artifacts.write_json(job_id, "environment.json", {"resource_guard": health})
            store.transition(store.load(job_id), "RESOURCE_LIMIT")
            _publish_terminal(store, job_id, "RESOURCE_LIMIT")
            return

        inventory = TerminalInventory(root)
        settings = load_settings(root)
        policy = settings.get("terminal_policy") or {}
        fixed_alias = str(policy.get("alias") or settings.get("defaults", {}).get("terminal") or "MT5-2")
        requested_alias = req.get("terminal", fixed_alias)
        effective_alias = fixed_alias
        effective = inventory.get(effective_alias)
        preflight = None

        if req.get("mock"):
            resolved_symbol = requested_symbol
            login = None
            selection = {
                "requested": requested_alias,
                "effective": fixed_alias,
                "fallback": False,
                "reason": "FIXED_TERMINAL_POLICY_MOCK",
                "policy": "FIXED_MT5_2",
            }
        else:
            if str(policy.get("mode", "fixed")).lower() != "fixed" or fixed_alias.upper() != "MT5-2":
                raise RuntimeError("TERMINAL_POLICY_INVALID: RC5 requires fixed MT5-2 execution")
            preflight = MT5Preflight(effective.terminal_path).probe(requested_symbol)
            if not preflight.get("ok"):
                code = preflight.get("code", "MT5_2_PREFLIGHT_FAILED")
                raise RuntimeError(f"{code}: MT5-2 must be logged in and connected before a tester job")
            resolved_symbol = preflight.get("resolved_symbol")
            if not resolved_symbol:
                raise RuntimeError(f"SYMBOL_NOT_FOUND_ON_MT5_2: {requested_symbol} was not found on the connected MT5-2 broker session")
            login = int(preflight.get("_login") or 0)
            if not login:
                raise RuntimeError("MT5_2_LOGIN_MISSING: live MT5-2 account login could not be resolved")
            selection = {
                "requested": requested_alias,
                "effective": fixed_alias,
                "fallback": False,
                "reason": "FIXED_MT5_2_POLICY",
                "policy": "FIXED_MT5_2",
                "observed_build": preflight.get("build"),
            }

        normalized_config = dict(normalized_config)
        normalized_config["symbol"] = resolved_symbol
        selection["requested_symbol"] = requested_symbol
        selection["resolved_symbol"] = resolved_symbol
        selection["session_mirror_required"] = False
        selection["exclusive_handoff_required"] = not bool(req.get("mock"))

        store.update_fields(job_id, execution_terminal=selection, tester_resolved_config=normalized_config)
        artifacts.write_json(job_id, "environment.json", {
            "resource_guard": health,
            "terminal_selection": selection,
            "requested_terminal": requested_alias,
            "effective_terminal": effective_alias,
            "requested_symbol": requested_symbol,
            "resolved_symbol": resolved_symbol,
            "requested_terminal_preflight": public_preflight(preflight),
            "tester_request_normalization": request_normalization,
        })

        workspace_mgr = WorkspaceManager(root)
        binary_mgr = BinaryIngressManager(root)
        store.transition(store.load(job_id), "COMPILING")
        if binary_ref:
            binary_binding = binary_mgr.resolve_for_launch(req["workspace"], req["ea"], binary_ref)
            immutable_ex5 = binary_mgr.capture_for_job(binary_binding, run_dir)
            build_inputs = artifacts.capture_imported_build_inputs(
                job_id,
                req["workspace"],
                workspace_mgr.workspace_root(req["workspace"]),
                req["ea"],
                binary_binding,
                immutable_ex5,
                req.get("set_file"),
                ingress_provenance=binary_mgr.import_provenance(binary_ref),
            )
            comp = {
                "status": "NOT_REQUIRED",
                "errors": 0,
                "warnings": 0,
                "diagnostics": [],
                "source": "imported_ex5",
                "expert_name": binary_mgr.expert_name(req["workspace"], req["ea"]),
                "immutable_ex5": immutable_ex5,
                "ea_binary_ref": binary_ref,
                "build_input_type": "IMPORTED_EX5",
                "process_exit_code": None,
                "mock": bool(req.get("mock")),
            }
            artifacts.write_json(job_id, "compile.json", comp)
            (run_dir / "compile.log").write_text(
                "VibeMQL5 TIP-026: compile not required for immutable imported EX5.\n",
                encoding="utf-8",
            )
            store.publish_event(job_id, "COMPILE_NOT_REQUIRED", {
                "build_input_type": "IMPORTED_EX5",
                "ea_binary_ref": binary_ref,
                "sha256": immutable_ex5.get("sha256"),
                "bytes": immutable_ex5.get("bytes"),
            })
        else:
            build_inputs = artifacts.capture_build_inputs(
                job_id,
                req["workspace"],
                workspace_mgr.workspace_root(req["workspace"]),
                req["ea"],
                req.get("set_file"),
            )
            compiler = CompilerDriver(root)

            def compiler_pid(pid):
                store.set_process(store.load(job_id), "metaeditor", pid)

            comp = compiler.compile(
                req["workspace"], req["ea"], effective_alias, run_dir,
                timeout=int(req.get("compile_timeout", 120)), mock=bool(req.get("mock")),
                on_pid=compiler_pid,
            )
            store.set_process(store.load(job_id), "metaeditor", None)

        store.update_fields(job_id, build_input_provenance={
            "manifest": "build-input-manifest.json",
            "sha256": build_inputs["manifest_sha256"],
            "source_snapshot_catalog_sha256": (build_inputs.get("source_snapshot") or {}).get("catalog_sha256"),
            "build_input_source": build_inputs.get("build_input_source", "COMPILED_SOURCE"),
            "ea_binary_ref": binary_ref or None,
        })
        build_outputs = artifacts.write_build_output_manifest(job_id, comp)
        store.update_fields(job_id, build_output_provenance={
            "manifest": "build-output-manifest.json",
            "sha256": build_outputs["manifest_sha256"],
            "compiled_ex5_sha256": (build_outputs.get("compiled_ex5") or {}).get("sha256"),
        })
        artifacts.write_phase_receipt(job_id, "compile", {
            "schema_version": "1.0",
            "phase": "COMPILE",
            "status": comp.get("status", "UNKNOWN"),
            "evidence": comp,
        })
        store.publish_event(job_id, "COMPILE_FINISHED", {
            "status": comp.get("status"),
            "errors": comp.get("errors"),
            "warnings": comp.get("warnings"),
            "immutable_ex5": comp.get("immutable_ex5"),
            "build_input_type": comp.get("build_input_type", "COMPILED_SOURCE"),
        })
        if source_guard_cm is not None:
            source_guard_cm.__exit__(None, None, None)
            source_guard_cm = None

        job = store.load(job_id)
        if job.get("cancel_requested"):
            store.transition(job, "CANCELLED")
            _publish_terminal(store, job_id, "CANCELLED")
            return
        if comp.get("status") == "FAILED":
            store.transition(job, "FAILED")
            result = build_result(root, job_id, comp, None)
            artifacts.write_json(job_id, "result.json", result)
            _publish_terminal(store, job_id, "FAILED", {"phase": "compile"})
            return

        store.transition(store.load(job_id), "DEPLOYING")
        job = store.load(job_id)
        if job.get("cancel_requested"):
            store.transition(job, "CANCELLED")
            _publish_terminal(store, job_id, "CANCELLED")
            return
        store.transition(job, "TESTING")
        tester = TesterDriver(root)

        def tester_pid(pid):
            store.set_process(store.load(job_id), "terminal", pid)

        def tester_event(kind: str, payload: dict):
            store.publish_event(job_id, kind, payload)

        timeout_value = int(req.get("test_timeout", 0) or 0)

        def cancel_requested() -> bool:
            try:
                return bool(store.load(job_id).get("cancel_requested"))
            except Exception:
                return False

        if req.get("mock"):
            tst = tester.run(
                job_id, req["workspace"], req["ea"], effective_alias, comp["expert_name"],
                req.get("preset", "smoke"), run_dir, req.get("set_file"),
                normalized_config, timeout_value, True, tester_pid, login=None,
                on_event=tester_event, resolved_config=normalized_config,
                request_normalization=request_normalization, should_cancel=cancel_requested,
            )
        else:
            close_timeout = int(policy.get("graceful_close_seconds", 20))
            reconnect_timeout = int(policy.get("reconnect_timeout_seconds", 60))
            try:
                with exclusive_live_terminal_handoff(
                    effective, login, resolved_symbol,
                    close_timeout=close_timeout, reconnect_timeout=reconnect_timeout,
                ) as hm:
                    handoff_meta = hm
                    env = _read_env(run_dir)
                    env["terminal_handoff"] = dict(handoff_meta)
                    artifacts.write_json(job_id, "environment.json", env)
                    artifacts.write_phase_receipt(job_id, "handoff", {
                        "schema_version": "1.0",
                        "phase": "HANDOFF",
                        "status": "PASSED",
                        "evidence": dict(handoff_meta),
                    })
                    store.publish_event(job_id, "TERMINAL_HANDOFF_COMPLETE", {
                        "was_running": bool(handoff_meta.get("was_running")),
                        "closed_pids": handoff_meta.get("closed_pids", []),
                    })
                    if binary_ref:
                        if binary_binding is None:
                            raise RuntimeError("BUILD_INPUT_REFERENCE_INVALID")
                        binary_deployment = binary_mgr.stage_for_terminal(
                            binary_binding, effective_alias,
                            terminal_build_at_execution=int((preflight or {}).get("build") or effective.build),
                        )
                        if binary_deployment.get("expert_name") != comp.get("expert_name"):
                            raise RuntimeError("MT5_DEPLOY_HASH_MISMATCH: expert binding mismatch")
                        env = _read_env(run_dir)
                        env["imported_ex5_deployment"] = dict(binary_deployment)
                        artifacts.write_json(job_id, "environment.json", env)
                        artifacts.write_phase_receipt(job_id, "binary-deploy", {
                            "schema_version": "1.0",
                            "phase": "BINARY_DEPLOY",
                            "status": "PASSED",
                            "evidence": dict(binary_deployment),
                        })
                        store.update_fields(job_id, imported_ex5_execution={
                            "ea_binary_ref": binary_ref,
                            "sha256": binary_deployment.get("ea_sha256_at_execution"),
                            "bytes": binary_deployment.get("ea_bytes_at_execution"),
                            "terminal": effective_alias,
                            "terminal_build": binary_deployment.get("terminal_build_at_execution"),
                        })
                        store.publish_event(job_id, "IMPORTED_EX5_DEPLOYED", {
                            "ea_binary_ref": binary_ref,
                            "sha256": binary_deployment.get("ea_sha256_at_execution"),
                            "bytes": binary_deployment.get("ea_bytes_at_execution"),
                            "terminal_build": binary_deployment.get("terminal_build_at_execution"),
                        })
                    try:
                        tst = tester.run(
                            job_id, req["workspace"], req["ea"], effective_alias, comp["expert_name"],
                            req.get("preset", "smoke"), run_dir, req.get("set_file"),
                            normalized_config, timeout_value, False, tester_pid, login=login,
                            on_event=tester_event, resolved_config=normalized_config,
                            request_normalization=request_normalization, should_cancel=cancel_requested,
                        )
                        if binary_deployment is not None:
                            binary_deployment = binary_mgr.verify_terminal_stage(binary_deployment)
                            env = _read_env(run_dir)
                            env["imported_ex5_deployment"] = dict(binary_deployment)
                            artifacts.write_json(job_id, "environment.json", env)
                    except Exception:
                        # Stop only the exact tester PID before the handoff context restores
                        # the user's prior normal MT5 session.
                        stop = manager.terminate_role_process(job_id, "terminal", wait_seconds=10)
                        store.publish_event(job_id, "TESTER_EXCEPTION_CLEANUP", stop)
                        raise
            finally:
                if handoff_meta is not None:
                    env = _read_env(run_dir)
                    env["terminal_handoff"] = dict(handoff_meta)
                    artifacts.write_json(job_id, "environment.json", env)
                    cleanup = {
                        "schema_version": "1.0",
                        "phase": "CLEANUP",
                        "status": (
                            "PASSED" if (
                                (handoff_meta.get("was_running") and handoff_meta.get("reconnected"))
                                or (not handoff_meta.get("was_running") and not handoff_meta.get("restore_attempted"))
                            ) else "FAILED"
                        ),
                        "evidence": dict(handoff_meta),
                    }
                    artifacts.write_phase_receipt(job_id, "cleanup", cleanup)
                    store.publish_event(job_id, "TERMINAL_CLEANUP_FINISHED", {
                        "status": cleanup["status"],
                        "restore_attempted": handoff_meta.get("restore_attempted"),
                        "reconnected": handoff_meta.get("reconnected"),
                        "was_running": handoff_meta.get("was_running"),
                    })

            if handoff_meta.get("was_running") and not handoff_meta.get("reconnected"):
                tst.setdefault("diagnostics", []).append({
                    "code": "MT5_2_RECONNECT_FAILED",
                    "message": "Tester finished but the previously-running normal MT5-2 session did not reconnect within the recovery timeout",
                })

        artifacts.write_phase_receipt(job_id, "tester", {
            "schema_version": "1.0",
            "phase": "TESTER",
            "status": tst.get("status", "UNKNOWN"),
            "evidence": tst,
        })

        evidence = {
            "execution_context": tst.get("execution_context"),
            "report_value": tst.get("report_value"),
            "terminal_report_path": tst.get("terminal_report_path"),
            "report_scan": tst.get("report_scan", []),
            "requested_period": tst.get("requested_period"),
            "effective_period": tst.get("effective_period"),
            "native_selected_period": tst.get("native_selected_period"),
            "period_conformance": tst.get("period_conformance"),
            "executed_coverage": tst.get("executed_coverage"),
            "completion_reason": tst.get("completion_reason"),
        }
        evidence = {k: v for k, v in evidence.items() if v not in (None, "", [])}
        if evidence:
            store.update_fields(job_id, tester_provenance=evidence)
            env = _read_env(run_dir)
            env["tester_provenance"] = evidence
            artifacts.write_json(job_id, "environment.json", env)

        store.set_process(store.load(job_id), "terminal", None)
        job = store.load(job_id)
        if job.get("cancel_requested"):
            cleanup_receipt = artifacts.read_phase_receipt(job_id, "cleanup")
            cleanup_ok = bool(req.get("mock")) or handoff_meta is None or (cleanup_receipt or {}).get("status") == "PASSED"
            if cleanup_ok:
                store.transition(job, "CANCELLED")
                _publish_terminal(store, job_id, "CANCELLED")
            else:
                store.update_fields(
                    job_id,
                    cancel_pending_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                    cancel_cleanup_blocked={
                        "reason": "PRIOR_TERMINAL_RESTORE_UNPROVEN",
                        "cleanup_status": (cleanup_receipt or {}).get("status"),
                        "handoff": dict(handoff_meta or {}),
                    },
                )
            return
        if tst["status"] == "TIMEOUT":
            store.transition(job, "TIMEOUT")
            artifacts.write_json(job_id, "result.json", build_result(root, job_id, comp, tst))
            _publish_terminal(store, job_id, "TIMEOUT", {"completion_reason": tst.get("completion_reason")})
            return
        if tst["status"] != "COMPLETED":
            store.transition(job, "FAILED")
            result = build_result(root, job_id, comp, tst)
            artifacts.write_json(job_id, "result.json", result)
            (run_dir / "summary.md").write_text(render_summary(result), encoding="utf-8")
            _publish_terminal(store, job_id, "FAILED", {"completion_reason": tst.get("completion_reason")})
            return

        store.transition(job, "PARSING")
        store.transition(store.load(job_id), "EVALUATING")
        result = build_result(root, job_id, comp, tst)
        final = "ANOMALY" if result["anomalies"] else "PASSED"
        store.transition(store.load(job_id), final)
        result["status"] = final
        artifacts.write_json(job_id, "result.json", result)
        (run_dir / "summary.md").write_text(render_summary(result), encoding="utf-8")
        _publish_terminal(store, job_id, final)
        artifacts.retain()

    except Exception as exc:
        try:
            job = store.load(job_id)
            if job["state"] not in TERMINALS:
                store.force_terminal(job_id, "FAILED", error=str(exc))
            result = build_result(root, job_id, comp, tst)
            result["status"] = "FAILED"
            result.setdefault("tester", {}).setdefault("diagnostics", []).append({
                "code": "WORKER_EXCEPTION",
                "message": str(exc),
            })
            artifacts.write_json(job_id, "result.json", result)
            (run_dir / "worker-error.log").write_text(traceback.format_exc(), encoding="utf-8")
            _publish_terminal(store, job_id, "FAILED", {"error": str(exc)})
        except Exception:
            pass
    finally:
        if source_guard_cm is not None:
            try:
                source_guard_cm.__exit__(None, None, None)
            except Exception:
                pass
        if lock:
            try:
                lock.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            actor_cm.__exit__(None, None, None)
        except Exception:
            pass


def _phase_evidence(artifacts: ArtifactManager, job_id: str, phase: str) -> dict | None:
    receipt = artifacts.read_phase_receipt(job_id, phase)
    if not receipt:
        return None
    evidence = receipt.get("evidence")
    return evidence if isinstance(evidence, dict) else None


def build_result(root: Path, job_id: str, comp: dict | None, tst: dict | None) -> dict:
    store = JobStore(root)
    artifacts = ArtifactManager(root)
    job = store.load(job_id)
    req = job["request"]

    comp = comp or _phase_evidence(artifacts, job_id, "compile")
    tst = tst or _phase_evidence(artifacts, job_id, "tester")
    cleanup_receipt = artifacts.read_phase_receipt(job_id, "cleanup")
    config_receipt = artifacts.read_phase_receipt(job_id, "config")

    selection = job.get("execution_terminal") or {
        "requested": req.get("terminal"),
        "effective": req.get("terminal"),
        "fallback": False,
        "reason": "UNRESOLVED",
    }
    terminal_build = None
    try:
        terminal_build = TerminalInventory(root).get(selection["effective"]).build
    except Exception:
        pass

    strategy = dict((tst or {}).get("report", {}).get("metrics", {}) if tst else {})
    build_input_record: dict = {}
    build_input_path = artifacts.run_dir(job_id) / "build-input-manifest.json"
    if build_input_path.is_file():
        try:
            candidate = json.loads(build_input_path.read_text(encoding="utf-8"))
            build_input_record = candidate if isinstance(candidate, dict) else {}
        except Exception:
            build_input_record = {}
    build_input_type = str(build_input_record.get("build_input_source") or "COMPILED_SOURCE")
    imported_input = dict(build_input_record.get("imported_ex5") or {})
    if build_input_type == "IMPORTED_EX5":
        strategy["build_input_type"] = "IMPORTED_EX5"
        strategy["binary_sha256"] = imported_input.get("sha256")
        strategy["binary_bytes"] = imported_input.get("bytes")
        strategy["ea_binary_ref"] = imported_input.get("ea_binary_ref")
    fatals = (tst or {}).get("logs", {}).get("fatal_errors", []) if tst else []
    anomalies: list[str] = []
    if tst and tst.get("report", {}).get("status") != "PARSED":
        anomalies.append("REPORT_NOT_PARSED")
    if tst and strategy.get("trades") == 0:
        anomalies.append("ZERO_TRADES")
    if fatals:
        anomalies.append("FATAL_TESTER_EVENTS")
    period_status = ((tst or {}).get("period_conformance") or {}).get("status") if tst else None
    if period_status == "UNVERIFIED":
        anomalies.append("PERIOD_CONFORMANCE_UNVERIFIED")
    elif period_status == "MISMATCH":
        anomalies.append("PERIOD_CONFORMANCE_MISMATCH")

    terminal_handoff = None
    preflight_public = None
    imported_ex5_deployment = None
    env_path = store.path(job_id).parent / "environment.json"
    if env_path.exists():
        try:
            env_data = json.loads(env_path.read_text(encoding="utf-8"))
            terminal_handoff = env_data.get("terminal_handoff")
            preflight_public = env_data.get("requested_terminal_preflight")
            imported_ex5_deployment = env_data.get("imported_ex5_deployment")
            if imported_ex5_deployment and imported_ex5_deployment.get("terminal_build_at_execution"):
                terminal_build = imported_ex5_deployment.get("terminal_build_at_execution")
            elif preflight_public and preflight_public.get("build"):
                terminal_build = preflight_public.get("build")
        except Exception:
            pass
    if cleanup_receipt and isinstance(cleanup_receipt.get("evidence"), dict):
        terminal_handoff = cleanup_receipt["evidence"]

    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "job_id": job_id,
        "status": job["state"],
        "tool_version": __version__,
        "host": socket.gethostname(),
        "platform": platform.system(),
        "recorded_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "compile": comp or {"status": "NOT_RUN", "errors": 0, "warnings": 0},
        "tester": {
            "status": (tst or {}).get("status", "NOT_RUN"),
            "execution_status": (tst or {}).get("execution_status", "NOT_RUN"),
            "report_status": (tst or {}).get("report_status", "NOT_RUN"),
            "duration_seconds": (tst or {}).get("duration_seconds"),
            "fatal_errors": fatals,
            "diagnostics": (tst or {}).get("diagnostics", []),
            "execution_context": (tst or {}).get("execution_context"),
            "source": (tst or {}).get("source"),
            "command": (tst or {}).get("command"),
            "report_value": (tst or {}).get("report_value"),
            "report_scan": (tst or {}).get("report_scan", []),
            "completion_reason": (tst or {}).get("completion_reason"),
            "requested_period": (tst or {}).get("requested_period"),
            "effective_period": (tst or {}).get("effective_period"),
            "native_selected_period": (tst or {}).get("native_selected_period"),
            "period_conformance": (tst or {}).get("period_conformance"),
            "executed_coverage": (tst or {}).get("executed_coverage"),
        },
        "resolved_preset": (tst or {}).get("preset") if tst else ((config_receipt or {}).get("resolved_config")),
        "strategy": strategy,
        "anomalies": anomalies,
        "environment": {
            "requested_terminal": selection.get("requested"),
            "terminal": selection.get("effective"),
            "terminal_fallback": bool(selection.get("fallback")),
            "terminal_selection_reason": selection.get("reason"),
            "requested_symbol": selection.get("requested_symbol"),
            "resolved_symbol": selection.get("resolved_symbol"),
            "terminal_handoff": terminal_handoff,
            "build": terminal_build,
            "terminal_build_at_execution": (imported_ex5_deployment or {}).get("terminal_build_at_execution") or terminal_build,
            "ea_sha256_at_execution": (imported_ex5_deployment or {}).get("ea_sha256_at_execution") or (((comp or {}).get("immutable_ex5") or {}).get("sha256") if comp else None),
            "ea_bytes_at_execution": (imported_ex5_deployment or {}).get("ea_bytes_at_execution") or (((comp or {}).get("immutable_ex5") or {}).get("bytes") if comp else None),
            "build_input_type": build_input_type,
            "ea_binary_ref": imported_input.get("ea_binary_ref") if build_input_type == "IMPORTED_EX5" else None,
            "imported_ex5_deployment": imported_ex5_deployment,
            "environment_changed": False,
            "mock": bool(req.get("mock")),
            "execution_context": (tst or {}).get("execution_context"),
        },
        "orchestration": {
            "actor": job.get("orchestration_actor") or req.get("orchestration_actor") or {},
            "native_execution": job.get("native_execution_lease") or {},
            "native_execution_wait_seconds": job.get("native_execution_wait_seconds"),
        },
        "phase_receipts": {
            "config": "phase-config.json" if artifacts.read_phase_receipt(job_id, "config") else None,
            "compile": "phase-compile.json" if artifacts.read_phase_receipt(job_id, "compile") else None,
            "handoff": "phase-handoff.json" if artifacts.read_phase_receipt(job_id, "handoff") else None,
            "tester": "phase-tester.json" if artifacts.read_phase_receipt(job_id, "tester") else None,
            "cleanup": "phase-cleanup.json" if cleanup_receipt else None,
            "binary_deploy": "phase-binary-deploy.json" if artifacts.read_phase_receipt(job_id, "binary-deploy") else None,
        },
        "artifacts": {
            "compile_log": "compile.log",
            "tester_log": "tester.log",
            "tester_log_cursor": "tester-log-cursor.json",
            "report": (tst or {}).get("report", {}).get("report_path") if tst else None,
            "native_report": (tst or {}).get("report", {}).get("report_path") if tst else None,
            "normalized_xml": ((tst or {}).get("normalized_xml") or {}).get("path") if tst else None,
            "immutable_ex5": ((comp or {}).get("immutable_ex5") or {}).get("path") if comp else None,
            "source_snapshot": "source_snapshot",
            "build_input_manifest": "build-input-manifest.json" if (artifacts.run_dir(job_id) / "build-input-manifest.json").is_file() else None,
            "build_output_manifest": "build-output-manifest.json" if (artifacts.run_dir(job_id) / "build-output-manifest.json").is_file() else None,
            "terminal_report_path": (tst or {}).get("terminal_report_path") if tst else None,
            "imported_ex5": "compiled.ex5" if build_input_type == "IMPORTED_EX5" else None,
        },
        "build_input": {
            "type": build_input_type,
            "ea_binary_ref": imported_input.get("ea_binary_ref") if build_input_type == "IMPORTED_EX5" else None,
            "sha256": imported_input.get("sha256") if build_input_type == "IMPORTED_EX5" else (build_input_record.get("main_source") or {}).get("sha256"),
            "bytes": imported_input.get("bytes") if build_input_type == "IMPORTED_EX5" else (build_input_record.get("main_source") or {}).get("bytes"),
            "logical_path": imported_input.get("logical_path") if build_input_type == "IMPORTED_EX5" else build_input_record.get("ea_path"),
        },
    }


def render_summary(result: dict) -> str:
    s = result.get("strategy", {})
    env = result.get("environment", {})
    return (
        f"# VibeMQL5 Job {result['job_id']}\n\nStatus: **{result['status']}**\n\n"
        f"- Compile: {result.get('compile', {}).get('status')}\n"
        f"- Tester: {result.get('tester', {}).get('status')}\n"
        f"- Native execution: {result.get('tester', {}).get('execution_status')}\n"
        f"- Report: {result.get('tester', {}).get('report_status')}\n"
        f"- Completion reason: {result.get('tester', {}).get('completion_reason')}\n"
        f"- Requested terminal: {env.get('requested_terminal')}\n"
        f"- Effective terminal: {env.get('terminal')}\n"
        f"- Requested symbol: {env.get('requested_symbol')}\n"
        f"- Resolved symbol: {env.get('resolved_symbol')}\n"
        f"- Trades: {s.get('trades')}\n- Net profit: {s.get('net_profit')}\n"
        f"- Profit factor: {s.get('profit_factor')}\n- Max DD %: {s.get('max_drawdown_pct')}\n"
        f"- Anomalies: {', '.join(result.get('anomalies', [])) or 'none'}\n"
    )


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--job-id", required=True)
    a = p.parse_args(argv)
    run_job(Path(a.root), a.job_id)


if __name__ == "__main__":
    main()
