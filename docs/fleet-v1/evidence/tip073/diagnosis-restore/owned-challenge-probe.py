import hashlib, importlib.util, json, tempfile, time
from pathlib import Path
root=Path("/workspace/scratch/b4674f0ac496/tip072-builder")
spec=importlib.util.spec_from_file_location("owned_restore_fixture",root/"tests/unit/test_tip060c_restore.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with tempfile.TemporaryDirectory(prefix="tip073-owned-restore-") as temporary:
    started=time.monotonic(); generator=m.recovery.__wrapped__(Path(temporary)); r=next(generator)
    setup_seconds=time.monotonic()-started
    before=r["coordinator"].path.read_bytes(); packet=m.proof(r).body
    packet["transport_witness"]["challenge"]="f"*32
    caught=None
    try: r["coordinator"].accept_witness(m.proof(r,value=packet),now_ms=1002)
    except Exception as error: caught={"type":type(error).__name__,"code":str(error)}
    receipt={"scope":"actual_owned_local_fixture; not Windows or live qualification", "setup_seconds":setup_seconds,"caught":caught,
       "coordinator_bytes_unchanged":before==r["coordinator"].path.read_bytes(),"coordinator_ready":r["coordinator"].status()["ready"],
       "control_status":r["control"].snapshot()["status"],"witness_count":len(r["coordinator"].record["witnesses"]),"nonce_count":len(r["coordinator"].record["nonces"])}
    try: next(generator)
    except StopIteration: pass
    receipt["cleanup_completed"]=True
    print(json.dumps(receipt,sort_keys=True))
