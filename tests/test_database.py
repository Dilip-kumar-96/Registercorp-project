"""
test_database.py — Unit tests for database.py
"""
import pytest
from flagger import database


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Use a temp file for every test — fully isolated."""
    monkeypatch.setattr(database, "_DB_PATH", tmp_path / "test.db")
    database.initialize()


class TestInitialize:
    def test_starts_empty(self):
        counts = database.get_counts()
        assert all(v == 0 for v in counts.values())

    def test_wipes_previous_data(self):
        database.add_email("TRACK001", "ID001", "CK001")
        database.initialize()  # Wipe
        assert database.get_status("TRACK001") is None


class TestAddEmail:
    def test_adds_as_pending(self):
        database.add_email("TRACK001", "ID001", "CK001")
        assert database.get_status("TRACK001") == "PENDING"

    def test_ignores_duplicate(self):
        database.add_email("TRACK001", "ID001", "CK001")
        database.add_email("TRACK001", "ID001", "CK001")  # Should not raise
        assert database.get_counts()["pending"] == 1


class TestStatusTransitions:
    def test_pending_to_confirmed(self):
        database.add_email("T1", "ID1", "CK1")
        database.update_status("T1", "CONFIRMED", portal_status="CONFIRMED")
        assert database.get_status("T1") == "CONFIRMED"

    def test_confirmed_to_flagged(self):
        database.add_email("T1", "ID1", "CK1")
        database.update_status("T1", "CONFIRMED")
        database.update_status("T1", "FLAGGED")
        assert database.get_status("T1") == "FLAGGED"

    def test_pending_to_failed(self):
        database.add_email("T1", "ID1", "CK1")
        database.update_status("T1", "FAILED")
        assert database.get_status("T1") == "FAILED"

    def test_confirmed_to_gone(self):
        database.add_email("T1", "ID1", "CK1")
        database.update_status("T1", "CONFIRMED")
        database.update_status("T1", "GONE")
        assert database.get_status("T1") == "GONE"

    def test_confirmed_to_error(self):
        database.add_email("T1", "ID1", "CK1")
        database.update_status("T1", "CONFIRMED")
        database.update_status("T1", "ERROR", error_message="Retry failed")
        assert database.get_status("T1") == "ERROR"


class TestGetPendingAndConfirmed:
    def test_get_pending(self):
        database.add_email("T1", "ID1", "CK1")
        database.add_email("T2", "ID2", "CK2")
        database.update_status("T2", "CONFIRMED")
        pending = database.get_pending()
        assert len(pending) == 1
        assert pending[0]["tracking_number"] == "T1"

    def test_get_confirmed(self):
        database.add_email("T1", "ID1", "CK1")
        database.add_email("T2", "ID2", "CK2")
        database.update_status("T1", "CONFIRMED")
        confirmed = database.get_confirmed()
        assert len(confirmed) == 1
        assert confirmed[0]["tracking_number"] == "T1"


class TestCounts:
    def test_counts_all_statuses(self):
        database.add_email("T1", "ID1", "CK1")
        database.add_email("T2", "ID2", "CK2")
        database.add_email("T3", "ID3", "CK3")
        database.update_status("T2", "CONFIRMED")
        database.update_status("T2", "FLAGGED")
        database.update_status("T3", "FAILED")

        counts = database.get_counts()
        assert counts["pending"] == 1
        assert counts["flagged"] == 1
        assert counts["failed"] == 1


class TestChangeKey:
    def test_update_change_key(self):
        database.add_email("T1", "ID1", "OLD_CK")
        database.update_change_key("T1", "NEW_CK")
        all_emails = database.get_all()
        assert all_emails[0]["change_key"] == "NEW_CK"


class TestActivityLog:
    def test_log_and_retrieve(self):
        database.log_activity("info", "FLAGGED", tracking="TRACK001", detail="test")
        activity = database.get_activity(limit=10)
        assert len(activity) == 1
        assert activity[0]["event"] == "FLAGGED"
        assert activity[0]["tracking"] == "TRACK001"

    def test_returns_most_recent_first(self):
        database.log_activity("info", "EVENT_A")
        database.log_activity("info", "EVENT_B")
        activity = database.get_activity(limit=10)
        assert activity[0]["event"] == "EVENT_B"


class TestSessionMeta:
    def test_set_and_get(self):
        database.set_meta("test_key", "test_value")
        assert database.get_meta("test_key") == "test_value"

    def test_get_default(self):
        assert database.get_meta("missing", default="default_val") == "default_val"

    def test_overwrite(self):
        database.set_meta("key", "val1")
        database.set_meta("key", "val2")
        assert database.get_meta("key") == "val2"
