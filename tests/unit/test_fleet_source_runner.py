"""Bounded proof orchestration only; these mocks do not certify a host."""
import importlib.util
import json
import os
import subprocess
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
    def run(command, *, stdout, timeout, **kwargs):
        case = Path(stdout.name).stem
        attempts.append((case, timeout, command))
        if case == 'full-unit' and outcome == 'full-unit-timeout':
            raise subprocess.TimeoutExpired(command, timeout)
        stdout.write('SYNTHETIC_RUNNER_FIXTURE_ONLY\n')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(runner, 'subprocess', SimpleNamespace(run=run,
        STDOUT=subprocess.STDOUT, TimeoutExpired=subprocess.TimeoutExpired))
    output = tmp_path / 'receipt'
    code = runner.main(['--output', str(output), *(['--require-windows'] if platform_name == 'nt' else [])])
    summary = json.loads((output / 'summary.json').read_text())
    assert [item[0] for item in attempts] == case_names
    assert [item['case'] for item in summary['cases']] == case_names
    assert attempts[0][1] == 600
    assert all(item[1] == 120 for item in attempts[1:])
    assert sum(item[1] for item in attempts) <= 1080
    assert '-v' in attempts[0][2] and 'faulthandler_timeout=90' in attempts[0][2]
    assert summary['physical_qualification'] == 'NOT_RUN'
    assert summary['source_unchanged_during_run'] is (outcome != 'source-changed')
    assert summary['status'] == ('PASS' if outcome == 'pass' else 'FAIL')
    assert code == (0 if outcome == 'pass' else 1)
    assert summary['cases'][0]['timed_out'] is (outcome == 'full-unit-timeout')
    assert summary['cases'][0]['exit_code'] == (124 if outcome == 'full-unit-timeout' else 0)
    for case in case_names:
        log = (output / (case + '.log')).read_text()
        assert 'SOURCE_CASE_STARTED' in log and 'SOURCE_CASE_FINISHED' in log
