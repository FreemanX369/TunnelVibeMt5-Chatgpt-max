"""Opt-in source-harness timing; no fixture locals or parameter values are emitted."""
import json
import re
import time

MAX_ROWS = 4096
_progress = None


class SourceProgress:
    def __init__(self, config):
        self.config, self.origin = config, time.monotonic()
        self.started, self.ordinal, self.rows, self.truncated = None, 0, 0, False
        self.outcome = 'UNKNOWN'

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

    def finish(self, nodeid): self.emit('FINISH', nodeid)


def pytest_configure(config):
    global _progress
    _progress = SourceProgress(config)


def pytest_runtest_logstart(nodeid, location): _progress.start(nodeid)
def pytest_runtest_logreport(report): _progress.report(report)
def pytest_runtest_logfinish(nodeid, location): _progress.finish(nodeid)
