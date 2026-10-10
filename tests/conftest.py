"""
conftest.py — Shared pytest fixtures.
"""
import sys
from pathlib import Path

# Add src/ to path so tests can import flagger modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest


@pytest.fixture
def portal_confirmed_response():
    """Sample portal API response with a CONFIRMED tracking number."""
    return {
        "success": True,
        "statusCode": 200,
        "data": [
            {
                "STATUS": "CONFIRMED",
                "TRACKING_NUMBER": "384007184685",
                "code": "246dfa1d40",
                "CARRIER": "FedEx",
            }
        ],
        "meta": {"total": 1, "max": 25, "offset": 0, "count": 1},
    }


@pytest.fixture
def portal_empty_response():
    """Portal API response with no records."""
    return {
        "success": True,
        "data": [],
        "meta": {"total": 0, "max": 25, "count": 0},
    }


@pytest.fixture
def finditem_response():
    """Sample Outlook FindItem response with one unflagged FedEx email."""
    return {
        "Body": {
            "ResponseMessages": {
                "Items": [
                    {
                        "RootFolder": {
                            "TotalItemsInView": 1,
                            "IncludesLastItemInRange": True,
                            "Items": [
                                {
                                    "__type": "Message:#Exchange",
                                    "ItemId": {
                                        "Id": "AAAID001",
                                        "ChangeKey": "CKAAAA001",
                                    },
                                    "Flag": {"FlagStatus": "NotFlagged"},
                                    "Preview": (
                                        "Account Name:   fedex\r\n"
                                        "Carrier:        FedEx\r\n"
                                        "Tracking Number:        384007184685\r\n"
                                        "Shipper Company:        TMRW\r\n"
                                    ),
                                    "DateTimeReceived": "2026-10-10T16:01:11-04:00",
                                }
                            ],
                        }
                    }
                ]
            }
        }
    }


@pytest.fixture
def updateitem_success_response():
    """Sample UpdateItem success response."""
    return {
        "Body": {
            "ResponseMessages": {
                "Items": [
                    {
                        "ResponseCode": "NoError",
                        "ResponseClass": "Success",
                        "Items": [{"ItemId": {"Id": "AAAID001", "ChangeKey": "CKNEW002"}}],
                    }
                ]
            }
        }
    }
