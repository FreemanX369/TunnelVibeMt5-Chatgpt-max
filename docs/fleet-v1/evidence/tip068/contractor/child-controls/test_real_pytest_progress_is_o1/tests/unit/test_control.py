import pytest
@pytest.mark.parametrize('value', ['PRIVATE_PARAMETER_TOKEN'])
def test_control(value):
    raise RuntimeError('CONTROLLED_FAILURE')
