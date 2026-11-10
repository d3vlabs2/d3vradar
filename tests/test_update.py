import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('updater', Path(__file__).parents[1] / 'deploy/apply_update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)

def test_update_preserves_private_data_and_backs_up(tmp_path):
    source, target = tmp_path/'new', tmp_path/'installed'
    for p in (source, target): p.mkdir()
    (target/'compose.yaml').write_text('old')
    (source/'compose.yaml').write_text('new')
    (target/'.env').write_text('private')
    (source/'.env').write_text('do not copy')
    (target/'data').mkdir()
    (target/'data/db').write_text('database')
    updater.apply(source, target)
    assert (target/'compose.yaml').read_text() == 'new'
    assert (target/'.env').read_text() == 'private'
    assert (target/'data/db').read_text() == 'database'
    assert next((target/'.radar-backups').glob('*/compose.yaml')).read_text() == 'old'
    updater.apply(source, target)
    assert len(list((target/'.radar-backups').iterdir())) == 1

def test_update_rejects_source_target_overlap(tmp_path):
    with pytest.raises(ValueError): updater.apply(tmp_path, tmp_path)
