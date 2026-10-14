"""Bounded proof orchestration only; these mocks do not certify a host."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('platform_name,case_names', [
    ('posix', ['full-unit', 'b1-portable']),
    ('nt', ['full-unit', 'b1-portable', 'q1-harmless', 'g03a-harmless', 'b1-harmless']),
])
@pytest.mark.parametrize('outcome', ['pass', 'full-unit-timeout', 'source-changed'])
def test_source_runner_keeps_required_proofs_and_honest_manifest(tmp_path, monkeypatch, platform_name, case_names, outcome):
    path = Path(__file__).resolve().parents[1] / 'proofs' / 'fleet_v1' / 'run_source.py'
    spec = importlib.util.spec_from_file_location('fleet_source_runner_fixture', path)
    runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner, 'os', SimpleNamespace(name=platform_name, environ={}, pathsep=os.pathsep))
    monkeypatch.setattr(runner, 'git_value', lambda argument: 'fixture-tree' if argument == 'HEAD^{tree}' else 'fixture-head')
    manifests = iter([{'fixture.py': 'before'}, {'fixture.py': 'changed' if outcome == 'source-changed' else 'before'}])
    monkeypatch.setattr(runner, 'source_manifest', lambda: next(manifests))
    attempts = []
    def run_case(case, command, destination, environment, timeout):
        attempts.append((case, timeout, command))
        timed_out = case == 'full-unit' and outcome == 'full-unit-timeout'
        (destination / (case + '.log')).write_text('SOURCE_CASE_STARTED\nSYNTHETIC_RUNNER_FIXTURE_ONLY\nSOURCE_CASE_FINISHED\n')
        return {'case': case, 'command': command, 'exit_code': 124 if timed_out else 0,
                'timed_out': timed_out, 'status': 'TIMED_OUT' if timed_out else 'PASS'}
    monkeypatch.setattr(runner, 'run_case', run_case)
    output = tmp_path / 'receipt'
    code = runner.main(['--output', str(output), *(['--require-windows'] if platform_name == 'nt' else [])])
    summary = json.loads((output / 'summary.json').read_text())
    assert [item[0] for item in attempts] == case_names
    assert [item['case'] for item in summary['cases']] == case_names
    assert attempts[0][1] == 900
    assert all(item[1] == 120 for item in attempts[1:])
    assert sum(item[1] for item in attempts) <= 1380
    assert '-v' in attempts[0][2] and 'faulthandler_timeout=90' in attempts[0][2]
    assert attempts[0][2].count('fleet_source_progress') == 1
    assert all('fleet_source_progress' not in item[2] for item in attempts[1:])
    assert not any(argument.startswith('--capture') for argument in attempts[0][2])
    assert summary['physical_qualification'] == 'NOT_RUN'
    assert summary['source_unchanged_during_run'] is (outcome != 'source-changed')
    assert summary['status'] == ('PASS' if outcome == 'pass' else 'FAIL')
    assert code == (0 if outcome == 'pass' else 1)
    assert summary['cases'][0]['timed_out'] is (outcome == 'full-unit-timeout')
    assert summary['cases'][0]['exit_code'] == (124 if outcome == 'full-unit-timeout' else 0)
    for case in case_names:
        log = (output / (case + '.log')).read_text()
        assert 'SOURCE_CASE_STARTED' in log and 'SOURCE_CASE_FINISHED' in log


def load_runner():
    path = Path(__file__).resolve().parents[1] / 'proofs' / 'fleet_v1' / 'run_source.py'
    spec = importlib.util.spec_from_file_location('fleet_source_runner_control', path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


@pytest.mark.parametrize('outcome', ['pass', 'fail', 'timeout'])
def test_real_disposable_child_keeps_before_receipt_and_direct_closure(tmp_path, monkeypatch, outcome):
    runner = load_runner()
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    monkeypatch.setattr(runner, 'HEARTBEAT_SECONDS', .05)
    code = ("import json, pathlib, sys, time; "
            "receipt=json.loads(pathlib.Path('control.receipt.json').read_text()); "
            "assert receipt['status']=='RUNNING' and receipt['exit_code'] is None; "
            "print('BEFORE_DISPATCH_RECEIPT_OBSERVED', flush=True); " +
            ("time.sleep(30)" if outcome == 'timeout' else "sys.exit(" + ('7' if outcome == 'fail' else '0') + ")"))
    receipt = runner.run_case('control', [sys.executable, '-c', code], tmp_path, dict(os.environ),
                              2 if outcome == 'timeout' else 10)
    saved = json.loads((tmp_path / 'control.receipt.json').read_text())
    assert saved == receipt
    assert receipt['status'] == {'pass': 'PASS', 'fail': 'FAIL', 'timeout': 'TIMED_OUT'}[outcome]
    assert receipt['exit_code'] == {'pass': 0, 'fail': 7, 'timeout': 124}[outcome]
    assert receipt['timed_out'] is (outcome == 'timeout')
    assert receipt['child']['pid'] > 0 and receipt['child']['creation_identity']
    assert receipt['direct_child_closure'] == 'EXITED'
    assert receipt['descendant_closure'] == 'UNKNOWN' and receipt['closure_scope'] == 'DIRECT_CHILD_ONLY'
    assert 'BEFORE_DISPATCH_RECEIPT_OBSERVED' in (tmp_path / 'control.log').read_text()
    assert receipt['started_utc'] <= receipt['finished_utc']
    if outcome == 'timeout':
        assert receipt['child_exit_code'] != 0 and receipt['heartbeat_utc']
        assert not Path(receipt['semantic_checkpoint']).exists()  # Heartbeat alone is not test progress.


@pytest.mark.parametrize('diagnostic_failure', ['none', 'evidence', 'cleanup'])
def test_interrupt_closes_owned_child_and_preserves_original_interrupt(tmp_path, monkeypatch, diagnostic_failure):
    runner = load_runner()
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    actual_popen = subprocess.Popen
    children = []
    def popen(*args, **kwargs):
        child = actual_popen(*args, **kwargs)
        children.append(child)
        actual_wait = child.wait
        calls = 0
        def wait(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1: raise KeyboardInterrupt()
            code = actual_wait(*args, **kwargs)
            if diagnostic_failure == 'cleanup': raise subprocess.TimeoutExpired(args, 5)
            return code
        child.wait = wait
        return child
    monkeypatch.setattr(runner.subprocess, 'Popen', popen)
    actual_checkpoint = runner.checkpoint
    def checkpoint(path, receipt):
        if diagnostic_failure == 'evidence' and receipt.get('status') == 'INTERRUPTED':
            raise OSError('CONTROLLED_EVIDENCE_FAILURE')
        actual_checkpoint(path, receipt)
    monkeypatch.setattr(runner, 'checkpoint', checkpoint)
    with pytest.raises(KeyboardInterrupt) as interrupted:
        runner.run_case('interrupted', [sys.executable, '-c', 'import time; time.sleep(30)'],
                        tmp_path, dict(os.environ), 10)
    receipt = json.loads((tmp_path / 'interrupted.receipt.json').read_text())
    if diagnostic_failure == 'evidence':
        assert receipt['status'] == 'RUNNING' and receipt['direct_child_closure'] == 'UNKNOWN'
        assert any('SOURCE_CASE_FINAL_EVIDENCE_FAILED:OSError' in note for note in interrupted.value.__notes__)
        assert children[0].returncode is not None
        return
    assert receipt['status'] == 'INTERRUPTED' and receipt['error_type'] == 'KeyboardInterrupt'
    assert receipt['exit_code'] is None and not receipt['timed_out']
    assert children[0].returncode is not None
    assert receipt['direct_child_closure'] == ('UNKNOWN' if diagnostic_failure == 'cleanup' else 'EXITED')
    assert receipt['descendant_closure'] == 'UNKNOWN'
    if diagnostic_failure == 'cleanup': assert receipt['cleanup_error_type'] == 'TimeoutExpired'
    assert 'SOURCE_CASE_FINISHED' in (tmp_path / 'interrupted.log').read_text()


def test_abrupt_runner_loss_retains_source_before_and_refuses_reuse(tmp_path):
    runner = load_runner()
    output = tmp_path / 'abrupt'
    command = [sys.executable, '-c',
        "import importlib.util, os, pathlib; "
        "spec=importlib.util.spec_from_file_location('runner', " + repr(str(Path(runner.__file__))) + "); "
        "runner=importlib.util.module_from_spec(spec); spec.loader.exec_module(runner); "
        "runner.ROOT=pathlib.Path(" + repr(str(tmp_path)) + "); "
        "runner.git_value=lambda argument: 'fixture-head'; "
        "runner.source_manifest=lambda: {'frozen.py':'fixture-hash'}; "
        "runner.run_case=lambda *args: os._exit(23); "
        "runner.main(['--output', " + repr(str(output)) + ", '--unit-only'])"]
    result = subprocess.run(command, timeout=10, check=False,
        env={key: value for key, value in os.environ.items() if key != 'FLEET_V1_EXPECTED_SHA'})
    assert result.returncode == 23
    before_bytes = (output / 'summary.json').read_bytes()
    summary = json.loads(before_bytes)
    assert summary['status'] == 'RUNNING' and summary['cases'] == []
    assert summary['source_before'] == {'frozen.py': 'fixture-hash'}
    with pytest.raises(SystemExit, match='SOURCE_OUTPUT_ALREADY_HAS_RECEIPT'):
        runner.main(['--output', str(output)])
    assert (output / 'summary.json').read_bytes() == before_bytes
    (output / 'summary.json').unlink()
    (output / 'control.receipt.json').write_text('{}')
    with pytest.raises(SystemExit, match='SOURCE_OUTPUT_ALREADY_HAS_RECEIPT'):
        runner.main(['--output', str(output)])
    assert (output / 'control.receipt.json').read_text() == '{}'


def test_unit_only_keeps_unit_cap_and_omits_platform_proofs(tmp_path, monkeypatch):
    monkeypatch.delenv('FLEET_V1_EXPECTED_SHA', raising=False)
    runner = load_runner()
    monkeypatch.setattr(runner, 'git_value', lambda argument: 'fixture-head')
    monkeypatch.setattr(runner, 'source_manifest', lambda: {})
    attempts = []
    def run_case(name, command, destination, environment, timeout):
        assert json.loads((destination / 'summary.json').read_text())['source_before'] == {}
        attempts.append((name, command, timeout))
        return {'exit_code': 0}
    monkeypatch.setattr(runner, 'run_case', run_case)
    assert runner.main(['--unit-only', '--output', str(tmp_path)]) == 0
    assert len(attempts) == 1 and attempts[0][0] == 'full-unit' and attempts[0][2] == 900
    assert '-p' in attempts[0][1] and 'fleet_source_progress' in attempts[0][1]
    assert 'faulthandler_timeout=90' in attempts[0][1]
    assert any(value.startswith('--junitxml=') for value in attempts[0][1])


def test_semantic_checkpoint_is_opt_in_safe_and_diagnostic_failure_does_not_mask(tmp_path, monkeypatch):
    import fleet_source_progress as progress
    lines = []
    reporter = SimpleNamespace(write_line=lines.append, flush=lambda: None)
    config = SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter))
    monkeypatch.delenv('FLEET_SOURCE_PROGRESS_PATH', raising=False)
    assert progress.SourceProgress(config).checkpoint_path is None
    monkeypatch.setenv('FLEET_SOURCE_PROGRESS_PATH', str(tmp_path / 'control.progress.json'))
    observer = progress.SourceProgress(config, os.environ.get('FLEET_SOURCE_PROGRESS_PATH'))
    observer.start('tests/unit/test_control.py::test_control[PRIVATE_PARAMETER_TOKEN]')
    initial = json.loads(observer.checkpoint_path.read_text())
    assert initial['stage'] == 'START' and initial['ordinal'] == 1 and initial['pid'] == os.getpid()
    observer.report(SimpleNamespace(failed=True, skipped=False, when='call', nodeid='tests/unit/test_control.py::test_control'))
    observer.finish('tests/unit/test_control.py::test_control')
    final = json.loads(observer.checkpoint_path.read_text())
    assert final['stage'] == 'FINISH' and final['outcome'] == 'FAILED'
    assert 'PRIVATE_PARAMETER_TOKEN' not in json.dumps(initial)
    monkeypatch.setenv('FLEET_SOURCE_PROGRESS_PATH', str(tmp_path / 'missing' / 'control.progress.json'))
    observer = progress.SourceProgress(config, os.environ.get('FLEET_SOURCE_PROGRESS_PATH'))
    observer.start('tests/unit/test_control.py::test_control')
    observer.report(SimpleNamespace(failed=True, skipped=False, when='call', nodeid='tests/unit/test_control.py::test_control'))
    observer.finish('tests/unit/test_control.py::test_control')
    assert observer.outcome == 'FAILED' and observer.checkpoint_failed
    assert sum('SOURCE_CHECKPOINT_FAILED' in line for line in lines) == 1


@pytest.mark.parametrize('failure', ['log-open', 'log-write-and-close'])
def test_log_failure_preserves_primary_error_and_before_dispatch_state(tmp_path, monkeypatch, failure):
    runner = load_runner()
    primary = OSError('CONTROLLED_PRIMARY_LOG_FAILURE')
    original_open = Path.open
    def broken_open(path, *args, **kwargs):
        if path.name != 'log-control.log': return original_open(path, *args, **kwargs)
        if failure == 'log-open': raise primary
        def write(*args): raise primary
        def close(): raise OSError('CONTROLLED_SECONDARY_CLOSE_FAILURE')
        return SimpleNamespace(write=write, flush=lambda: None, close=close, closed=False)
    monkeypatch.setattr(Path, 'open', broken_open)
    with pytest.raises(OSError) as error:
        runner.run_case('log-control', [sys.executable, '-c', "raise AssertionError('MUST_NOT_DISPATCH')"],
                        tmp_path, dict(os.environ), 10)
    assert error.value is primary
    receipt = json.loads((tmp_path / 'log-control.receipt.json').read_text())
    assert receipt['status'] == 'ERROR' and receipt['child'] is None
    assert receipt['direct_child_closure'] == 'NOT_DISPATCHED' and receipt['log_evidence'] == 'UNKNOWN'


def test_final_manifest_failure_is_terminal_error_and_keeps_completed_cases(tmp_path, monkeypatch):
    monkeypatch.delenv('FLEET_V1_EXPECTED_SHA', raising=False)
    runner = load_runner()
    monkeypatch.setattr(runner, 'git_value', lambda argument: 'fixture-head')
    observations = 0
    def manifest():
        nonlocal observations
        observations += 1
        if observations == 2: raise OSError('CONTROLLED_FINAL_MANIFEST_FAILURE')
        return {'frozen.py': 'fixture-hash'}
    monkeypatch.setattr(runner, 'source_manifest', manifest)
    monkeypatch.setattr(runner, 'run_case', lambda name, *args: {'case': name, 'exit_code': 0})
    with pytest.raises(OSError, match='CONTROLLED_FINAL_MANIFEST_FAILURE'):
        runner.main(['--output', str(tmp_path), '--unit-only'])
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['status'] == 'ERROR' and summary['error_type'] == 'OSError'
    assert summary['cases'] == [{'case': 'full-unit', 'exit_code': 0}]
    assert summary['source_before'] == {'frozen.py': 'fixture-hash'}
    assert summary['active_case']['case'] == 'full-unit' and 'finished_utc' in summary
