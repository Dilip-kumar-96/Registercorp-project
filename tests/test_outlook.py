"""
test_outlook.py — Unit tests for outlook_module.py
"""
import pytest
from unittest.mock import MagicMock, patch

from flagger.outlook_module import (
    find_unflagged_fedex_emails,
    flag_email,
    get_item_change_key,
    _extract_tracking_number,
    OutlookSessionExpiredError,
    OutlookNetworkError,
    OutlookAPIError,
    _set_cookies,
)

# Seed cookies so requests don't fail on missing session
@pytest.fixture(autouse=True)
def seed_cookies():
    _set_cookies({"X-OWA-CANARY": "test-canary", "cookie1": "val1"})


def _mock_post_response(json_data=None, status_code=200, text=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.headers = {}
    mock.text = text or str(json_data)
    mock.json.return_value = json_data
    return mock


class TestExtractTrackingNumber:
    def test_extracts_correctly(self):
        preview = "Account Name:   fedex\r\nTracking Number:        384007184685\r\n"
        assert _extract_tracking_number(preview) == "384007184685"

    def test_returns_none_when_missing(self):
        assert _extract_tracking_number("No tracking info here") is None

    def test_handles_extra_whitespace(self):
        preview = "Tracking Number:   999000111222"
        assert _extract_tracking_number(preview) == "999000111222"


class TestFindUnflaggedEmails:
    def test_returns_unflagged_emails(self, finditem_response):
        with patch("flagger.outlook_module.requests.post") as mock_post:
            mock_post.return_value = _mock_post_response(finditem_response)
            result = find_unflagged_fedex_emails("myfda@registrarcorp.com")
        assert len(result) == 1
        assert result[0]["tracking_number"] == "384007184685"
        assert result[0]["item_id"] == "AAAID001"
        assert result[0]["change_key"] == "CKAAAA001"

    def test_skips_already_flagged_emails(self, finditem_response):
        finditem_response["Body"]["ResponseMessages"]["Items"][0]["RootFolder"]["Items"][0][
            "Flag"
        ]["FlagStatus"] = "Flagged"
        with patch("flagger.outlook_module.requests.post") as mock_post:
            mock_post.return_value = _mock_post_response(finditem_response)
            result = find_unflagged_fedex_emails("myfda@registrarcorp.com")
        assert result == []

    def test_skips_emails_without_tracking_number(self, finditem_response):
        finditem_response["Body"]["ResponseMessages"]["Items"][0]["RootFolder"]["Items"][0][
            "Preview"
        ] = "No tracking number here"
        with patch("flagger.outlook_module.requests.post") as mock_post:
            mock_post.return_value = _mock_post_response(finditem_response)
            result = find_unflagged_fedex_emails("myfda@registrarcorp.com")
        assert result == []

    def test_session_expired_on_redirect(self):
        with patch("flagger.outlook_module.requests.post") as mock_post:
            mock_post.return_value = _mock_post_response(status_code=302)
            with pytest.raises(OutlookSessionExpiredError):
                find_unflagged_fedex_emails("myfda@registrarcorp.com")

    def test_session_expired_on_login_html(self):
        with patch("flagger.outlook_module.requests.post") as mock_post:
            resp = _mock_post_response(status_code=200,
                                       text="<html>Sign in to microsoftonline.com</html>")
            resp.json.side_effect = ValueError("not json")
            mock_post.return_value = resp
            with pytest.raises(OutlookSessionExpiredError):
                find_unflagged_fedex_emails("myfda@registrarcorp.com")

    def test_network_error_retries(self):
        import requests as req
        with patch("flagger.outlook_module.requests.post") as mock_post:
            mock_post.side_effect = req.ConnectionError("no connection")
            with patch("flagger.outlook_module.time.sleep"):
                with pytest.raises(OutlookNetworkError):
                    find_unflagged_fedex_emails("myfda@registrarcorp.com")
            assert mock_post.call_count == 3  # MAX_RETRIES


class TestFlagEmail:
    def test_dry_run_returns_success_without_posting(self):
        with patch("flagger.outlook_module.requests.post") as mock_post:
            result = flag_email("AAAID001", "CKAAAA001", dry_run=True)
        mock_post.assert_not_called()
        assert result["success"] is True
        assert result["dry_run"] is True

    def test_successful_flag(self, updateitem_success_response):
        with patch("flagger.outlook_module.requests.post") as mock_post:
            mock_post.return_value = _mock_post_response(updateitem_success_response)
            result = flag_email("AAAID001", "CKAAAA001", dry_run=False)
        assert result["success"] is True
        assert result["new_change_key"] == "CKNEW002"
        assert result["error_code"] is None

    def test_item_not_found(self):
        data = {
            "Body": {
                "ResponseMessages": {
                    "Items": [{"ResponseCode": "ErrorItemNotFound", "ResponseClass": "Error"}]
                }
            }
        }
        with patch("flagger.outlook_module.requests.post") as mock_post:
            mock_post.return_value = _mock_post_response(data)
            result = flag_email("AAAID001", "CKAAAA001", dry_run=False)
        assert result["success"] is False
        assert result["error_code"] == "ErrorItemNotFound"

    def test_changekey_mismatch(self):
        data = {
            "Body": {
                "ResponseMessages": {
                    "Items": [{"ResponseCode": "ErrorChangeKeyRequired", "ResponseClass": "Error"}]
                }
            }
        }
        with patch("flagger.outlook_module.requests.post") as mock_post:
            mock_post.return_value = _mock_post_response(data)
            result = flag_email("AAAID001", "OLD_CK", dry_run=False)
        assert result["success"] is False
        assert result["error_code"] == "ErrorChangeKeyRequired"


class TestGetItemChangeKey:
    def test_returns_change_key(self):
        data = {
            "Body": {
                "ResponseMessages": {
                    "Items": [{"Items": [{"ItemId": {"Id": "ID1", "ChangeKey": "NEWCK"}}]}]
                }
            }
        }
        with patch("flagger.outlook_module.requests.post") as mock_post:
            mock_post.return_value = _mock_post_response(data)
            ck = get_item_change_key("ID1")
        assert ck == "NEWCK"

    def test_returns_none_on_error(self):
        with patch("flagger.outlook_module.requests.post") as mock_post:
            mock_post.return_value = _mock_post_response({"bad": "data"})
            ck = get_item_change_key("ID1")
        assert ck is None
