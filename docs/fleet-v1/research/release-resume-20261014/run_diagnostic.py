"""Fixed, bounded NEW research revision; never replays UNKNOWN original44."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
RESEARCH = Path(__file__).resolve().parent
SELECTED = (
    'tests/unit/test_tip064_capacity_https.py::test_capacity_positive_profile_delayed_durable_registration_has_no_retry[5000]',
    'tests/unit/test_tip077_capacity_entry_watchdog.py::test_original_three_second_capacity_entry_observation_remains_bounded_negative',
    'tests/unit/test_tip063_worktrees.py::test_exact_crash_reopen_recovers_without_duplicate_git_effect[commit:after_effect]',
    'tests/unit/test_tip064_integration.py::test_actual_tls_blocked_native_keeps_heartbeat_status_cancel_and_lost_ack_durable',
)


def research_manifest():
    return {name: hashlib.sha256((RESEARCH / name).read_bytes()).hexdigest()
            for name in ('observer.py', 'controls.py', 'run_diagnostic.py', 'README.md')}


def junit_count(path, expected):
    if not path.is_file(): return False
    cases = list(ET.parse(path).getroot().iter('testcase'))
    return len(cases) == expected and not any(
        list(case.iter('failure')) or list(case.iter('error')) or list(case.iter('skipped')) for case in cases)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--require-windows', action='store_true')
    args = parser.parse_args(argv)
    if args.require_windows and os.name != 'nt':
        raise SystemExit('DIAGNOSTIC_PLATFORM_MISMATCH')
    destination = Path(args.output).resolve()
    if destination.exists():
        raise SystemExit('DIAGNOSTIC_OUTPUT_REUSE_FORBIDDEN')
    destination.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location('fleet_source_research_runner',
        ROOT / 'tests/proofs/fleet_v1/run_source.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    head, tree = runner.git_value('HEAD'), runner.git_value('HEAD^{tree}')
    expected = os.environ.get('FLEET_V1_EXPECTED_SHA')
    expected_tree = os.environ.get('FLEET_V1_EXPECTED_TREE', tree)
    if expected is None or head != expected or tree != expected_tree:
        raise SystemExit('DIAGNOSTIC_CHECKOUT_MISMATCH')
    before, research_before = runner.source_manifest(), research_manifest()
    environment = dict(os.environ)
    environment['PYTHONPATH'] = os.pathsep.join((str(RESEARCH), str(ROOT / 'app'), str(ROOT / 'tests/unit')))
    base = [sys.executable, '-m', 'pytest', '-p', 'observer', '-p', 'fleet_source_progress', '-v',
            '--tb=short', '-o', 'faulthandler_timeout=60']
    cases = [
        ('controls', [*base, str(RESEARCH / 'controls.py'),
            '--junitxml=' + str(destination / 'controls.junit.xml'),
            '--basetemp=' + str(destination / 'controls-tmp')], 60),
        ('selected', [*base, *SELECTED,
            '--tip088-diag-output=' + str(destination / 'observations.jsonl'),
            '--junitxml=' + str(destination / 'selected.junit.xml'),
            '--basetemp=' + str(destination / 'selected-tmp')], 240),
    ]
    summary = {'schema': 'fleet.release-resume-diagnostic/1', 'status': 'RUNNING',
        'head_sha': head, 'tree_sha': tree, 'expected_sha': expected, 'expected_tree': expected_tree,
        'relationship': 'NEW_REVISION_SUPERSEDES_RESEARCH_INPUT_ONLY_ORIGINAL44_UNKNOWN',
        'retries': 0, 'scope': 'SOURCE_AND_TEMPORARY_HARMLESS_FIXTURES', 'physical_qualification': 'NOT_RUN',
        'platform': platform.platform(), 'python': platform.python_version(),
        'started_utc': runner.utc_now(), 'source_before': before, 'research_before': research_before,
        'planned_cases': [{'case': name, 'command': command, 'timeout_seconds': cap} for name, command, cap in cases],
        'cases': [], 'active_case': None, 'closure_scope': 'DIRECT_CHILD_ONLY', 'descendant_closure': 'UNKNOWN'}
    runner.checkpoint(destination / 'summary.json', summary)
    try:
        for name, command, cap in cases:
            summary['active_case'] = {'case': name, 'receipt': str(destination / (name + '.receipt.json')),
                                     'log': str(destination / (name + '.log'))}
            runner.checkpoint(destination / 'summary.json', summary)
            current_environment = dict(environment)
            current_environment['FLEET_SOURCE_PROGRESS_PATH'] = str(destination / (name + '.progress.json'))
            result = runner.run_case(name, command, destination, current_environment, cap)
            summary['cases'].append(result)
            runner.checkpoint(destination / 'summary.json', summary)
            if result['exit_code'] != 0 or result['direct_child_closure'] != 'EXITED':
                break  # No dispatch of later case after failed/unknown earlier outcome.
        after, research_after = runner.source_manifest(), research_manifest()
        observations = []
        observation_path = destination / 'observations.jsonl'
        if observation_path.is_file():
            observations = [json.loads(line) for line in observation_path.read_text().splitlines() if line]
        observation_ok = (len(observations) == 4 and
            [row.get('case_ordinal') for row in observations] == [1, 2, 3, 4] and
            all(row.get('observer_errors') == 0 for row in observations))
        junit_ok = junit_count(destination / 'controls.junit.xml', 10) and junit_count(destination / 'selected.junit.xml', 4)
        passed = (len(summary['cases']) == 2 and all(row['exit_code'] == 0 for row in summary['cases']) and
                  before == after and research_before == research_after and observation_ok and junit_ok)
        summary.update(status='PASS' if passed else 'FAIL', active_case=None, finished_utc=runner.utc_now(),
            source_after=after, research_after=research_after, source_unchanged_during_run=before == after,
            research_unchanged_during_run=research_before == research_after,
            observation_attestation=observation_ok, junit_attestation=junit_ok)
        runner.checkpoint(destination / 'summary.json', summary)
    except BaseException as error:
        summary.update(status='INTERRUPTED' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'ERROR',
                       error_type=type(error).__name__, finished_utc=runner.utc_now())
        try:
            summary.update(source_after=runner.source_manifest(), research_after=research_manifest())
            runner.checkpoint(destination / 'summary.json', summary)
        except Exception as evidence_error:
            error.add_note('DIAGNOSTIC_FINAL_EVIDENCE_FAILED:' + type(evidence_error).__name__)
        raise
    print(json.dumps({key: summary[key] for key in ('schema', 'status', 'head_sha', 'tree_sha', 'physical_qualification')}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
