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


def failure_rows(text):
    return [json.loads(line.split('SOURCE_TEST_FAILURE ', 1)[1])
            for line in text.splitlines() if 'SOURCE_TEST_FAILURE ' in line]


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


@pytest.mark.parametrize('phase', ['setup', 'call', 'teardown'])
def test_failed_phase_is_flushed_before_later_owned_child_timeout(tmp_path, phase):
    directory = tmp_path / 'tests' / 'unit'; directory.mkdir(parents=True)
    error = "    private_local = 'PRIVATE_LOCAL_BODY'\n    raise PermissionError(13, 'PRIVATE_MESSAGE_BODY', 'PRIVATE_PATH_BODY')\n"
    fixture = error if phase == 'setup' else '    yield\n' + (error if phase == 'teardown' else '')
    call = error if phase == 'call' else '    assert True\n'
    (directory / 'test_control.py').write_text('import pytest, time\n@pytest.fixture\ndef fixture():\n' + fixture +
        'def test_failed(fixture):\n' + call + 'def test_later():\n    time.sleep(30)\n')
    junit = tmp_path / 'child.junit.xml'
    command = [sys.executable, '-m', 'pytest', '-p', 'fleet_source_progress',
               'tests/unit/test_control.py', '-q', '--junitxml=' + str(junit)]
    log = tmp_path / 'child.log'
    (tmp_path / 'child-command.json').write_text(json.dumps(command))
    with log.open('w') as output:
        process = subprocess.Popen(command, cwd=tmp_path, env=child_environment(), stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while process.poll() is None and time.monotonic() < deadline:
                text = log.read_text(); complete = text[:text.rfind('\n') + 1]
                if failure_rows(complete) and len(progress_rows(complete)) == 3: break
                time.sleep(.01)
            rows = progress_rows(complete); diagnostics = failure_rows(complete)
            assert [row['stage'] for row in rows] == ['START', 'FINISH', 'START']
            assert rows[1]['outcome'] == 'FAILED'
            assert len(diagnostics) == 1
            record = diagnostics[0]
            assert record['phase'] == phase and record['ordinal'] == 1
            assert record['exception_type'] == 'PermissionError' and record['errno'] == 13
            assert record['file'] == 'tests/unit/test_control.py' and record['function'] == 'test_failed'
            assert any(frame['file'] == 'tests/unit/test_control.py' and frame['function'] in ('fixture', 'test_failed')
                       and frame['line'] > 0 for frame in record['frames'])
            assert all(token not in json.dumps(diagnostics) for token in
                       ('PRIVATE_LOCAL_BODY', 'PRIVATE_MESSAGE_BODY', 'PRIVATE_PATH_BODY', str(tmp_path)))
            assert not junit.exists()
            with pytest.raises(subprocess.TimeoutExpired): process.wait(timeout=.1)
        finally:
            if process.poll() is None: process.kill()
            process.wait(timeout=5)
    assert process.returncode != 0 and not junit.exists()


@pytest.mark.parametrize('outcome', ['passed', 'skipped'])
def test_nonfailed_reports_emit_no_failure_diagnostic(outcome):
    lines = []
    reporter = SimpleNamespace(write_line=lines.append, flush=lambda: None)
    observer = SourceProgress(SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter)))
    report = SimpleNamespace(failed=False, skipped=outcome == 'skipped', when='call', passed=outcome == 'passed')
    observer.report(report)
    assert not failure_rows('\n'.join(lines))
    assert observer.outcome == outcome.upper()


def test_failure_diagnostic_bounds_rows_frames_and_bytes(monkeypatch):
    import fleet_source_progress as module
    lines, flushes = [], []
    reporter = SimpleNamespace(write_line=lines.append, flush=lambda: flushes.append(True))
    observer = SourceProgress(SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter)))
    monkeypatch.setattr(module, 'MAX_FAILURE_ROWS', 2)
    metadata = {'exception_type': 'RuntimeError', 'frames': [
        {'file': 'tests/unit/test_control.py', 'function': 'fixture', 'line': 1} for _ in range(30)]}
    report = SimpleNamespace(failed=True, when='setup', nodeid='tests/unit/test_control.py::test_control[PRIVATE_PARAMETER_TOKEN]',
                             _source_failure_metadata=metadata)
    for _ in range(5): observer.report(report)
    records = failure_rows('\n'.join(lines))
    assert len(records) == 3 and records[-1] == {'stage': 'TRUNCATED', 'rows_emitted': 2, 'row_limit': 2}
    assert all(len(record['frames']) <= module.MAX_FAILURE_FRAMES for record in records[:-1])
    assert all(len(line.encode('utf-8')) <= module.MAX_FAILURE_BYTES + len('SOURCE_TEST_FAILURE ') for line in lines)
    assert len(flushes) == len(lines) == 3 and observer.outcome == 'FAILED'
    assert 'PRIVATE_PARAMETER_TOKEN' not in json.dumps(records)


