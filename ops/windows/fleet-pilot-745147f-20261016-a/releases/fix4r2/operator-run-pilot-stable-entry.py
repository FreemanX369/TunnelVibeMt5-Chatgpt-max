"""Pinned resume bootstrap; normal runtime receipts provide progress evidence."""
import hashlib,runpy,sys
from pathlib import Path
R=Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a\releases\fix4r2')
script=R/'operator-run-pilot-paced.py'
assert sys.argv[1:]==['--resume'],'EXPLICIT_RESUME_REQUIRED'
assert hashlib.sha256(script.read_bytes()).hexdigest()=='6af2f0891738bb5ca84422435d19f76beac53971cf103697e323cc2784c41d63','PACED_SOURCE_CHANGED'
runpy.run_path(str(script),run_name='__main__')
