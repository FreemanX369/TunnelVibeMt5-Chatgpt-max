import pytest, time
@pytest.fixture
def fixture():
    yield
    private_local = 'PRIVATE_LOCAL_BODY'
    raise PermissionError(13, 'PRIVATE_MESSAGE_BODY', 'PRIVATE_PATH_BODY')
def test_failed(fixture):
    assert True
def test_later():
    time.sleep(30)
