"""Real owned Windows process and fail-closed enumeration fault regressions."""
import os,shutil,subprocess,time
from types import SimpleNamespace
import pytest
from vibemql5.core import windows_process_inventory as w

def fake(monkeypatch,*,error,terminal=False):
 closed=[]
 def first(_,entry):
  if terminal:entry._obj.szExeFile='terminal64.exe';entry._obj.th32ProcessID=123;return 1
  return 0
 k=SimpleNamespace(CreateToolhelp32Snapshot=lambda *_:1,Process32FirstW=first,Process32NextW=lambda *_:0,OpenProcess=lambda *_:0,CloseHandle=lambda h:closed.append(h))
 monkeypatch.setattr(w,'_api',lambda:k);monkeypatch.setattr(w,'_last_error',lambda:error)
 return closed

def test_enumeration_failure_is_unknown_and_closes_snapshot(monkeypatch):
 closed=fake(monkeypatch,error=5)
 with pytest.raises(w.ProcessObservationUnavailable,match='TERMINAL_PROCESS_OBSERVATION_UNAVAILABLE'):w.terminal_paths()
 assert closed==[1]

def test_verified_end_of_snapshot_can_report_empty(monkeypatch):
 closed=fake(monkeypatch,error=18)
 assert w.terminal_paths()==set() and closed==[1]

def test_access_denied_to_matching_process_never_claims_idle(monkeypatch):
 closed=fake(monkeypatch,error=5,terminal=True)
 with pytest.raises(w.ProcessObservationUnavailable):w.terminal_paths()
 assert closed==[1]

@pytest.mark.skipif(os.name!='nt',reason='Owned harmless Win32 process fixture')
def test_real_owned_process_path_observed_without_shell_query(tmp_path,monkeypatch):
 exe=tmp_path/'terminal64.exe';shutil.copyfile(os.environ.get('COMSPEC',r'C:\Windows\System32\cmd.exe'),exe)
 process=subprocess.Popen([str(exe),'/d','/q'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  deadline=time.monotonic()+5;expected=str(exe).replace('/','\\').casefold()
  while time.monotonic()<deadline:
   paths={x.replace('/','\\').casefold() for x in w.terminal_paths()}
   if expected in paths:break
   time.sleep(.02)
  assert expected in paths
  monkeypatch.setattr(subprocess,'run',lambda *a,**k:(_ for _ in ()).throw(AssertionError('SHELL_QUERY_USED')))
  assert expected in {x.replace('/','\\').casefold() for x in w.terminal_paths()}
 finally:
  if process.poll() is None:process.communicate(b'exit\r\n',timeout=5)
  assert process.poll() is not None
 assert expected not in {x.replace('/','\\').casefold() for x in w.terminal_paths()}
