import gc, hashlib, json, os, tempfile, threading
from contextlib import ExitStack
from pathlib import Path
from queue import Queue
from test_tip058b_transport import tls_files, control_policy, fleet_policy, TOKEN
from test_tip064_integration import domain_policy
from vibemql5.fleet.domain import DomainJournal, GatewayDomain
from vibemql5.fleet.gateway_control import GatewayControlStore
from vibemql5.fleet.job_journal import GatewayJobJournal
from vibemql5.fleet.read_broker import ReadBroker
from vibemql5.fleet.transport import serve_gateway, GatewayController
from vibemql5.core.jobs import _exclusive_file_lock

def fds():return len(os.listdir("/proc/self/fd")) if Path("/proc/self/fd").exists() else None
def find_controller(error):
    frame=error.__traceback__
    while frame is not None:
        if frame.tb_frame.f_code.co_name=="serve_gateway":return frame.tb_frame.f_locals["controller"]
        frame=frame.tb_next
    raise AssertionError("CONTROLLER_FRAME_ABSENT")
def lease_available(path):
    try:
        with _exclusive_file_lock(path,timeout_seconds=.05):return True
    except TimeoutError:return False
def run_case(corrected):
    with tempfile.TemporaryDirectory(prefix="owned-started-callback-")as tmp:
        root=Path(tmp);ca,certificate,private=tls_files.__wrapped__(root)
        queue,observed,bound=Queue(),Queue(),Queue();stopped=threading.Event();holder={};primary=RuntimeError("OWNED_STARTED_CALLBACK")
        baseline=fds()
        def factory(address):
            origin="https://127.0.0.1:"+str(address[1])
            with ExitStack()as closes:
                control=GatewayControlStore.initialize(root/"control.sqlite",policy=control_policy());closes.callback(control.close)
                jobs=GatewayJobJournal(root/"jobs.sqlite",initialize=True,max_records=20,max_payload_bytes=262144,wait_ms=1000);closes.callback(jobs.close)
                journal=DomainJournal(root/"domain.sqlite",initialize=True,role="GATEWAY",policy=domain_policy());closes.callback(journal.close)
                domain=GatewayDomain(control,journal,jobs,start_authorization_ms=2000)
                controller=GatewayController(control,fleet_policy(),audience=origin,owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),broker=ReadBroker.for_synthetic_tests(fleet_policy()),domain=domain)
                if corrected:holder["controller"]=controller
                closes.pop_all();return controller
        def started(address):
            bound.put(address)
            if corrected:
                controller=holder.pop("controller")
                try:controller.domain.close()
                finally:controller.store.close()
            raise primary
        def run():
            try:serve_gateway(("127.0.0.1",0),certificate=certificate,key_file=private,controller_factory=factory,stop_event=stopped,started=started)
            except BaseException as error:
                controller=find_controller(error)
                owners={"control":controller.store,"jobs":controller.domain.native,"domain":controller.domain.journal}
                observed.put({name:{"db_open":obj._db is not None,"actual_select_one":obj._db.execute("SELECT 1").fetchone()[0] if obj._db is not None else None}for name,obj in owners.items()})
                queue.put(error)
        thread=threading.Thread(target=run,daemon=True);thread.start();thread.join(timeout=5)
        assert not thread.is_alive();error=queue.get(timeout=1);assert error is primary
        state=observed.get(timeout=1);address=bound.get(timeout=1)
        import socket
        with socket.socket()as sock:sock.bind(address);socket_rebind=True
        leases={name:lease_available(root/(name+".sqlite.owner.lock"))for name in ("control","jobs","domain")}
        result={"corrected_owned_cleanup_control":corrected,"scope":"actual_owned_local_TLS_Gateway_SQLite; not Windows or live qualification","thread_exited":not thread.is_alive(),"same_primary_error":error is primary,"error_type":type(error).__name__,"owner_thread_observations":state,"leases_available_while_original_traceback_retained":leases,"socket_rebind_after_started_failure":socket_rebind,"fds_baseline":baseline,"fds_with_traceback_retained":fds()}
        error.__traceback__=None;holder.clear();gc.collect()
        result.update({"leases_available_after_owned_traceback_release":{name:lease_available(root/(name+".sqlite.owner.lock"))for name in ("control","jobs","domain")},"fds_after_owned_traceback_release":fds()})
        return result
results=[run_case(False),run_case(True)]
assert not any(results[0]["leases_available_while_original_traceback_retained"].values())
assert all(results[1]["leases_available_while_original_traceback_retained"].values())
assert all(all(row["leases_available_after_owned_traceback_release"].values())for row in results)
print(json.dumps(results,sort_keys=True))
