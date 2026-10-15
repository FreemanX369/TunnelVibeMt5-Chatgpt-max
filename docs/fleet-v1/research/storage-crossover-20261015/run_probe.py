"""One declared C1/D/C2 experiment; no original test or product budget changes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
SELECTED = (
    'tests/unit/test_tip064_capacity_https.py::test_scope_broken_diagnostic_and_restore_keep_original_unknown_and_armed[record]',
    'tests/unit/test_tip064_integration.py::test_long_fixture_preserves_wrapper_failure_after_terminal_ack[timeout-1000]',
    'tests/unit/test_tip064_integration.py::test_actual_tls_client_possession_to_async_guarded_source_two_commits_and_phase_ack',
    'tests/unit/test_tip077_capacity_entry_watchdog.py::test_positive_capacity_entry_observation_preserves_callback_union_under_finite_schedule',
)
IO_PROBE = '''import json, sqlite3, sys, time
from pathlib import Path
path = Path(sys.argv[1]) / 'owned-latency-probe.sqlite'
db = sqlite3.connect(path, timeout=1, isolation_level=None)
try:
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE sample (value INTEGER)')
    db.execute('INSERT INTO sample VALUES (0)')
    samples = []
    for index in range(8):
        db.execute('BEGIN IMMEDIATE')
        db.execute('UPDATE sample SET value=?', (index + 1,))
        began = time.perf_counter()
        db.commit()
        samples.append(round((time.perf_counter() - began) * 1000, 3))
    print(json.dumps({'schema': 'fleet.sqlite-path-probe/1', 'commit_ms': samples,
        'journal_mode': db.execute('PRAGMA journal_mode').fetchone()[0],
        'synchronous': db.execute('PRAGMA synchronous').fetchone()[0]}), flush=True)
finally:
    db.close()
'''


def research_manifest():
    return {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__), HERE / 'README.md',
            ROOT / '.github/workflows/research-windows-storage-crossover.yml')}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    if os.name != 'nt':
        raise SystemExit('STORAGE_EXPERIMENT_REQUIRES_WINDOWS')
    packet = Path(args.output).resolve()
    packet.mkdir()  # Never overwrite an earlier attempt.
    spec = importlib.util.spec_from_file_location('storage_source_runner',
        ROOT / 'tests/proofs/fleet_v1/run_source.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    head, tree = runner.git_value('HEAD'), runner.git_value('HEAD^{tree}')
    if head != os.environ.get('FLEET_V1_EXPECTED_SHA'):
        raise SystemExit('STORAGE_EXPERIMENT_CHECKOUT_MISMATCH')
    before = runner.source_manifest()
    inputs = research_manifest()
    summary = {'schema': 'fleet.storage-crossover/1', 'status': 'RUNNING',
        'head_sha': head, 'tree_sha': tree, 'source_before': before, 'research_inputs': inputs,
        'started_utc': runner.utc_now(), 'retries': 0, 'arm_order': ['C1', 'D', 'C2'],
        'io_cap_seconds': 30, 'case_cap_seconds': 120, 'selected': SELECTED,
        'scope': 'DISPOSABLE_SOURCE_PATH_DIAGNOSTIC_NOT_QUALIFICATION',
        'physical_qualification': 'NOT_RUN', 'descendant_closure': 'UNKNOWN',
        'platform': platform.platform(), 'python': platform.python_version(), 'arms': []}
    runner.checkpoint(packet / 'summary.json', summary)
    try:
        if len(before) != 235 or sum(path.startswith('app/') for path in before) != 89:
            raise RuntimeError('STORAGE_EXPERIMENT_SOURCE_INVENTORY_MISMATCH')
        original, alternate = Path(tempfile.gettempdir()).resolve(), Path(os.environ['RUNNER_TEMP']).resolve()
        if any(path.is_symlink() or path.is_junction() for path in (original, alternate)):
            raise RuntimeError('STORAGE_EXPERIMENT_ROOT_REPARSE')
        if original.stat().st_dev == alternate.stat().st_dev:
            raise RuntimeError('STORAGE_EXPERIMENT_DISTINCT_VOLUME_PRECONDITION_MISSING')
        summary['roots'] = {'C': {'drive': original.drive, 'st_dev': original.stat().st_dev},
                            'D': {'drive': alternate.drive, 'st_dev': alternate.stat().st_dev}}
        runner.checkpoint(packet / 'summary.json', summary)
        for name, root in [('C1', original), ('D', alternate), ('C2', original)]:
            owned = Path(tempfile.mkdtemp(prefix='fleet-storage-' + name + '-', dir=root))
            output = packet / name
            output.mkdir()
            env = dict(os.environ)
            for key in ('TMP', 'TEMP', 'TMPDIR'): env[key] = str(owned)
            env['PYTHONPATH'] = os.pathsep.join((str(ROOT / 'app'), str(ROOT / 'tests/unit')))
            arm = {'arm': name, 'temp_drive': owned.drive, 'temp_st_dev': owned.stat().st_dev,
                   'acl_policy': 'ORIGINAL_INHERITED_NOT_MODIFIED', 'status': 'RUNNING'}
            summary['arms'].append(arm)
            runner.checkpoint(packet / 'summary.json', summary)
            probe = runner.run_case('io-probe', [sys.executable, '-c', IO_PROBE, str(owned)], output, env, 30)
            arm['io_receipt'] = probe
            runner.checkpoint(packet / 'summary.json', summary)
            if probe['exit_code'] != 0 or probe['direct_child_closure'] != 'EXITED':
                raise RuntimeError('STORAGE_EXPERIMENT_IO_PROBE_FAILED_OR_CLOSURE_UNKNOWN')
            lines = (output / 'io-probe.log').read_text(encoding='utf-8').splitlines()
            arm['io_observation'] = json.loads(lines[-1])
            env['FLEET_SOURCE_PROGRESS_PATH'] = str(output / 'selected.progress.json')
            command = [sys.executable, '-m', 'pytest', '-p', 'fleet_source_progress', '-v', '--tb=short',
                '-o', 'faulthandler_timeout=60', *SELECTED, '--junitxml=' + str(output / 'selected.junit.xml')]
            receipt = runner.run_case('selected', command, output, env, 120)
            arm['case_receipt'] = receipt
            runner.checkpoint(packet / 'summary.json', summary)
            if receipt['exit_code'] not in (0, 1) or receipt['direct_child_closure'] != 'EXITED':
                raise RuntimeError('STORAGE_EXPERIMENT_UNEXPECTED_EXIT_OR_CLOSURE_UNKNOWN')
            cases = list(ET.parse(output / 'selected.junit.xml').getroot().iter('testcase'))
            identities = [(case.get('classname'), case.get('name')) for case in cases]
            expected = [(value.split('::')[0][:-3].replace('/', '.'), value.split('::')[1]) for value in SELECTED]
            if identities != expected or any(case.find('skipped') is not None for case in cases):
                raise RuntimeError('STORAGE_EXPERIMENT_ORIGINAL_CASE_INVENTORY_MISMATCH')
            arm['case_outcomes'] = [{'classname': case.get('classname'), 'name': case.get('name'),
                'seconds': case.get('time'), 'status': 'FAIL' if any(case.find(tag) is not None
                    for tag in ('failure', 'error')) else 'PASS'} for case in cases]
            arm['status'] = 'PASS' if receipt['exit_code'] == 0 else 'FAIL'
            if (receipt['exit_code'] == 0) != all(row['status'] == 'PASS' for row in arm['case_outcomes']):
                raise RuntimeError('STORAGE_EXPERIMENT_JUNIT_EXIT_MISMATCH')
            if runner.source_manifest() != before or research_manifest() != inputs:
                raise RuntimeError('STORAGE_EXPERIMENT_SOURCE_DRIFT')
            runner.checkpoint(packet / 'summary.json', summary)
        passed = all(arm['status'] == 'PASS' for arm in summary['arms'])
        summary.update(status='ALL_ARMS_PASS_NOT_REPRODUCED' if passed else 'OBSERVED_TEST_FAILURES',
            source_after=runner.source_manifest(), research_after=research_manifest(), finished_utc=runner.utc_now())
        runner.checkpoint(packet / 'summary.json', summary)
    except BaseException as error:
        summary.update(status='ERROR', error_type=type(error).__name__,
            finished_utc=runner.utc_now())
        try:
            summary.update(source_after=runner.source_manifest(), research_after=research_manifest())
            runner.checkpoint(packet / 'summary.json', summary)
        except Exception as evidence_error:
            error.add_note('STORAGE_FINAL_EVIDENCE_FAILED:' + type(evidence_error).__name__)
        raise
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
