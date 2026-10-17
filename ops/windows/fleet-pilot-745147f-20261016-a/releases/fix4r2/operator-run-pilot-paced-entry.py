"""Verified bootstrap for the paced control-only pilot; bounded startup trace."""
import faulthandler,hashlib,json,os,runpy,sys
from pathlib import Path
from datetime import datetime,timezone
R=Path(r'C:\VibeMQL5\ops\windows\fleet-pilot-745147f-20261016-a\releases\fix4r2')
expected='6af2f0891738bb5ca84422435d19f76beac53971cf103697e323cc2784c41d63'
script=R/'operator-run-pilot-paced.py'
assert sys.argv[1:]==['--resume'],'EXPLICIT_RESUME_REQUIRED'
assert hashlib.sha256(script.read_bytes()).hexdigest()==expected,'PACED_SOURCE_CHANGED'
trace=(R/'qa/paced-boot-stack.txt').open('a')
faulthandler.dump_traceback_later(20,file=trace)
(R/'qa/PACED-BOOT.json').write_text(json.dumps({'pid':os.getpid(),'stage':'VERIFIED_BOOTSTRAP','runner_sha256':expected,'at':datetime.now(timezone.utc).isoformat()}))
runpy.run_path(str(script),run_name='__main__')
