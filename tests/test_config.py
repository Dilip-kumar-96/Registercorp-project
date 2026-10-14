"""
test_config.py — Unit tests for config.py and dashboard mode control endpoints
"""
import os
from pathlib import Path
from unittest.mock import patch

from flagger import config


def test_get_app_dir_not_frozen():
    with patch.object(config.sys, "frozen", False, create=True):
        d = config.get_app_dir()
        assert isinstance(d, Path)
        assert d.exists()


def test_get_app_dir_frozen(tmp_path):
    fake_exe = tmp_path / "FedExFlagger.exe"
    with patch.object(config.sys, "frozen", True, create=True):
        with patch.object(config.sys, "executable", str(fake_exe)):
            d = config.get_app_dir()
            assert d == tmp_path


def test_auto_start_bot_toggle(tmp_path):
    env_file = tmp_path / ".env"
    with patch.object(config, "ENV_PATH", env_file):
        with patch.object(config, "_ROOT", tmp_path):
            assert config.is_auto_start_bot() is False
            config.update_auto_start_bot(True)
            assert config.is_auto_start_bot() is True
            config.update_auto_start_bot(False)
            assert config.is_auto_start_bot() is False


def test_dry_run_toggle(tmp_path):
    env_file = tmp_path / ".env"
    with patch.object(config, "ENV_PATH", env_file):
        with patch.object(config, "_ROOT", tmp_path):
            config.update_dry_run(True)
            assert config.is_dry_run() is True
            config.update_dry_run(False)
            assert config.is_dry_run() is False
