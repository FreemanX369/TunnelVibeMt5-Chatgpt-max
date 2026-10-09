import gc, json, os, tempfile, threading
from contextlib import ExitStack
from pathlib import Path
from queue import Queue
from dataclasses import replace
from test_tip058b_transport import tls_files, control_policy
from test_tip064_integration import domain_policy
from vibemql5.fleet.domain import DomainJournal
from vibemql5.fleet.gateway_control import GatewayControlStore
from vibemql5.fleet.job_journal import GatewayJobJournal
from vibemql5.fleet.transport import serve_gateway
from vibemql5.core.jobs import _exclusive_file_lock

def fds():return len(os.listdir("/proc/self/fd")) if Path("/proc/self/fd").exists() else None
def resources(error):
    frame=error.__traceback__
    while frame is not None:
        if frame.tb_frame.f_code.co_name == "factory":
            return {name:frame.tb_frame.f_locals[name] for name in ("control","jobs")}
        frame=frame.tb_next
    raise AssertionError("FACTORY_FRAME_ABSENT")
def lease_available(path):
    try:
        with _exclusive_file_lock(path,timeout_seconds=.05):return True
    except TimeoutError:return False
def run_case(corrected):
    with tempfile.TemporaryDirectory(prefix="owned-partial-factory-") as tmp:
        root=Path(tmp);ca,certificate,private=tls_files.__wrapped__(root)
        domain=root/"domain.sqlite";domain.write_bytes(b"OWNED_EXISTING_DOMAIN")
        queue=Queue();observed=Queue();bound=Queue(); stopped=threading.Event(); baseline=fds()
        def factory(address):
            bound.put(address)
            with ExitStack() as closes:
                control=GatewayControlStore.initialize(root/"control.sqlite",policy=replace(control_policy(),max_operations=1000,max_nonces=1000))
                if corrected:closes.callback(control.close)
                jobs=GatewayJobJournal(root/"jobs.sqlite",initialize=True,max_records=20,max_payload_bytes=262144,wait_ms=1000)
                if corrected:closes.callback(jobs.close)
                DomainJournal(domain,initialize=True,role="GATEWAY",policy=domain_policy())
                raise AssertionError("EXPECTED_ACTUAL_DOMAIN_EXISTS")
        def run():
            try:serve_gateway(("127.0.0.1",0),certificate=certificate,key_file=private,controller_factory=factory,stop_event=stopped)
            except BaseException as error:
                retained=resources(error)
                observed.put({name:{"db_open":obj._db is not None,"actual_select_one":obj._db.execute("SELECT 1").fetchone()[0] if obj._db is not None else None} for name,obj in retained.items()})
                queue.put(error)
        thread=threading.Thread(target=run,daemon=True);thread.start();thread.join(timeout=5)
        assert not thread.is_alive();error=queue.get(timeout=1)
        assert type(error).__name__=="WireError" and str(error)=="DOMAIN_EXISTS"
        state=observed.get(timeout=1);address=bound.get(timeout=1)
        import socket
        with socket.socket() as sock:
            sock.bind(address);socket_rebind=True
        result={"corrected_owned_cleanup_control":corrected,"scope":"actual_owned_local_TLS_SQLite; not Windows or live qualification","thread_exited":not thread.is_alive(),"error_type":type(error).__name__,"error_code":"DOMAIN_EXISTS","owner_thread_observations":state,"control_lease_available_while_traceback_retained":lease_available(root/"control.sqlite.owner.lock"),"jobs_lease_available_while_traceback_retained":lease_available(root/"jobs.sqlite.owner.lock"),"socket_rebind_after_factory_failure":socket_rebind,"fds_baseline":baseline,"fds_with_traceback_retained":fds()}
        error.__traceback__=None;error=None;gc.collect()
        result.update({"control_lease_available_after_owned_traceback_release":lease_available(root/"control.sqlite.owner.lock"),"jobs_lease_available_after_owned_traceback_release":lease_available(root/"jobs.sqlite.owner.lock"),"fds_after_owned_traceback_release":fds()})
        return result
results=[run_case(False),run_case(True)]
assert all(not results[0][key] for key in ("control_lease_available_while_traceback_retained","jobs_lease_available_while_traceback_retained"))
assert all(results[1][key] for key in ("control_lease_available_while_traceback_retained","jobs_lease_available_while_traceback_retained"))
assert all(row["control_lease_available_after_owned_traceback_release"] and row["jobs_lease_available_after_owned_traceback_release"] for row in results)
print(json.dumps(results,sort_keys=True))
