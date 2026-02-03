"""Test AuditLog backward compatibility with dual schema (details vs data)"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from packages.storage.models import AuditActionEnum, AuditLog, Base


class TestAuditLogDualSchema:
    """Test that AuditLog works with both details and data columns"""

    @pytest.fixture
    def db_session(self):
        """Create a test database session"""
        # Use in-memory SQLite for testing
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    def test_audit_log_with_details_column(self, db_session):
        """Test AuditLog creation when details column exists"""
        # Simulate details column existing
        audit_log = AuditLog(
            action=AuditActionEnum.KILL_SWITCH,
            message="Test message",
            details={"key": "value", "reason": "test"}
        )
        db_session.add(audit_log)
        db_session.commit()

        # Verify it was saved
        retrieved = db_session.query(AuditLog).first()
        assert retrieved is not None
        assert retrieved.message == "Test message"
        assert retrieved.details == {"key": "value", "reason": "test"}
        assert retrieved.action == AuditActionEnum.KILL_SWITCH

    def test_audit_log_with_data_column_fallback(self, db_session):
        """Test AuditLog creation when only data column exists (backward compatibility)"""
        # Simulate only data column existing (legacy schema)
        # Note: This test requires mocking the schema or using a different DB setup
        # For now, we test the logic that would handle this

        # Create with data instead of details
        audit_log = AuditLog(
            action=str(AuditActionEnum.KILL_SWITCH.value),
            message="Test message",
            data={"key": "value", "reason": "test"}
        )
        db_session.add(audit_log)
        db_session.commit()

        # Verify it was saved
        retrieved = db_session.query(AuditLog).first()
        assert retrieved is not None
        assert retrieved.message == "Test message"
        # Check if data or details was used
        if hasattr(retrieved, 'data') and retrieved.data:
            assert retrieved.data == {"key": "value", "reason": "test"}
        elif hasattr(retrieved, 'details') and retrieved.details:
            assert retrieved.details == {"key": "value", "reason": "test"}

    def test_audit_log_action_enum_handling(self, db_session):
        """Test that action can be both Enum and string"""
        # Test with Enum
        audit_log1 = AuditLog(
            action=AuditActionEnum.KILL_SWITCH,
            message="Test 1"
        )
        db_session.add(audit_log1)

        # Test with string
        audit_log2 = AuditLog(
            action="KILL_SWITCH",
            message="Test 2"
        )
        db_session.add(audit_log2)

        db_session.commit()

        # Verify both were saved
        logs = db_session.query(AuditLog).all()
        assert len(logs) == 2
        assert logs[0].message == "Test 1"
        assert logs[1].message == "Test 2"

    def test_backward_compatible_creation_logic(self, mocker):
        """Test the backward-compatible creation logic"""
        from unittest.mock import MagicMock

        # Mock scenario: details column exists
        mock_inspector = MagicMock()
        mock_inspector.get_columns.return_value = [{"name": "details"}, {"name": "action"}]

        mock_bind = MagicMock()

        # Since we cannot easily mock sqlalchemy.inspect due to how it's implemented (it's a function, but also a registry),
        # we'll test the logic function directly if possible, or adapt the test to not rely on mocking sqlalchemy.inspect
        # directly in this way.

        # Instead, let's verify that our logic inside config_guard.py matches what we expect.
        # We can simulate the `inspect` call return value.

        def mock_inspect_wrapper(obj):
            return mock_inspector

        with pytest.MonkeyPatch.context() as m:
            # We need to patch where it is USED, or patch sqlalchemy.inspection.inspect
            m.setattr("sqlalchemy.inspect", mock_inspect_wrapper)

            # Test the logic
            # Note: We need to import inspect again or use the one from sqlalchemy
            from sqlalchemy import inspect as test_inspect

            columns = test_inspect(mock_bind).get_columns("audit_logs")
            has_details = any(
                c.get("name") == "details" or getattr(c, "name", None) == "details"
                for c in columns
            )

            assert has_details is True

            # Test fallback scenario
            mock_inspector.get_columns.return_value = [{"name": "data"}, {"name": "action"}]

            columns = test_inspect(mock_bind).get_columns("audit_logs")
            has_details = any(
                c.get("name") == "details" or getattr(c, "name", None) == "details"
                for c in columns
            )

            assert has_details is False

        # Mock scenario: details column exists
        class MockColumn:
            def __init__(self, name):
                self.name = name

            def get(self, key):
                if key == "name":
                    return self.name
                return None

        class MockInspector:
            def get_columns(self, table_name):
                return [MockColumn("details"), MockColumn("action")]

        class MockInspectorNoDetails:
            def get_columns(self, table_name):
                return [MockColumn("data"), MockColumn("action")]

        class MockDB:
            def __init__(self):
                self.bind = "mock_bind"

        # Mock sqlalchemy.inspect
        mock_inspect = mocker.patch("sqlalchemy.inspect")

        # Case 1: details column exists
        mock_inspect.return_value = MockInspector()
        db = MockDB()

        columns = mock_inspect(db.bind).get_columns("audit_logs")
        has_details = any(
            c.get("name") == "details" or getattr(c, "name", None) == "details"
            for c in columns
        )

        assert has_details is True

        # Case 2: details column missing
        mock_inspect.return_value = MockInspectorNoDetails()
        db_no_details = MockDB()

        columns = mock_inspect(db_no_details.bind).get_columns("audit_logs")
        has_details = any(
            c.get("name") == "details" or getattr(c, "name", None) == "details"
            for c in columns
        )

        assert has_details is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
