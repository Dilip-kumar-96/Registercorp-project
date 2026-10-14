"""
test_dashboard_api.py — Unit tests for Flask dashboard API endpoints
"""
import pytest
from unittest.mock import patch
from flagger.dashboard import app as dashboard_module


@pytest.fixture
def client():
    dashboard_module.app.config["TESTING"] = True
    with dashboard_module.app.test_client() as c:
        yield c


def test_dry_run_endpoint_toggle(client, tmp_path):
    env_file = tmp_path / ".env"
    with patch("flagger.config.ENV_PATH", env_file):
        with patch("flagger.config._ROOT", tmp_path):
            # Turn dry run off
            res = client.post("/api/bot/dry-run", json={"dry_run": False})
            assert res.status_code == 200
            data = res.get_json()
            assert data["success"] is True
            assert data["dry_run"] is False

            # Turn dry run on
            res = client.post("/api/bot/dry-run", json={"dry_run": True})
            assert res.status_code == 200
            data = res.get_json()
            assert data["success"] is True
            assert data["dry_run"] is True


def test_settings_save_auto_start_bot(client, tmp_path):
    env_file = tmp_path / ".env"
    with patch("flagger.config.ENV_PATH", env_file):
        with patch("flagger.config._ROOT", tmp_path):
            res = client.post("/api/settings", json={"auto_start_bot": True})
            assert res.status_code == 200
            assert res.get_json()["success"] is True
            from flagger import config
            assert config.is_auto_start_bot() is True
