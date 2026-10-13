"""
test_portal.py — Unit tests for portal_module.py

All HTTP calls are mocked — no real API calls are made during tests.
"""
import pytest
from unittest.mock import MagicMock, patch

from flagger.portal_module import (
    fetch_statuses,
    validate_token,
    PortalTokenExpiredError,
    PortalNetworkError,
    PortalParseError,
)


def _mock_response(json_data=None, status_code=200, raises=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.raise_for_status = MagicMock()
    if raises:
        mock.json.side_effect = raises
    else:
        mock.json.return_value = json_data
        mock.text = str(json_data)
    return mock


class TestFetchStatuses:
    def test_single_page_confirmed(self, portal_confirmed_response):
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.return_value = _mock_response(portal_confirmed_response)
            result = fetch_statuses("valid-token", date_range_days=2)
        assert result["384007184685"] == "CONFIRMED"

    def test_multiple_statuses(self):
        data = {
            "success": True,
            "data": [
                {"TRACKING_NUMBER": "111", "STATUS": "CONFIRMED"},
                {"TRACKING_NUMBER": "222", "STATUS": "FAILED"},
                {"TRACKING_NUMBER": "333", "STATUS": "SUBMITTED"},
                {"TRACKING_NUMBER": "444", "STATUS": "PROCESSING"},
            ],
            "meta": {"count": 4},
        }
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.return_value = _mock_response(data)
            result = fetch_statuses("token", 2)
        assert result["111"] == "CONFIRMED"
        assert result["222"] == "FAILED"
        assert result["333"] == "SUBMITTED"
        assert result["444"] == "PROCESSING"

    def test_empty_response(self, portal_empty_response):
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.return_value = _mock_response(portal_empty_response)
            result = fetch_statuses("token", 2)
        assert result == {}

    def test_token_expired_401(self):
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.return_value = _mock_response(status_code=401)
            mock_get.return_value.raise_for_status = MagicMock()
            with pytest.raises(PortalTokenExpiredError):
                fetch_statuses("bad-token", 2)

    def test_token_expired_403(self):
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.return_value = _mock_response(status_code=403)
            with pytest.raises(PortalTokenExpiredError):
                fetch_statuses("bad-token", 2)

    def test_api_success_false_with_token_message(self):
        data = {"success": False, "message": "Token is invalid or expired"}
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.return_value = _mock_response(data)
            with pytest.raises(PortalTokenExpiredError):
                fetch_statuses("bad-token", 2)

    def test_api_success_false_generic(self):
        data = {"success": False, "message": "Internal server error"}
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.return_value = _mock_response(data)
            with pytest.raises(PortalParseError):
                fetch_statuses("token", 2)

    def test_network_error_retries_then_raises(self):
        import requests as req
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.side_effect = req.ConnectionError("connection refused")
            with patch("flagger.portal_module.time.sleep"):  # Don't actually sleep
                with pytest.raises(PortalNetworkError):
                    fetch_statuses("token", 2)
            assert mock_get.call_count == 3  # MAX_RETRIES

    def test_timeout_retries_then_raises(self):
        import requests as req
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.side_effect = req.Timeout("timed out")
            with patch("flagger.portal_module.time.sleep"):
                with pytest.raises(PortalNetworkError):
                    fetch_statuses("token", 2)

    def test_invalid_json_response(self):
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.return_value = _mock_response(raises=ValueError("bad json"))
            with pytest.raises(PortalParseError):
                fetch_statuses("token", 2)

    def test_missing_data_field(self):
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.return_value = _mock_response({"success": True, "records": []})
            with pytest.raises(PortalParseError):
                fetch_statuses("token", 2)

    def test_pagination_fetches_all_pages(self):
        """When first page returns 25 records, should fetch the next page."""
        page1 = {
            "success": True,
            "data": [{"TRACKING_NUMBER": str(i), "STATUS": "CONFIRMED"} for i in range(25)],
            "meta": {"count": 25, "searchAfter": [123456, "cursor1"]},
        }
        page2 = {
            "success": True,
            "data": [{"TRACKING_NUMBER": "999", "STATUS": "FAILED"}],
            "meta": {"count": 1},
        }
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_response(page1),
                _mock_response(page2),
            ]
            result = fetch_statuses("token", 2)
        assert len(result) == 26
        assert result["999"] == "FAILED"
        assert mock_get.call_count == 2


class TestTestToken:
    def test_valid_token_returns_true(self, portal_empty_response):
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.return_value = _mock_response(portal_empty_response)
            valid, msg = validate_token("good-token")
        assert valid is True

    def test_expired_token_returns_false(self):
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.return_value = _mock_response(status_code=401)
            valid, msg = validate_token("bad-token")
        assert valid is False
        assert "expired" in msg.lower() or "invalid" in msg.lower()

    def test_network_error_returns_false(self):
        import requests as req
        with patch("flagger.portal_module.requests.get") as mock_get:
            mock_get.side_effect = req.ConnectionError("no network")
            with patch("flagger.portal_module.time.sleep"):
                valid, msg = validate_token("token")
        assert valid is False
        assert "network" in msg.lower()
