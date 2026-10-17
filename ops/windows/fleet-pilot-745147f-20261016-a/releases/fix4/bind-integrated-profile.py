"""Finite CAS profile switch/rollback for the three existing tunnel instances."""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PILOT=Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a')
HERE=PILOT/'releases/fix4'
sys.path.insert(0,str(HERE/'source/app'))
from vibemql5.fleet import node_keys as keys

EXPECTED_ENTRY='38febd6d4036914b3ea271c1619ce48b4be6a0ed1406a522930f155e386d7b07'
OLD=b'C:/VibeMQL5/.venv/Scripts/python.exe C:/VibeMQL5/ops/windows/fleet-pilot-745147f-20261016-a/releases/fix3/operator-integrated-mcp.py'
NEW=b'C:/VibeMQL5/.venv/Scripts/python.exe C:/VibeMQL5/ops/windows/fleet-pilot-745147f-20261016-a/releases/fix4/operator-integrated-mcp.py'
INSTANCES={
 'A':('vibemql5-vps','tunnel_6a932fb788b881919cbe59cde1effcea'),
 'B':('vibemql5-vps-b','tunnel_6aa8162c6aa48191bf05786861b3eef9'),
 'C':('vibemql5-vps-c','tunnel_6ab364eabc8c8191b66b96b9d7e9ad0b'),
}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--instance',required=True,choices=INSTANCES)
    parser.add_argument('--mode',required=True,choices=['apply','rollback'])
    args=parser.parse_args()
    if hashlib.sha256((HERE/'operator-integrated-mcp.py').read_bytes()).hexdigest()!=EXPECTED_ENTRY:
        raise RuntimeError('ENTRY_HASH_CHANGED')
    profile_name,tunnel=INSTANCES[args.instance]
    profile=Path(r'C:\Users\Administrator\AppData\Roaming\tunnel-client')/(profile_name+'.yaml')
    backup=PILOT/'runtime/secrets'/('fix4-profile-'+args.instance+'.original.yaml')
    path=HERE/('PROFILE-'+args.instance+'-'+args.mode.upper()+'-RECEIPT.json')
    if path.exists():raise RuntimeError('PROFILE_OPERATION_RECEIPT_EXISTS')
    before=profile.read_bytes()
    if tunnel.encode() not in before:raise RuntimeError('TUNNEL_ID_MISMATCH')
    if args.mode=='apply':
        gate=json.loads((HERE/'qa/predeploy/RECEIPT.json').read_bytes())
        if gate.get('status')!='PASS' or gate.get('entry_sha256')!=EXPECTED_ENTRY:
            raise RuntimeError('PREDEPLOY_E2E_NOT_ACCEPTED')
        qa=json.loads((HERE/'qa/focused/RECEIPT.json').read_bytes())
        if qa.get('status')!='PASS':raise RuntimeError('FOCUSED_WINDOWS_QA_NOT_ACCEPTED')
        if args.instance!='A':
            accepted=json.loads((HERE/'A-ACCEPTANCE-RECEIPT.json').read_bytes())
            if accepted.get('status')!='PASS' or accepted.get('entry_sha256')!=EXPECTED_ENTRY:
                raise RuntimeError('A_ACCEPTANCE_NOT_RECORDED')
        if before.count(OLD)!=1 or NEW in before:raise RuntimeError('OLD_COMMAND_MISMATCH')
        fd=keys._windows_create(keys._path(backup))
        try:
            keys._windows_acl(fd,set_restrictive=True);keys._check(fd)
            with os.fdopen(fd,'wb',closefd=False) as stream:
                stream.write(before);stream.flush();os.fsync(fd)
        finally:os.close(fd)
        after=before.replace(OLD,NEW)
    else:
        applied=json.loads((HERE/('PROFILE-'+args.instance+'-APPLY-RECEIPT.json')).read_bytes())
        if hashlib.sha256(before).hexdigest()!=applied['after_sha256']:
            raise RuntimeError('ROLLBACK_CURRENT_PROFILE_CAS_MISMATCH')
        after=backup.read_bytes()
        if hashlib.sha256(after).hexdigest()!=applied['before_sha256']:
            raise RuntimeError('ROLLBACK_BACKUP_HASH_MISMATCH')
    with profile.open('r+b') as stream:
        if stream.read()!=before:raise RuntimeError('PROFILE_CAS_MISMATCH')
        stream.seek(0);stream.write(after);stream.truncate();stream.flush();os.fsync(stream.fileno())
    if profile.read_bytes()!=after:raise RuntimeError('PROFILE_READBACK_MISMATCH')
    result={'status':'PROFILE_SWITCHED_RESTART_PENDING','mode':args.mode,'instance':args.instance,
        'profile':profile_name,'tunnel_id':tunnel,'before_sha256':hashlib.sha256(before).hexdigest(),
        'after_sha256':hashlib.sha256(after).hexdigest(),'entry_sha256':EXPECTED_ENTRY,
        'at_utc':datetime.now(timezone.utc).isoformat(),'application_files':'UNCHANGED',
        'keys_journals_native_qualification':'UNCHANGED'}
    with path.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result))


if __name__=='__main__':main()
