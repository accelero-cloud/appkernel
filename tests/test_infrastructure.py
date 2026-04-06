"""Tests for CfgEngine config loading and get() traversal."""
import pytest

from appkernel.core import AppInitialisationError
from appkernel.infrastructure import CfgEngine


def test_cfg_engine_with_valid_file(tmp_path):
    cfg = tmp_path / 'cfg.yml'
    cfg.write_text(
        'appkernel:\n'
        '  mongo:\n'
        '    host: testhost\n'
        '    db: testdb\n'
    )
    engine = CfgEngine(cfg_dir=str(tmp_path))
    assert engine.get('appkernel.mongo.host') == 'testhost'
    assert engine.get('appkernel.mongo.db') == 'testdb'


def test_cfg_engine_missing_file_non_optional_raises():
    with pytest.raises(AppInitialisationError):
        CfgEngine(cfg_dir='/nonexistent/path/xyz', optional=False)


def test_cfg_engine_missing_file_optional_returns_defaults():
    engine = CfgEngine(cfg_dir='/nonexistent/path/xyz', optional=True)
    assert not engine.initialised
    assert engine.get('appkernel.mongo.host', 'fallback') == 'fallback'


def test_cfg_engine_bad_yaml_raises(tmp_path):
    # Use a tab-indented file, which triggers yaml.scanner.ScannerError
    cfg = tmp_path / 'cfg.yml'
    cfg.write_text('\t bad_key: value\n')
    with pytest.raises(AppInitialisationError):
        CfgEngine(cfg_dir=str(tmp_path))


def test_cfg_engine_get_missing_key_returns_default(tmp_path):
    cfg = tmp_path / 'cfg.yml'
    cfg.write_text('appkernel:\n  mongo:\n    host: localhost\n')
    engine = CfgEngine(cfg_dir=str(tmp_path))
    assert engine.get('appkernel.missing.key', 42) == 42


def test_cfg_engine_get_shallow_key(tmp_path):
    cfg = tmp_path / 'cfg.yml'
    cfg.write_text('name: myapp\n')
    engine = CfgEngine(cfg_dir=str(tmp_path))
    assert engine.get('name') == 'myapp'


def test_cfg_engine_get_deep_path(tmp_path):
    cfg = tmp_path / 'cfg.yml'
    cfg.write_text('a:\n  b:\n    c: deep_value\n')
    engine = CfgEngine(cfg_dir=str(tmp_path))
    assert engine.get('a.b.c') == 'deep_value'


def test_cfg_engine_get_missing_intermediate_node(tmp_path):
    cfg = tmp_path / 'cfg.yml'
    cfg.write_text('appkernel:\n  mongo:\n    host: localhost\n')
    engine = CfgEngine(cfg_dir=str(tmp_path))
    assert engine.get('appkernel.server.port', 5000) == 5000


def test_cfg_engine_not_initialised_returns_default():
    engine = CfgEngine(cfg_dir='/nonexistent', optional=True)
    # get() should return default_value when not initialised
    assert engine.get('anything.at.all', 'default') == 'default'
