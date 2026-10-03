"""Ephemeral real Ed25519 client/node/gateway, verified local HTTPS only."""
import hashlib
import threading
import time
from queue import Queue

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_tip058b_transport import tls_files, fleet_policy, control_policy, TOKEN
from test_tip061a_057n import node as project_node
from vibemql5.fleet.domain import GatewayDomain, DomainJournal, DomainPolicy
from vibemql5.fleet.gateway_control import GatewayControlStore
from vibemql5.fleet.job_journal import GatewayJobJournal
from vibemql5.fleet.principals import GatewayPrincipalAuthority, PrincipalPolicy, sign_principal_request, PATHS
from vibemql5.fleet.transport import GatewayController, HttpsClient, NodeClient, OwnerClient, serve_gateway
from vibemql5.fleet.wire import encode_body
from vibemql5.fleet.writers import NodePrincipalRuntime, WriterPolicy


def principal_policy():
    return PrincipalPolicy(max_principals=20,max_assignments=20,max_operations=200,max_nonces=200,
        max_payload_bytes=1048576,clock_skew_ms=5000,phase_ttl_ms=10000,wait_ms=50)


def writer_policy():
    return WriterPolicy(max_operations=100,max_projects=20,max_payload_bytes=1048576,max_source_bytes=32768,wait_ms=50)


@pytest.fixture
def writer_fixture(project_node,tls_files,tmp_path):
    ca,certificate,private=tls_files
    stopping,ready,failures=threading.Event(),Queue(),Queue()
    gatewaykey,clientkey,nodekey=(Ed25519PrivateKey.generate() for _ in range(3))
    root=project_node['root']; device=project_node['registry']['device_id']
    target={**project_node['project']['default_target'],'route_generation':1}
    def factory(address):
        origin='https://localhost:'+str(address[1])
        control=GatewayControlStore.initialize(tmp_path/'gateway'/'control.sqlite',policy=control_policy())
        domains=DomainJournal(tmp_path/'gateway'/'domains.sqlite',policy=DomainPolicy(max_records=100,max_payload_bytes=32768,wait_ms=50,max_commands=4,start_authorization_ms=2000),role='GATEWAY',initialize=True)
        native=GatewayJobJournal(tmp_path/'gateway'/'native.sqlite',initialize=True,max_records=100,max_payload_bytes=32768,wait_ms=50)
        authority=GatewayPrincipalAuthority(tmp_path/'gateway'/'principals.json',signing_key=gatewaykey,audience=origin,policy=principal_policy(),initialize=True)
        domain=GatewayDomain(control,domains,native,principal_authority=authority,start_authorization_ms=2000)
        return GatewayController(control,fleet_policy(),audience=origin,owner_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),domain=domain)
    def run():
        try: serve_gateway(('127.0.0.1',0),certificate=certificate,key_file=private,controller_factory=factory,stop_event=stopping,started=ready.put)
        except BaseException as error: failures.put(error)
    thread=threading.Thread(target=run,daemon=True);thread.start();address=ready.get(timeout=5)
    http=HttpsClient('https://localhost:'+str(address[1]),fleet_policy(),cafile=str(ca));owner=OwnerClient(http,TOKEN)
    grant=owner.admin('grant',{'device_id':device,'public_key':nodekey.public_key().public_bytes_raw().hex(),'operation_id':'grant','expected_revision':1,'expected_route_generation':None})
    node=NodeClient(http,nodekey,device,0);node.pair(grant_id=grant['receipt']['grant_id'],secret=grant['secret'],operation_id='pair',expected_revision=2)
    node.heartbeat('node-session')
    credential=owner.domain_request('/fleet/v1/principals/issue',{'operation_id':'issue','client_public_key':clientkey.public_key().public_bytes_raw().hex(),'installation_id':'client-install','session_id':'client-session','expires_ms':int(time.time()*1000)+600000,'scopes':sorted(PATHS)})['credential']
    principal=credential['body']['principal_id']
    assignment=owner.domain_request('/fleet/v1/principals/assign',{'operation_id':'assign','principal_id':principal,'project_id':'P','target':target,'writer_epoch':1})['assignment']
    runtime=NodePrincipalRuntime(root,gateway_public_key=gatewaykey.public_key().public_bytes_raw(),audience=http.origin,device_id=device,route_generation=1,session_id='node-session',policy=writer_policy(),initialize=True)
    runtime.bind_control_transport(node)
    counter=0
    def admit(path,payload,operation='operation'):
        nonlocal counter
        counter+=1
        value={'schema':'fleet.domain-request/1','node':{'device_id':device,'route_generation':1},'operation_id':operation,'payload':payload}
        body=encode_body(value,32768)
        headers=sign_principal_request(clientkey,credential,path=path,body_bytes=body,timestamp_ms=int(time.time()*1000),nonce='client-'+str(counter),audience=http.origin)
        return http.post(path,value,headers)
    value={'root':root,'runtime':runtime,'admit':admit,'node':node,'owner':owner,'http':http,'credential':credential,'assignment':assignment,'principal':principal,
        'gateway_path':tmp_path/'gateway','gateway_key':gatewaykey,'stop':stopping,'thread':thread,'failures':failures,**project_node}
    yield value
    runtime.close();stopping.set();thread.join(timeout=5)
    assert not thread.is_alive()
    if not failures.empty(): raise failures.get()
