"""Fresh positive fixture policy discrimination; no production policy edits."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import threading
import time

import pytest
import test_tip064_capacity_https as capacity
import test_tip064_integration as integration
import test_tip058b_transport as transport
from test_tip064_integration import project_node, composed_service
from test_tip064_capacity_https import capacity_service
from test_tip058b_transport import tls_files, service
from vibemql5.fleet.job_journal import GatewayJobJournal
from vibemql5.fleet.wire import WireError

OUT = Path(__file__).parent


@pytest.fixture(autouse=True)
def profile(request, monkeypatch):
    budget = getattr(request.node, 'callspec', None)
    budget = budget.params.get('positive_budget', 5000) if budget else 5000
    original = transport.fleet_policy
    def selected(): return replace(original(), http_timeout_ms=budget, heartbeat_interval_ms=budget)
    for module in (capacity, integration, transport): monkeypatch.setattr(module, 'fleet_policy', selected)


@pytest.mark.parametrize('positive_budget', [1000, 5000])
def test_delayed_durable_registration_budget(project_node, capacity_service, monkeypatch, tmp_path, positive_budget):
    original = GatewayJobJournal.install_capacity_roster
    installed, returned = [], threading.Event()
    def delayed(self, roster):
        result = original(self, roster)
        installed.append(result['profile']['device_id'])
        time.sleep(1.2)
        returned.set()
        return result
    monkeypatch.setattr(GatewayJobJournal, 'install_capacity_roster', delayed)
    if positive_budget == 1000:
        with pytest.raises(WireError) as observed:
            capacity.test_actual_tls_verified_two_slot_delivery_keeps_control_live_and_conflicting_third_queued(
                project_node, capacity_service, 'normal')
        assert observed.value.code == 'HTTPS_UNAVAILABLE'
        assert any('TimeoutError' in note for note in observed.value.__notes__)
    else:
        capacity.test_actual_tls_verified_two_slot_delivery_keeps_control_live_and_conflicting_third_queued(
            project_node, capacity_service, 'normal')
    assert returned.wait(3)
    assert installed == [project_node['registry']['device_id']]
    db = sqlite3.connect((tmp_path / 'capacity-jobs.sqlite').as_uri()+'?mode=ro', uri=True)
    try: durable = json.loads(db.execute("SELECT value FROM meta WHERE name='capacity_rosters'").fetchone()[0])
    finally: db.close()
    assert list(durable) == installed and durable[installed[0]]['profile']['capacity'] == 2
    assert capacity_service[0].policy.http_timeout_ms == positive_budget
    assert capacity_service[0].policy.heartbeat_interval_ms == positive_budget
    (OUT / ('positive-profile-'+str(positive_budget)+'.json')).write_text(json.dumps({
        'classification':'CONTROLLED_RESPONSE_DELAY_NOT_HISTORICAL_CAUSE', 'http_and_control_round_ms':positive_budget,
        'response_delay_seconds':1.2, 'actual_durable_install_calls':len(installed), 'durable_roster_count':len(durable),
        'outcome':'EXPECTED_TIMEOUT_WITH_UNCERTAIN_RESPONSE' if positive_budget==1000 else 'ALL_ORIGINAL_CAPACITY_ASSERTIONS_PASS',
        'registration_retries':0},indent=2)+'\n')


@pytest.mark.parametrize('composed_service', [1000], indirect=True)
def test_long_fixture_expiry_remains_one_second_under_positive_profile(project_node, composed_service, monkeypatch):
    integration.run_long_fixture(project_node, composed_service, monkeypatch)
    assert composed_service[0].policy.http_timeout_ms == 5000
    assert composed_service[0].policy.heartbeat_interval_ms == 5000
    (OUT/'positive-profile-expiry.json').write_text(json.dumps({'signed_ttl_ms':1000,'http_and_control_round_ms':5000,
        'original_expired_entry_proof_denial':True,'fresh_next_phase_success':True,'native_effects':'SYNTHETIC_ONLY'},indent=2)+'\n')


def test_actual_nonce_replay_remains_denied_under_positive_profile(service):
    transport.test_actual_https_pair_retry_replay_sessions_and_no_secrets(service)
    assert service[0].policy.http_timeout_ms == 5000
    (OUT/'positive-profile-replay.json').write_text(json.dumps({'http_and_control_round_ms':5000,
        'actual_CONTROL_REPLAY_denial':True,'actual_session_conflict_denial':True,'actual_unauthorized_owner_denial':True},indent=2)+'\n')
