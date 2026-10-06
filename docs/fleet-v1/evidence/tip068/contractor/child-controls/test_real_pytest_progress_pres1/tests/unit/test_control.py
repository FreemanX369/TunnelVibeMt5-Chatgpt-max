import pytest
@pytest.fixture
def fixture():
    yield
    raise RuntimeError('CONTROLLED_TEARDOWN_FAILURE')
def test_control(fixture):
    assert True