def test_failure_diagnostic_byte_bound_drops_oversized_frame_metadata():
    import fleet_source_progress as module
    lines = []
    reporter = SimpleNamespace(write_line=lines.append, flush=lambda: None)
    observer = SourceProgress(SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter)))
    file = 'app/vibemql5/' + 'a' * 80 + '/' + 'b' * 80 + '.py'
    frame = {'file': file, 'function': 'c' * 96, 'line': 999999}
    assert module._source_frame(**frame) == frame
    observer.report(SimpleNamespace(failed=True, when='call', nodeid='tests/unit/test_control.py::test_control',
        _source_failure_metadata={'exception_type': 'RuntimeError', 'frames': [frame] * module.MAX_FAILURE_FRAMES}))
    assert failure_rows('\n'.join(lines))[0]['frames'] == []
    assert len(lines[0].encode('utf-8')) <= module.MAX_FAILURE_BYTES + len('SOURCE_TEST_FAILURE ')
    assert observer.outcome == 'FAILED'


def test_partial_write_then_flush_failure_cannot_bypass_diagnostic_row_quota(monkeypatch):
    import fleet_source_progress as module
    lines = []
    def broken_flush(): raise RuntimeError('PRIVATE_FLUSH_BODY')
    reporter = SimpleNamespace(write_line=lines.append, flush=broken_flush)
    observer = SourceProgress(SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter)))
    monkeypatch.setattr(module, 'MAX_FAILURE_ROWS', 2)
    report = SimpleNamespace(failed=True, when='call', nodeid='tests/unit/test_control.py::test_control')
    for _ in range(20): observer.report(report)
    records = failure_rows('\n'.join(lines))
    assert len(records) == 3 and records[-1] == {'stage': 'TRUNCATED', 'rows_emitted': 2, 'row_limit': 2}
    assert observer.failure_rows == 2 and observer.outcome == 'FAILED' and report.failed is True
    assert 'PRIVATE_FLUSH_BODY' not in json.dumps(records)


@pytest.mark.parametrize('nodeid', [None, '/private/test_secret.py::test_secret',
                                   'tests/unit/../private.py::test_secret', 'tests/unit/test_control.py::SECRET_FUNCTION'])
def test_failure_diagnostic_omits_nonliteral_ids(nodeid):
    lines = []
    reporter = SimpleNamespace(write_line=lines.append, flush=lambda: None)
    observer = SourceProgress(SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name: reporter)))
    observer.report(SimpleNamespace(failed=True, when='call', nodeid=nodeid))
    record = failure_rows('\n'.join(lines))[0]
    assert record['exception_type'] == 'UNKNOWN' and 'file' not in record and 'function' not in record
    assert 'secret' not in json.dumps(record).lower()


def test_diagnostic_formatter_and_reporter_failure_preserve_original_failed_outcome(monkeypatch):
    import fleet_source_progress as module
    def broken(*args, **kwargs): raise RuntimeError('PRIVATE_FORMATTER_BODY')
    observer = SourceProgress(SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name:
        SimpleNamespace(write_line=broken, flush=broken))))
    monkeypatch.setattr(module.json, 'dumps', broken)
    report = SimpleNamespace(failed=True, when='call', nodeid='tests/unit/test_control.py::test_control')
    observer.report(report)
    assert observer.outcome == 'FAILED' and report.failed is True


def test_metadata_never_stringifies_exception_and_preserves_unknown_classification(tmp_path):
    import fleet_source_progress as module
    class PrivateError(Exception):
        def __str__(self): raise AssertionError('PRIVATE_STR_CALLED')
        def __repr__(self): raise AssertionError('PRIVATE_REPR_CALLED')
    try: raise PrivateError('PRIVATE_MESSAGE_BODY')
    except PrivateError:
        excinfo = pytest.ExceptionInfo.from_current()
    item = SimpleNamespace(config=SimpleNamespace(rootpath=tmp_path))
    metadata = module._failure_metadata(item, SimpleNamespace(excinfo=excinfo))
    assert metadata['exception_type'] == 'UNKNOWN' and metadata['frames'] == []
    assert 'PRIVATE' not in json.dumps(metadata)


def test_makereport_metadata_failure_returns_original_report(monkeypatch):
    import fleet_source_progress as module
    report = SimpleNamespace(failed=True)
    def broken(*args): raise RuntimeError('PRIVATE_HOOK_BODY')
    monkeypatch.setattr(module, '_failure_metadata', broken)
    hook = module.pytest_runtest_makereport(SimpleNamespace(), SimpleNamespace())
    assert next(hook) is None
    with pytest.raises(StopIteration): hook.send(SimpleNamespace(get_result=lambda: report))
    assert report.failed is True and report._source_failure_metadata == {'exception_type': 'UNKNOWN', 'frames': []}
