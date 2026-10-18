"""Real TLS/HTTP slow-peer isolation, retaining the sole gateway event owner."""
import socket,time
from dataclasses import replace
import pytest
from test_tip058b_transport import service,tls_files
from vibemql5.fleet.wire import WireError

def short_owner(http):
 http.policy=replace(http.policy,http_timeout_ms=500)


def test_slow_tls_peer_cannot_block_authenticated_owner(service):
 http,owner,address,*_=service
 raw=socket.create_connection(address,timeout=1)
 try:
  time.sleep(.05);short_owner(http)
  with pytest.raises(WireError,match='READ_INTERRUPTED'):owner.read_status('read_isolation_absent')
 finally:raw.close()


def test_slow_http_headers_cannot_block_authenticated_owner(service):
 http,owner,address,*_=service
 raw=http.context.wrap_socket(socket.create_connection(address,timeout=1),server_hostname='127.0.0.1')
 try:
  raw.sendall(b'POST /fleet/v1/read-status HTTP/1.0\r\n');time.sleep(.05);short_owner(http)
  with pytest.raises(WireError,match='READ_INTERRUPTED'):owner.read_status('read_isolation_absent')
 finally:raw.close()
