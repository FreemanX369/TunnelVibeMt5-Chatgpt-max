"""Contractor read-only verification of downloaded GitHub candidate artifacts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

folder, repo, head, tree = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
partial = '--partial' in sys.argv[5:]
sha = lambda data: hashlib.sha256(data).hexdigest()
cache = {}
tracked = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', head], cwd=repo, text=True).splitlines()
expected_manifest = {p for p in tracked if
    (p.endswith('.py') and p.startswith(('app/', 'tests/unit/', 'tests/proofs/')))
    or (p.startswith('.github/workflows/') and p.endswith('.yml'))
    or (p.startswith('ops/windows/') and p.endswith('.ps1'))
    or (('/' not in p) and (p == 'pyproject.toml' or p.startswith('requirements') or 'lock' in p))
    or (p.startswith(('configs/', 'config/', 'docs/fleet-v1/config/')) and Path(p).suffix in {'.json','.toml','.yaml','.yml'})}
def git_bytes(path):
    if path not in cache:
        cache[path] = subprocess.check_output(['git', 'show', head + ':' + path], cwd=repo)
    return cache[path]

def proof(z, name):
    value = json.loads(z.read(name))
    parent = str(Path(name).parent)
    prefix = '' if parent == '.' else parent + '/'
    if 'source' in value:
        assert value['source']['head'] == head and value['source']['exact_head_required']
        for path, item in value['source']['files'].items():
            data = git_bytes(path)
            assert sha(data) == item['sha256'] and len(data) == item['bytes'], path
            assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == item['git_blob'], path
        count = value['executed']
        skips = value['skipped']
        assert count == value['required_count']
        log = z.read(prefix + 'proof.log')
        assert len(log) == value['proof_log']['bytes'] and sha(log) == value['proof_log']['sha256']
        assert not value['proof_log']['truncated']
        sources = len(value['source']['files'])
    else:
        assert value['candidate_sha'] == value['expected_head_sha'] == head
        assert value['exact_head_verified'] and value['source_blob_verified']
        assert value['sources'] == value['git_blob_sources']
        for path, digest in value['sources'].items():
            path = path if '/' in path else 'tests/proofs/tip057rq/' + path
            assert sha(git_bytes(path)) == digest, path
        count, skips, sources = value['tests_run'], value['skips'], len(value['sources'])
        if 'proof_log' in value:
            log = z.read(prefix + 'proof.log')
            assert len(log) == value['proof_log']['original_bytes'] == value['proof_log']['retained_bytes']
            assert sha(log) == value['proof_log']['original_sha256'] and not value['proof_log']['truncated']
    assert value['errors'] == value['failures'] == skips == 0
    required = {'PASS_SYNTHETIC_PORTABLE_ONLY': 39, 'PASS_HARMLESS_WINDOWS_STUB_ONLY': 10,
                'G03A_WINDOWS_FOUNDATION_PASS_PRODUCER_OPEN': 8, 'FIXTURE_PASS_Q03_OPEN': 16}
    assert count == required[value['status']]
    return {'proof': name, 'status': value['status'], 'executed': count, 'errors': 0,
            'failures': 0, 'skips': skips, 'head': head, 'verified_sources': sources}

metadata = {}
for path in (folder / 'metadata').glob('artifacts-*.json'):
    for item in json.loads(path.read_text())['artifacts']:
        metadata[item['id']] = item
receipts = []
for archive in sorted((folder / 'artifacts').glob('*.zip')):
    aid = int(archive.stem.split('-')[1])
    item, data = metadata[aid], archive.read_bytes()
    assert len(data) == item['size_in_bytes'] and sha(data) == item['digest'].removeprefix('sha256:')
    assert item['workflow_run']['head_sha'] == head and not item['expired']
    result = {'artifact_id': aid, 'archive': archive.name, 'bytes': len(data), 'sha256': sha(data),
              'head': head, 'run_id': item['workflow_run']['id'], 'proofs': []}
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not name.endswith('summary.json'):
                continue
            value = json.loads(z.read(name))
            if value.get('schema') == 'fleet.source-verification/1':
                assert value['head_sha'] == value['expected_sha'] == head and value['tree_sha'] == tree
                assert value['status'] == ('FAIL' if 'windows-latest' in item['name'] else 'PASS') and value['scope'] == 'SOURCE_AND_HARMLESS_FIXTURES'
                assert value['physical_qualification'] == 'NOT_RUN'
                assert value['source_before'] == value['source_after'] and value['source_unchanged_during_run']
                assert set(value['source_before']) == expected_manifest
                for path, digest in value['source_before'].items():
                    assert sha(git_bytes(path)) == digest, path
                assert all(c['exit_code'] == (1 if value['status'] == 'FAIL' and c['case'] == 'full-unit' else 0) and not c['timed_out'] for c in value['cases'])
                suite = next(ET.fromstring(z.read('unit.junit.xml')).iter('testsuite'))
                assert int(suite.get('errors')) == 0 and int(suite.get('failures')) == (1 if value['status'] == 'FAIL' else 0)
                cases = list(ET.fromstring(z.read('unit.junit.xml')).iter('testcase'))
                assert len(cases) == int(suite.get('tests'))
                failures = [c.get('name') for c in cases if any(t.tag in ('failure','error') for t in c)]
                assert failures == (['test_long_fixture_valid_finite_schedule_requires_aggregate_observation[10-1000]'] if value['status'] == 'FAIL' else [])
                result.update(recorded_status=value['status'], failed_tests=failures)
                result.update(tree=tree, source_entries=len(value['source_before']), junit=suite.attrib,
                              passed=int(suite.get('tests'))-int(suite.get('skipped'))-int(suite.get('failures')), cases=value['cases'])
            else:
                result['proofs'].append(proof(z, name))
    receipts.append(result)
assert partial or len(receipts) == 5
integrated = [r for r in receipts if 'junit' in r]
if not partial:
    assert len(integrated) == 2 and all(r['source_entries'] == integrated[0]['source_entries'] for r in integrated)
    assert sorted(len(r['cases']) for r in integrated) == [2, 5]
output = {'schema': 'fleet.artifacts-independent-verification/1', 'head': head, 'tree': tree,
          'scope': 'SOURCE_AND_HARMLESS_FIXTURES', 'physical_qualification': 'NOT_RUN', 'source_acceptance': False, 'status': 'FAILED_CANDIDATE_EVIDENCE_VERIFIED_NOT_ACCEPTED', 'artifacts': receipts}
(folder / 'metadata' / ('partial-artifacts-independent-verification.json' if partial else 'failed-artifacts-independent-verification.json')).write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps({'head': head, 'tree': tree, 'archives': len(receipts),
                  'integrated': [{k:r[k] for k in ('artifact_id','passed','source_entries','junit')} for r in integrated],
                  'proof_receipts': sum(len(r['proofs']) for r in receipts)}, indent=2))
