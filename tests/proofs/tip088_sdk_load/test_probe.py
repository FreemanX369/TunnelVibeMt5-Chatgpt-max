import importlib.util
from pathlib import Path
import ast
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('sdk_load_probe', HERE / 'run_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_existing_lab_is_rejected_without_touching_contents(tmp_path):
    marker = tmp_path / 'existing.txt'
    marker.write_text('keep')
    with pytest.raises(RuntimeError, match='FRESH_LAB_REQUIRED'):
        probe.fresh_lab(tmp_path)
    assert marker.read_text() == 'keep'


def test_symlink_parent_cannot_redirect_acl_scope(tmp_path):
    actual = tmp_path / 'actual'; actual.mkdir()
    link = tmp_path / 'link'
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip('OS denies creating symlink')
    with pytest.raises(RuntimeError, match='LAB_REPARSE_PARENT_DENIED'):
        probe.fresh_lab(link / 'lab')
    assert not (actual / 'lab').exists()


def test_runtime_copy_rejects_links_before_copy(tmp_path):
    src = tmp_path / 'source'; src.mkdir()
    secret = tmp_path / 'outside'; secret.write_text('do not copy')
    try:
        (src / 'link').symlink_to(secret)
    except OSError:
        pytest.skip('OS denies creating symlink')
    with pytest.raises(RuntimeError, match='RUNTIME_LINK_DENIED'):
        probe.copy_tree(src, tmp_path / 'destination')
    assert not (tmp_path / 'destination').exists()


def test_load_worker_never_calls_sdk_operations():
    tree = ast.parse((HERE / 'worker.py').read_text())
    sdk_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and isinstance(n.func.value, ast.Name) and n.func.value.id == 'sdk']
    assert sdk_calls == []
