"""Opt-in source-harness timing; no fixture locals or parameter values are emitted."""
import json
import re
import time
from pathlib import Path

import pytest

MAX_ROWS = 4096
MAX_FAILURE_ROWS = 64
MAX_FAILURE_FRAMES = 8
MAX_FAILURE_BYTES = 2048
_progress = None


def _source_frame(file, function, line):
    if (type(file) is not str or len(file) > 192
            or re.fullmatch(r'(?:tests/unit|app/vibemql5)(?:/[A-Za-z0-9_]{1,96}){0,6}/[A-Za-z0-9_]{1,96}\.py', file) is None
            or type(function) is not str or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,95}', function) is None
            or type(line) is not int or not 1 <= line <= 1_000_000):
        return None
    return {'file': file, 'function': function, 'line': line}


def _failure_metadata(item, call):
    value = {'exception_type': 'UNKNOWN', 'frames': []}
    if call.excinfo is None: return value
    error = call.excinfo.value
    kind = type(error)
    if (kind.__module__ in ('builtins', '_pytest.outcomes') or re.fullmatch(r'vibemql5(?:\.[A-Za-z_][A-Za-z0-9_]*)+', kind.__module__)):
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,95}', kind.__name__): value['exception_type'] = kind.__name__
    if isinstance(error, OSError) and type(error.errno) is int and -4095 <= error.errno <= 4095:
        value['errno'] = error.errno
    for index, entry in enumerate(reversed(call.excinfo.traceback)):
        if index >= 64 or len(value['frames']) >= MAX_FAILURE_FRAMES: break
        try: file = Path(entry.path).relative_to(item.config.rootpath).as_posix()
        except ValueError: continue
        frame = _source_frame(file, entry.frame.code.name, entry.lineno + 1)
        if frame is not None: value['frames'].append(frame)
    value['frames'].reverse()
    return value


class SourceProgress:
    def __init__(self, config):
        self.config, self.origin = config, time.monotonic()
        self.started, self.ordinal, self.rows, self.truncated = None, 0, 0, False
        self.outcome = 'UNKNOWN'
        self.failure_rows, self.failure_truncated = 0, False

    @staticmethod
    def literal(nodeid):
        if type(nodeid) is not str or len(nodeid) > 4096: return {}
        parts = nodeid.split('::')
        function = parts[-1].split('[', 1)[0]
        if (len(parts) < 2 or re.fullmatch(r'tests/unit/[A-Za-z0-9_]{1,96}\.py', parts[0]) is None
                or re.fullmatch(r'test_[A-Za-z0-9_]{1,96}', function) is None): return {}
        return {'file': parts[0], 'function': function}

    def emit(self, stage, nodeid):
        reporter = self.config.pluginmanager.get_plugin('terminalreporter')
        if reporter is None: return
        if self.rows >= MAX_ROWS:
            if not self.truncated:
                self.truncated = True
                reporter.write_line('SOURCE_TEST_PROGRESS ' + json.dumps(
                    {'stage': 'TRUNCATED', 'rows_emitted': self.rows, 'row_limit': MAX_ROWS}, sort_keys=True))
                reporter.flush()
            return
        now = time.monotonic()
        row = {'stage': stage, 'ordinal': self.ordinal, 'suite_elapsed_ms': max(0, int((now - self.origin) * 1000)),
               'test_elapsed_ms': max(0, int((now - self.started) * 1000)), **self.literal(nodeid)}
        if stage == 'FINISH': row['outcome'] = self.outcome
        self.rows += 1
        reporter.write_line('SOURCE_TEST_PROGRESS ' + json.dumps(row, sort_keys=True))
        reporter.flush()

    def start(self, nodeid):
        self.ordinal += 1
        self.started, self.outcome = time.monotonic(), 'UNKNOWN'
        self.emit('START', nodeid)

    def report(self, report):
        if report.failed: self.outcome = 'FAILED'
        elif report.skipped and self.outcome != 'FAILED': self.outcome = 'SKIPPED'
        elif report.when == 'call' and report.passed and self.outcome == 'UNKNOWN': self.outcome = 'PASSED'
        if report.failed: self.failure(report)

    def failure(self, report):
        # Diagnostics cannot replace the original report or change its outcome.
        try:
            reporter = self.config.pluginmanager.get_plugin('terminalreporter')
            if reporter is None: return
            if self.failure_rows >= MAX_FAILURE_ROWS:
                if not self.failure_truncated:
                    self.failure_truncated = True
                    reporter.write_line('SOURCE_TEST_FAILURE ' + json.dumps(
                        {'stage': 'TRUNCATED', 'rows_emitted': self.failure_rows, 'row_limit': MAX_FAILURE_ROWS}, sort_keys=True))
                    reporter.flush()
                return
            metadata = getattr(report, '_source_failure_metadata', {})
            row = {'ordinal': self.ordinal, 'phase': report.when if report.when in ('setup', 'call', 'teardown') else 'UNKNOWN',
                   'exception_type': 'UNKNOWN', 'frames': [], **self.literal(getattr(report, 'nodeid', None))}
            if type(metadata) is dict:
                kind = metadata.get('exception_type')
                if type(kind) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,95}', kind): row['exception_type'] = kind
                number = metadata.get('errno')
                if type(number) is int and -4095 <= number <= 4095: row['errno'] = number
                frames = metadata.get('frames', [])
                if type(frames) is list:
                    for frame in frames[:MAX_FAILURE_FRAMES]:
                        if type(frame) is dict:
                            safe = _source_frame(frame.get('file'), frame.get('function'), frame.get('line'))
                            if safe is not None: row['frames'].append(safe)
            encoded = json.dumps(row, sort_keys=True)
            if len(encoded.encode('utf-8')) > MAX_FAILURE_BYTES:
                row['frames'] = []
                encoded = json.dumps(row, sort_keys=True)
            self.failure_rows += 1
            reporter.write_line('SOURCE_TEST_FAILURE ' + encoded)
            reporter.flush()
        except BaseException:
            pass

    def finish(self, nodeid): self.emit('FINISH', nodeid)


def pytest_configure(config):
    global _progress
    _progress = SourceProgress(config)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        try: report._source_failure_metadata = _failure_metadata(item, call)
        except BaseException: report._source_failure_metadata = {'exception_type': 'UNKNOWN', 'frames': []}


def pytest_runtest_logstart(nodeid, location): _progress.start(nodeid)
def pytest_runtest_logreport(report): _progress.report(report)
def pytest_runtest_logfinish(nodeid, location): _progress.finish(nodeid)
