import pytest
@pytest.mark.parametrize('value', ['PRIVATE_PARAMETER_TOKEN'])
def test_control(value):
    pytest.skip('CONTROLLED_SKIP')
