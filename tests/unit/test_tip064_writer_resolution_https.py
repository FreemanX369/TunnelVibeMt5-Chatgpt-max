"""An actual signed drain resolves only its original same-journal UNKNOWN."""
import copy
import time

import pytest

from fleet_writer_fixture import writer_fixture, project_node, tls_files, principal_policy
from test_tip061b_writers import source_command
from vibemql5.fleet.domain import DomainJournal, DomainPolicy, NodeDomainDispatcher
from vibemql5.fleet.job_journal import NodeJobJournal
from vibemql5.fleet.principals import GatewayPrincipalAuthority, PrincipalError
from vibemql5.fleet.wire import WireError, encode_body


def domain_policy():
    return DomainPolicy(max_records=100, max_payload_bytes=32768, wait_ms=50,
        max_commands=4, start_authorization_ms=2000)


def test_real_https_unknown_source_revoke_drain_exact_same_journal_resolution(writer_fixture):
    f = writer_fixture
    admitted, _, data = source_command(f)
    journal = DomainJournal(f['root'] / 'local-domain.db', policy=domain_policy(), role='NODE', initialize=True)
    native = NodeJobJournal(f['root'] / 'local-native.db', initialize=True,
        max_records=100, max_payload_bytes=32768, wait_ms=50)
    dispatcher = NodeDomainDispatcher(f['root'], journal, native, None, principal_runtime=f['runtime'])
    try:
        def fault(stage):
            if stage == 'source_record:after_commit':
                raise OSError('interruption between durable source and session commits')
        f['runtime'].fault = fault
        command = f['node'].poll('node-session', 4)['commands'][0]
        dispatcher.dispatch(command, f['node'], 'node-session')
        f['runtime'].fault = None
        original = journal.get(command['command_id'])
        raw_failure = copy.deepcopy(original)
        assert original['state'] == 'UNKNOWN'
        assert f['source'].read_bytes() == data
        assert f['projects'].sessions.get('P')['revision_id'] == 'REV-000001'
        missing_head = journal.control_head()
        assert missing_head['unresolved_count'] == 1
        with pytest.raises(WireError, match='DOMAIN_QUIESCENT_CHECKPOINT_MISMATCH'):
            journal.assert_quiescent_head(missing_head)

        f['owner'].domain_request('/fleet/v1/principals/revoke',
            {'operation_id': 'revoke', 'principal_id': f['principal']})
        fence = f['node'].poll('node-session', 4)['commands'][0]
        dispatcher.dispatch(fence, f['node'], 'node-session')
        installed = journal.get(fence['command_id'])
        assert installed['state'] == 'COMPLETED'
        assert installed['result']['pending_intents']
        assert f['runtime'].state['assignments']['P']['state'] == 'DRAINING'
        assert journal.control_head()['unresolved_count'] == 1
        with pytest.raises(WireError):
            f['admit']('/fleet/v1/sources/write', {'project_id':'P','frozen_id':'new','source_base64':''}, 'new-owner-attempt')

        intent = admitted['payload']['principal_evidence']['body']['intent_sha256']
        f['owner'].domain_request('/fleet/v1/principals/reconcile',
            {'operation_id':'reconcile','original_operation_id':'write','principal_id':f['principal'],
             'project_id':'P','intent_sha256':intent,'expires_ms':int(time.time()*1000)+5000})
        drain = f['node'].poll('node-session', 4)['commands'][0]
        dispatcher.dispatch(drain, f['node'], 'node-session')
        reconciled = journal.get(drain['command_id'])
        assert reconciled['state'] == 'COMPLETED'
        assert reconciled['result']['source_receipt']['session']['revision_id'] == 'REV-000002'
        assert f['source'].read_bytes() == data
        assert f['runtime'].state['assignments']['P']['state'] == 'RELEASED'
        assert journal.get(command['command_id']) == raw_failure
        head = journal.control_head()
        assert head['unresolved_count'] == 0
        journal.assert_quiescent_head(head)
        binding = f['runtime'].verify_domain_resolution(original, reconciled)
        assert binding['original_command_id'] == command['command_id']
        for altered in ('approval', 'receipt', 'intent'):
            bad = copy.deepcopy(reconciled)
            if altered == 'approval': bad['payload']['approval']['body']['operation_id'] = 'different'
            elif altered == 'receipt': bad['result']['source_receipt']['source_sha256'] = '0'*64
            else: bad['result']['writer_acks'][0]['intent_sha256'] = '0'*64
            with pytest.raises((PrincipalError, WireError)):
                f['runtime'].verify_domain_resolution(original, bad)

        # Reopen the real gateway journals on their own event owner after TLS stops.
        f['stop'].set(); f['thread'].join(timeout=5)
        assert not f['thread'].is_alive() and f['failures'].empty()
        authority = GatewayPrincipalAuthority(f['gateway_path']/'principals.json',
            signing_key=f['gateway_key'], audience=f['http'].origin, policy=principal_policy())
        gateway_journal = DomainJournal(f['gateway_path']/'domains.sqlite', policy=domain_policy(), role='GATEWAY')
        try:
            gateway_journal.bind_principal_authority(authority)
            assert gateway_journal.get(command['command_id'])['state'] == 'UNKNOWN'
            gateway_head = gateway_journal.control_head()
            assert gateway_head['unresolved_count'] == 0
            gateway_journal.assert_quiescent_head(gateway_head)
            assert authority.state['assignments']['P']['state'] == 'RELEASED'
            assert authority.state['principals'][f['principal']]['state'] == 'REVOKED'
            authority.assert_quiescent_head(authority.control_head())
            assert authority.verify_domain_resolution(gateway_journal.get(command['command_id']),
                gateway_journal.get(drain['command_id'])) == binding
            # A well-shaped stored outcome cannot resolve UNKNOWN after its
            # exact receipt is changed; the signed authority binding must hold.
            changed = gateway_journal.get(drain['command_id'])
            changed['result']['source_receipt']['source_sha256'] = '0'*64
            gateway_journal._db.execute('UPDATE commands SET record=? WHERE command_id=?',
                (encode_body(changed, domain_policy().max_payload_bytes).decode('ascii'), drain['command_id']))
            tampered_head = gateway_journal.control_head()
            assert tampered_head['unresolved_count'] == 1
            with pytest.raises(WireError, match='DOMAIN_QUIESCENT_CHECKPOINT_MISMATCH'):
                gateway_journal.assert_quiescent_head(tampered_head)
            assert gateway_journal.get(command['command_id'])['state'] == 'UNKNOWN'
        finally:
            gateway_journal.close(); authority.close()
    finally:
        dispatcher.close(); journal.close(); native.close()
