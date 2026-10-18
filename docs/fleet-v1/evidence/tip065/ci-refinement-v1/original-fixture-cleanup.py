cancelled.set()
deadline = time.monotonic() + 2
while dispatcher.has_pending_work() and time.monotonic() < deadline:
    try:
        stopping.run_once()
    except WireError as error:
        assert error.code == 'FIXTURE_LOST_ACK'
    time.sleep(0.005)
assert stopping.close()['status'] == 'CLOSED'
assert stopping.close()['status'] == 'CLOSED'
