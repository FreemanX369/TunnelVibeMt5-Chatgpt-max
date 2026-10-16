"""Exact one-line tunnel-C target update; retains protected original profile."""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a')
PROFILE = Path(r'C:\Users\Administrator\AppData\Roaming\tunnel-client\vibemql5-vps-c.yaml')
sys.path.insert(0, str(ROOT / 'source/app'))
from vibemql5.fleet import node_keys as keys

if __name__ == '__main__':
    before = PROFILE.read_bytes()
    old = b'C:/VibeMQL5/.venv/Scripts/python.exe -m vibemql5.adapters.mcp --root C:/VibeMQL5 --transport stdio'
    new = b'C:/VibeMQL5/.venv/Scripts/python.exe C:/VibeMQL5/ops/windows/fleet-pilot-745147f-20261016-a/operator-fleet-mcp.py'
    if before.count(old) != 1 or new in before or b'tunnel_6ab364eabc8c8191b66b96b9d7e9ad0b' not in before:
        raise RuntimeError('TUNNEL_PROFILE_SCOPE_MISMATCH')
    backup = ROOT / 'runtime/secrets/tunnel-c-profile.before-fleet.yaml'
    fd = keys._windows_create(keys._path(backup))
    try:
        keys._windows_acl(fd, set_restrictive=True); keys._check(fd)
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(before); stream.flush(); os.fsync(fd)
    finally:
        os.close(fd)
    after = before.replace(old,new)
    with PROFILE.open('r+b') as stream:
        if stream.read() != before:
            raise RuntimeError('TUNNEL_PROFILE_CAS_MISMATCH')
        stream.seek(0); stream.write(after); stream.truncate(); stream.flush(); os.fsync(stream.fileno())
    if PROFILE.read_bytes() != after:
        raise RuntimeError('TUNNEL_PROFILE_READBACK_MISMATCH')
    receipt = {'status':'PROFILE_UPDATED_RESTART_PENDING','instance':'C',
        'tunnel_id':'tunnel_6ab364eabc8c8191b66b96b9d7e9ad0b',
        'before_sha256':hashlib.sha256(before).hexdigest(), 'after_sha256':hashlib.sha256(after).hexdigest(),
        'replaced_exact_command_count':1, 'tool_catalog':'SEPARATE_FLEET_31', 'legacy_A_B':'UNCHANGED'}
    (ROOT / 'runtime/TUNNEL-C-BIND-RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt))
