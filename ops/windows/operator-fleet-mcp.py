"""Frozen Fleet-only stdio entry for existing tunnel C."""
import sys
from pathlib import Path

ROOT = Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a')
sys.path.insert(0, str(ROOT / 'source/app'))
from vibemql5.adapters.fleet_mcp import main

if __name__ == '__main__':
    main(['--config', str(ROOT / 'runtime/secrets/owner-client.json')])
