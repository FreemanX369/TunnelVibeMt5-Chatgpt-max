"""Real disposable pytest children; no Windows or runtime qualification."""
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

from fleet_source_progress import SourceProgress


def progress_rows(text):
    return [json.loads(line.split('SOURCE_TEST_PROGRESS ', 1)[1])
            for line in text.splitlines() if 'SOURCE_TEST_PROGRESS ' in line]


def live_progress_rows(text):
    # A concurrently written final row is not ready until its newline exists.
    return progress_rows(text[:text.rfind('\n') + 1])


def child_environment():
    return {**{key: value for key, value in os.environ.items()
               if key not in ('PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'PYTEST_CURRENT_TEST')},
            'PYTHONPATH': str(Path(__file__).parent), 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}


@pytest.mark.parametrize('outcome', ['passed', 'failed', 'skipped'])
@pytest.mark.parametrize('enabled', [False, True])
def test_real_pytest_progress_is_opt_in_and_preserves_outcome(tmp_path, outcome, enabled):
    directory = tmp_path / 'tests' / 'unit'; directory.mkdir(parents=True)
    source = directory / 'test_control.py'
    body = {'passed': 'assert True', 'failed': "raise RuntimeError('CONTROLLED_FAILURE')",
            'skipped': "pytest.skip('CONTROLLED_SKIP')"}[outcome]
    source.write_text("import pytest\n@pytest.mark.parametrize('value', ['PRIVATE_PARAMETER_TOKEN'])\n"
                      "def test_control(value):\n    " + body + '\n')
    command = [sys.executable, '-m', 'pytest', *(['-p', 'fleet_source_progress'] if enabled else []),
               'tests/unit/test_control.py', '-q', '--junitxml=' + str(tmp_path / 'child.junit.xml')]
    (tmp_path / 'child-command.json').write_text(json.dumps(command))
    with (tmp_path / 'child.log').open('w') as output:
        result = subprocess.run(command, cwd=tmp_path, env=child_environment(),
            stdout=output, stderr=subprocess.STDOUT, timeout=30, check=False)
    rows = progress_rows((tmp_path / 'child.log').read_text())
    assert result.returncode == (1 if outcome == 'failed' else 0)
    cases = list(ET.parse(tmp_path / 'child.junit.xml').getroot().iter('testcase'))
    assert len(cases) == 1 and (cases[0].find('failure') is not None) is (outcome == 'failed')
    assert (cases[0].find('skipped') is not None) is (outcome == 'skipped')
    if enabled:
        assert [row['stage'] for row in rows] == ['START', 'FINISH']
        assert all(row['file'] == 'tests/unit/test_control.py' and row['function'] == 'test_control' for row in rows)
        assert rows[1]['outcome'] == outcome.upper() and rows[0]['ordinal'] == rows[1]['ordinal'] == 1
        assert rows[1]['suite_elapsed_ms'] >= rows[0]['suite_elapsed_ms'] >= 0
        assert rows[1]['test_elapsed_ms'] >= rows[0]['test_elapsed_ms'] >= 0
        assert 'PRIVATE_PARAMETER_TOKEN' not in json.dumps(rows)
    else: assert not rows


def test_parent_timeout_keeps_flushed_unfinished_start_and_original_raw_handler_dump(tmp_path):
    directory = tmp_path / 'tests' / 'unit'; directory.mkdir(parents=True)
    (directory / 'test_control.py').write_text('import time\ndef test_control():\n    time.sleep(30)\n')
    command = [sys.executable, '-m', 'pytest', '-p', 'fleet_source_progress', 'tests/unit/test_control.py',
               '-q', '-o', 'faulthandler_timeout=0.1']
    log = tmp_path / 'control.log'
    (tmp_path / 'child-command.json').write_text(json.dumps(command))
    with log.open('w') as output:
        process = subprocess.Popen(command, cwd=tmp_path, env=child_environment(),
            stdout=output, stderr=subprocess.STDOUT)
        try:
            # Interpreter startup is outside the controlled timeout. Observe
            # actual flushed START first, with its own bounded setup wait.
            deadline = time.monotonic() + 20
            while not live_progress_rows(log.read_text()) and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            assert live_progress_rows(log.read_text()), 'CONTROLLED_CHILD_START_NOT_OBSERVED'
            with pytest.raises(subprocess.TimeoutExpired): process.wait(timeout=.5)
        finally:
            if process.poll() is None: process.kill()
            process.wait(timeout=5)
    text = log.read_text(); rows = progress_rows(text)
    assert [row['stage'] for row in rows] == ['START']
    assert rows[0]['file'] == 'tests/unit/test_control.py' and rows[0]['function'] == 'test_control'
    assert 'Timeout (' in text and 'test_control.py' in text
    assert not any(argument.startswith('--capture') for argument in command)


@pytest.mark.parametrize('stage', ['setup', 'teardown'])
def test_real_pytest_progress_preserves_fixture_failure_and_junit_error(tmp_path, stage):
    directory = tmp_path / 'tests' / 'unit'; directory.mkdir(parents=True)
    body = ("    raise RuntimeError('CONTROLLED_SETUP_FAILURE')\n" if stage == 'setup' else
            "    yield\n    raise RuntimeError('CONTROLLED_TEARDOWN_FAILURE')\n")
    (directory / 'test_control.py').write_text('import pytest\n@pytest.fixture\ndef fixture():\n' + body +
        'def test_control(fixture):\n    assert True\n')
    command = [sys.executable, '-m', 'pytest', '-p', 'fleet_source_progress', 'tests/unit/test_control.py',
               '-q', '--junitxml=' + str(tmp_path / 'child.junit.xml')]
    (tmp_path / 'child-command.json').write_text(json.dumps(command))
    with (tmp_path / 'child.log').open('w') as output:
        result = subprocess.run(command, cwd=tmp_path, env=child_environment(),
            stdout=output, stderr=subprocess.STDOUT, timeout=30, check=False)
    rows = progress_rows((tmp_path / 'child.log').read_text())
    assert result.returncode == 1 and [row['stage'] for row in rows] == ['START', 'FINISH']
    assert rows[1]['outcome'] == 'FAILED'
    cases = list(ET.parse(tmp_path / 'child.junit.xml').getroot().iter('testcase'))
    assert len(cases) == 1 and cases[0].find('error') is not None


@pytest.mark.parametrize('nodeid', [None, [], {}, 'PRIVATE_PARAMETER_TOKEN', '/private/test_secret.py::test_secret',
                                  'tests/unit/../private.py::test_secret', 'tests/unit/test_control.py::PRIVATE_FUNCTION_TOKEN',
                                  'tests/unit/test_control.py::test_' + 'x' * 97])
def test_source_progress_omits_malformed_or_nonliteral_ids(nodeid):
    assert SourceProgress.literal(nodeid) == {}


def test_source_progress_keeps_literal_function_and_omits_all_parameter_data():
    assert SourceProgress.literal('tests/unit/test_control.py::TestClass::test_control[PRIVATE_PARAMETER_TOKEN]') == {
        'file': 'tests/unit/test_control.py', 'function': 'test_control'}


def test_source_progress_caps_rows_flushes_and_marks_truncation(monkeypatch):
    import fleet_source_progress as module
    lines, flushes = [], []
    reporter = SimpleNamespace(write_line=lines.append, flush=lambda: flushes.append(True))
    config = SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter))
    monkeypatch.setattr(module, 'MAX_ROWS', 2)
    observer = SourceProgress(config)
    for _ in range(5): observer.start('tests/unit/test_control.py::test_control[PRIVATE_PARAMETER_TOKEN]')
    rows = progress_rows('\n'.join(lines))
    assert [row['stage'] for row in rows] == ['START', 'START', 'TRUNCATED']
    assert rows[-1] == {'stage': 'TRUNCATED', 'rows_emitted': 2, 'row_limit': 2}
    assert observer.ordinal == 5 and len(flushes) == len(lines) == 3
    assert 'PRIVATE_PARAMETER_TOKEN' not in json.dumps(rows)


def test_source_progress_finish_without_call_report_is_honestly_unknown():
    lines = []
    reporter = SimpleNamespace(write_line=lines.append, flush=lambda: None)
    observer = SourceProgress(SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter)))
    observer.start('tests/unit/test_control.py::test_control')
    observer.finish('tests/unit/test_control.py::test_control')
    assert progress_rows('\n'.join(lines))[-1]['outcome'] == 'UNKNOWN'


def test_live_progress_requires_newline_but_rejects_malformed_complete_rows():
    partial = 'SOURCE_TEST_PROGRESS {"stage":"START"'
    assert live_progress_rows(partial) == []
    assert live_progress_rows(partial + '}\n') == [{'stage': 'START'}]
    with pytest.raises(json.JSONDecodeError): live_progress_rows(partial + '\n')
    with pytest.raises(json.JSONDecodeError): progress_rows(partial)
