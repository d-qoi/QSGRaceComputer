from typing import cast
import pytest
from qsgrc.messages import (
    unpack,
    AlertMessage,
    AlertConfigMessage,
    OBD2Datapoint,
    SSEMessage,
)
from qsgrc.messages import AlertConditions


class TestMessageUnpack:
    def test_unpack_alert_message(self):
        """Test unpacking an AlertMessage"""
        message = "A:engine=rpm@1@1500"
        result = unpack(message)

        assert isinstance(result, AlertMessage)
        assert result.name == "engine"
        assert result.listen_to == "rpm"
        assert result.triggered is True
        assert result.val == 1500.0

    def test_unpack_alert_config_message(self):
        """Test unpacking an AlertConfigMessage"""
        message = "AC:engine=rpm@GT@3000@High RPM"
        result = unpack(message)

        assert isinstance(result, AlertConfigMessage)
        assert result.name == "engine"
        assert result.listen_to == "rpm"
        assert result.condition == AlertConditions.GT
        assert result.threshold == 3000.0
        assert result.msg == "High RPM"

    def test_unpack_obd2_datapoint(self):
        """Test unpacking an OBD2Datapoint"""
        message = "OBD:engine=rpm=1500"
        result = unpack(message)

        assert isinstance(result, OBD2Datapoint)
        assert result.name == "engine"
        assert result.value == "rpm=1500"

    def test_unpack_sse_message(self):
        """Test unpacking an SSEMessage"""
        message = "SSE:status=connected"
        result = unpack(message)

        assert isinstance(result, SSEMessage)
        assert result.name == "status"
        assert result.value == "connected"

    def test_invalid_message_format(self):
        """Test handling invalid message format"""
        invalid_message = "This is not a valid message"

        with pytest.raises(ValueError) as excinfo:
            unpack(invalid_message)

        assert "Invalid Message Format" in str(excinfo.value)

    def test_unknown_leader(self):
        """Test handling unknown message leader"""
        unknown_leader = "UNKNOWN:test=value"

        with pytest.raises(ValueError) as excinfo:
            unpack(unknown_leader)

        assert "Unknown Leader" in str(excinfo.value)

    def test_leader_mismatch(self):
        """Test handling leader mismatch within message class"""
        mismatched = (
            "AC:test=rpm@1@1500"  # Using AlertConfig leader but AlertMessage format
        )

        with pytest.raises(ValueError) as excinfo:
            unpack(mismatched)

        assert "leader mismatch" in str(excinfo.value) or "Invalid format" in str(
            excinfo.value
        )

    def test_all_registered_leaders(self):
        """Test that all leaders in the registry are unique"""
        from qsgrc.messages import MESSAGE_REGISTERY

        # Check all leaders are unique
        leaders = list(MESSAGE_REGISTERY.keys())
        assert len(leaders) == len(set(leaders)), "Duplicate leaders in registry"

        # Check all values are BaseMessage subclasses
        from qsgrc.messages.core import BaseMessage

        for cls in MESSAGE_REGISTERY.values():
            assert issubclass(
                cls, BaseMessage
            ), f"{cls} is not a subclass of BaseMessage"

    def test_malformed_message_content(self):
        """Test handling malformed message content"""
        # AlertConfigMessage with invalid condition
        malformed = "AC:engine=rpm@INVALID@3000@High RPM"

        with pytest.raises(ValueError):
            unpack(malformed)


class TestMessagePacking:
    def test_pack_alert_message(self):
        """Test converting AlertMessage to string"""
        # Create message
        msg = AlertMessage("engine", "rpm", True, 1500)

        # Test string representation
        packed = str(msg)
        assert packed == "A:engine=rpm@1@1500"

        # Round-trip test
        unpacked = unpack(packed)
        assert isinstance(unpacked, AlertMessage)
        assert unpacked.name == "engine"
        assert unpacked.listen_to == "rpm"
        assert unpacked.triggered is True
        assert unpacked.val == 1500.0

    def test_pack_alert_message_with_error(self):
        """Test AlertMessage with error string value"""
        # Create message with error string
        msg = AlertMessage("engine", "rpm", False, "sensor_error")

        # Test string representation
        packed = str(msg)
        assert packed == "A:engine=rpm@0@sensor_error"

        # Round-trip test

        unpacked = unpack(packed)
        assert unpacked.val == "sensor_error"

    def test_pack_alert_config_message(self):
        """Test converting AlertConfigMessage to string"""
        # Create message
        msg = AlertConfigMessage("engine", "rpm", AlertConditions.GT, 3000, "High RPM")

        # Test string representation
        packed = str(msg)
        assert packed == "AC:engine=rpm@GT@3000@High RPM"

        # Round-trip test

        unpacked = unpack(packed)
        assert isinstance(unpacked, AlertConfigMessage)
        assert unpacked.name == "engine"
        assert unpacked.listen_to == "rpm"
        assert unpacked.condition == AlertConditions.GT
        assert unpacked.threshold == 3000.0
        assert unpacked.msg == "High RPM"

    def test_pack_obd2_datapoint(self):
        """Test converting OBD2Datapoint to string"""
        # Create message
        msg = OBD2Datapoint("engine", "rpm=1500")

        # Test string representation
        packed = str(msg)
        assert packed == "OBD:engine=rpm=1500"

        # Round-trip test

        unpacked = unpack(packed)
        assert isinstance(unpacked, OBD2Datapoint)
        assert unpacked.name == "engine"
        assert unpacked.value == "rpm=1500"

    def test_pack_sse_message(self):
        """Test converting SSEMessage to string"""
        # Create message
        msg = SSEMessage("status", "connected")

        # Test string representation
        packed = str(msg)
        assert packed == "SSE:status=connected"

        # Round-trip test

        unpacked = unpack(packed)
        assert isinstance(unpacked, SSEMessage)
        assert unpacked.name == "status"
        assert unpacked.value == "connected"

    def test_alert_message_empty_values(self):
        """Test AlertMessage with empty values"""
        msg = AlertMessage("engine", "rpm")
        packed = str(msg)
        assert packed == "A:engine=rpm@0@"

        unpacked = unpack(packed)
        assert unpacked.triggered is False
        assert unpacked.val == 0.0 or unpacked.val == ""  # Depending on implementation

    def test_alert_config_empty_message(self):
        """Test AlertConfigMessage with empty message"""
        msg = AlertConfigMessage("engine", "rpm", AlertConditions.LT, 1000)
        packed = str(msg)
        assert packed == "AC:engine=rpm@LT@1000@"

        unpacked = unpack(packed)
        assert unpacked.msg == ""

    def test_round_trip_all_condition_types(self):
        """Test round-trip for all AlertConditions types"""
        for condition in AlertConditions:
            msg = AlertConfigMessage("engine", "rpm", condition, 1000)
            packed = str(msg)

            unpacked = unpack(packed)
            assert unpacked.condition == condition
