"""
Tests for PKI key loading priority in AppKernelEngine.__init_crypto:
  1. APPKERNEL_PRIVATE_KEY_PATH / APPKERNEL_PUBLIC_KEY_PATH env vars
  2. cfg.yml appkernel.security.private_key_path / public_key_path
  3. Default: {cfg_dir}/keys/appkernel.pem / appkernel.pub
"""
import os
import pytest
from pathlib import Path
from appkernel import AppKernelEngine
from appkernel.configuration import config

CURRENT_DIR = Path(__file__).parent
CFG_DIR = str(CURRENT_DIR / '..')
# Actual key files used by all other tests
PRIVATE_KEY_PATH = str(CURRENT_DIR / '..' / 'keys' / 'appkernel.pem')
PUBLIC_KEY_PATH = str(CURRENT_DIR / '..' / 'keys' / 'appkernel.pub')


def _fresh_engine(monkeypatch):
    """Remove cached keys so __init_crypto always runs."""
    for attr in ('public_key', 'private_key'):
        if hasattr(config, attr):
            monkeypatch.delattr(config, attr, raising=False)


def _make_engine():
    return AppKernelEngine('pki_test', cfg_dir=CFG_DIR, development=True)


# ---------------------------------------------------------------------------
# Default fallback: {cfg_dir}/keys/appkernel.pem + appkernel.pub
# ---------------------------------------------------------------------------

def test_default_key_path_loads_keys(monkeypatch):
    _fresh_engine(monkeypatch)
    engine = _make_engine()
    engine.enable_pki()
    assert hasattr(config, 'private_key')
    assert hasattr(config, 'public_key')


# ---------------------------------------------------------------------------
# Env var override
# ---------------------------------------------------------------------------

def test_env_var_private_key_path_is_used(monkeypatch, tmp_path):
    _fresh_engine(monkeypatch)
    # Copy key to a different path to prove env var is followed, not default
    import shutil
    alt_priv = tmp_path / 'alt.pem'
    alt_pub = tmp_path / 'alt.pub'
    shutil.copy(PRIVATE_KEY_PATH, alt_priv)
    shutil.copy(PUBLIC_KEY_PATH, alt_pub)

    monkeypatch.setenv('APPKERNEL_PRIVATE_KEY_PATH', str(alt_priv))
    monkeypatch.setenv('APPKERNEL_PUBLIC_KEY_PATH', str(alt_pub))

    engine = _make_engine()
    engine.enable_pki()
    assert hasattr(config, 'private_key')
    assert hasattr(config, 'public_key')


def test_env_var_takes_priority_over_default(monkeypatch, tmp_path):
    _fresh_engine(monkeypatch)
    import shutil
    alt_priv = tmp_path / 'alt.pem'
    alt_pub = tmp_path / 'alt.pub'
    shutil.copy(PRIVATE_KEY_PATH, alt_priv)
    shutil.copy(PUBLIC_KEY_PATH, alt_pub)

    monkeypatch.setenv('APPKERNEL_PRIVATE_KEY_PATH', str(alt_priv))
    monkeypatch.setenv('APPKERNEL_PUBLIC_KEY_PATH', str(alt_pub))

    # Point cfg_dir somewhere that has NO keys/ folder — if env var is
    # honoured, the engine loads fine; if it falls through to default it fails.
    engine = AppKernelEngine('pki_test', cfg_dir=str(tmp_path), development=True)
    engine.enable_pki()
    assert hasattr(config, 'public_key')


def test_missing_env_var_key_file_raises(monkeypatch):
    _fresh_engine(monkeypatch)
    monkeypatch.setenv('APPKERNEL_PRIVATE_KEY_PATH', '/nonexistent/path/private.pem')
    monkeypatch.setenv('APPKERNEL_PUBLIC_KEY_PATH', '/nonexistent/path/public.pub')
    engine = _make_engine()
    with pytest.raises((FileNotFoundError, OSError)):
        engine.enable_pki()


# ---------------------------------------------------------------------------
# cfg.yml override
# ---------------------------------------------------------------------------

def test_cfg_yml_key_paths_are_used(monkeypatch, tmp_path):
    _fresh_engine(monkeypatch)
    import shutil
    alt_priv = tmp_path / 'cfg_priv.pem'
    alt_pub = tmp_path / 'cfg_pub.pub'
    shutil.copy(PRIVATE_KEY_PATH, alt_priv)
    shutil.copy(PUBLIC_KEY_PATH, alt_pub)

    # Inject config values directly (simulates cfg.yml entries)
    from appkernel.infrastructure import CfgEngine
    original_get = CfgEngine.get

    def patched_get(self, key, default=None):
        if key == 'appkernel.security.private_key_path':
            return str(alt_priv)
        if key == 'appkernel.security.public_key_path':
            return str(alt_pub)
        return original_get(self, key, default)

    monkeypatch.setattr(CfgEngine, 'get', patched_get)
    engine = _make_engine()
    engine.enable_pki()
    assert hasattr(config, 'public_key')


def test_env_var_takes_priority_over_cfg_yml(monkeypatch, tmp_path):
    """Env var must win over cfg.yml when both are set."""
    _fresh_engine(monkeypatch)
    import shutil
    env_priv = tmp_path / 'env.pem'
    env_pub = tmp_path / 'env.pub'
    shutil.copy(PRIVATE_KEY_PATH, env_priv)
    shutil.copy(PUBLIC_KEY_PATH, env_pub)

    monkeypatch.setenv('APPKERNEL_PRIVATE_KEY_PATH', str(env_priv))
    monkeypatch.setenv('APPKERNEL_PUBLIC_KEY_PATH', str(env_pub))

    from appkernel.infrastructure import CfgEngine
    original_get = CfgEngine.get

    def patched_get(self, key, default=None):
        if key == 'appkernel.security.private_key_path':
            return '/nonexistent/cfg_priv.pem'   # would fail if used
        if key == 'appkernel.security.public_key_path':
            return '/nonexistent/cfg_pub.pub'
        return original_get(self, key, default)

    monkeypatch.setattr(CfgEngine, 'get', patched_get)
    engine = AppKernelEngine('pki_test', cfg_dir=str(tmp_path), development=True)
    engine.enable_pki()
    assert hasattr(config, 'public_key')
