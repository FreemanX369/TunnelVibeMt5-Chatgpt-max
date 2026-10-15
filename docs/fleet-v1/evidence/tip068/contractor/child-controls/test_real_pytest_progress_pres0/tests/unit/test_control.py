import pytest
@pytest.fixture
def fixture():
    raise RuntimeError('CONTROLLED_SETUP_FAILURE')
def test_control(fixture):
    assert True
