from __future__ import annotations

import json

from vibemql5.backend_admin import core
from vibemql5.backend_admin.multitunnel import MultiTunnelBackendAdmin


def test_poll_diagnostics_cross_instance_and_redacts_log_text(tmp_path, monkeypatch):
    logs = {
        8080: [
            {"time": "2026-09-23T20:31:35+07:00", "message": "poll failed; backing off",
             "attrs": {"error": 'Get "https://api.openai.com/poll?secret=sk-privatefixture": proxyconnect tcp failed',
                       "retry_in_ms": 10000}},
            {"time": "2026-09-23T20:35:37+07:00", "message": "poller recovered; polling operational"},
            {"time": "2026-09-23T21:17:36+07:00", "message": "poll timed out; backing off",
             "attrs": {"error": "Client.Timeout exceeded while awaiting headers",
                       "poll_timeout_ms": 30000, "poll_deadline_ms": 35000}},
            {"time": "2026-09-23T21:25:33+07:00", "message": "poller recovered; polling operational"},
        ],
        8081: [
            {"time": "2026-09-23T21:17:40+07:00", "message": "poll failed; backing off",
             "attrs": {"error": "context deadline exceeded", "status_code": 503}},
        ],
        8082: [{"time": "2026-09-23T20:30:00+07:00", "message": "poller started"}],
    }
    requested = []

    class Response:
        status = 200

        def __init__(self, port):
            self.port = port

        def read(self, _limit):
            return json.dumps({"events": logs[self.port]}).encode()

    class Connection:
        def __init__(self, host, port, timeout):
            assert host == "127.0.0.1" and timeout == 4
            self.port = port

        def request(self, method, path):
            requested.append((self.port, method, path))

        def getresponse(self):
            return Response(self.port)

        def close(self):
            pass

    monkeypatch.setattr(core.http.client, "HTTPConnection", Connection)
    admin = MultiTunnelBackendAdmin(tmp_path)
    monkeypatch.setattr(admin, "_profile_pids", lambda _profile: [1234])
    monkeypatch.setattr(admin, "_task_state", lambda _name: "Ready")
    monkeypatch.setattr(admin, "_http_status", lambda _url: 200)

    result = admin.tunnel_admin_status("all")
    assert result["status"] == "PASS"
    assert requested == [(p, "GET", "/api/logs?limit=5000") for p in (8080, 8081, 8082)]
    a, b, c = (item["poll_diagnostics"] for item in result["instances"])
    assert [(x["failure_count"], x["recovered_at"]) for x in a["episodes"]] == [
        (1, "2026-09-23T20:35:37+07:00"), (1, "2026-09-23T21:25:33+07:00")
    ]
    assert a["episodes"][0]["first_error_kind"] == "PROXY"
    assert a["episodes"][1]["last_error_kind"] == "AWAITING_HEADERS_TIMEOUT"
    assert a["episodes"][1]["poll_deadline_ms"] == 35000
    assert b["episodes"][0]["first_error_kind"] == "HTTP_503"
    assert b["episodes"][0]["recovered_at"] is None
    assert c["poll_failures_retained"] == 0
    assert "sk-privatefixture" not in json.dumps(result)
    assert "https://api.openai.com" not in json.dumps(result)


def test_unavailable_local_logs_do_not_break_tunnel_status(tmp_path, monkeypatch):
    class Connection:
        def __init__(self, _host, _port, timeout):
            pass

        def request(self, _method, _path):
            raise ConnectionRefusedError("private endpoint")

        def close(self):
            pass

    monkeypatch.setattr(core.http.client, "HTTPConnection", Connection)
    admin = MultiTunnelBackendAdmin(tmp_path)
    monkeypatch.setattr(admin, "_profile_pids", lambda _profile: [])
    monkeypatch.setattr(admin, "_task_state", lambda _name: "MISSING")
    monkeypatch.setattr(admin, "_http_status", lambda _url: 0)

    result = admin.tunnel_admin_status("C")
    assert result["status"] == "PASS"
    assert result["instances"][0]["poll_diagnostics"] == {
        "status": "UNAVAILABLE", "reason_code": "LOGS_UNREACHABLE_OR_INVALID"
    }
