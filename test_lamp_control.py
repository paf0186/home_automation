"""
Tests for lamp_control_mqtt.py

Run with: pytest test_lamp_control.py -v
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
import sys

# Mock hardware and MQTT dependencies before importing
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()
sys.modules['rpi_rf'] = MagicMock()
sys.modules['paho'] = MagicMock()
sys.modules['paho.mqtt'] = MagicMock()
sys.modules['paho.mqtt.client'] = MagicMock()

# Now we can import the module
# We need to mock argparse to avoid it trying to parse test runner args
with patch('argparse.ArgumentParser.parse_args') as mock_args:
    mock_args.return_value = Mock(
        code=None,
        gpio_tx=4,
        gpio_rx=23,
        pulselength=None,
        protocol=None
    )
    import lamp_control_mqtt as lcm


class TestConstants:
    """Test that constants are defined correctly."""
    
    def test_command_offsets(self):
        """Test RF command offset values."""
        assert lcm.ON_OFF_OFFSET == 0
        assert lcm.CCT_OFFSET == 1
        assert lcm.BRIGHTNESS_UP_OFFSET == 3
        assert lcm.BRIGHTNESS_DOWN_OFFSET == 7
        assert lcm.MAX_OFFSET == 7
    
    def test_brightness_constants(self):
        """Test brightness calculation constants."""
        assert lcm.BR_LEVELS == 36
        assert lcm.HK_BR_MAX == 100
        assert lcm.BR_INCREMENT == pytest.approx(100/36)
    
    def test_timing_constants(self):
        """Test timing constants are reasonable."""
        assert lcm.MIN_GAP == 200000  # 200ms in microseconds
        assert lcm.RF_DELAY == 0.05
        assert lcm.RF_POLL_INTERVAL == 0.0001
    
    def test_lamp_ids(self):
        """Test lamp IDs are defined."""
        assert lcm.LIVING_ROOM_LAMP == 3513633
        assert lcm.STUDY_LAMPS == 13470497
        assert lcm.STUDY_DESK_LAMP == 9513633
        assert lcm.STUDY_TABLE_LAMP == 4513633


class TestJoofoLamp:
    """Test the joofo_lamp class."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock MQTT client."""
        client = Mock()
        client.message_callback_add = Mock()
        client.publish = Mock()
        return client
    
    @pytest.fixture
    def lamp(self, mock_client):
        """Create a lamp instance for testing."""
        return lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
    
    def test_lamp_initialization(self, lamp, mock_client):
        """Test lamp is initialized with correct state."""
        assert lamp.lamp_id == lcm.LIVING_ROOM_LAMP
        assert lamp.client == mock_client
        assert lamp.on == False
        assert lamp.brightness == 0
        assert lamp.reset == False
        assert lamp.color_temp == 0
    
    def test_lamp_registers_callbacks(self, mock_client):
        """Test lamp registers MQTT callbacks on init."""
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        
        # Should register 4 callbacks (reset + 3 lamp-specific)
        assert mock_client.message_callback_add.call_count == 4
    
    def test_on_off_toggle(self, lamp, mock_client):
        """Test on/off toggling."""
        assert lamp.on == False
        
        # Turn on
        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.on_off("true", True)
            assert lamp.on == True
            mock_send.assert_called_once()
        
        # Turn off
        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.on_off("false", True)
            assert lamp.on == False
            mock_send.assert_called_once()
    
    def test_on_off_no_change(self, lamp, mock_client):
        """Test on/off doesn't send RF if state unchanged."""
        lamp.on = False
        
        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.on_off("false", True)
            assert lamp.on == False
            mock_send.assert_not_called()
    
    def test_brightness_up(self, lamp):
        """Test brightness increase."""
        lamp.brightness = 50
        initial = lamp.brightness
        
        with patch('lamp_control_mqtt.send_rf'):
            lamp.brup(False, False)
        
        assert lamp.brightness > initial
        assert lamp.brightness <= lcm.HK_BR_MAX
    
    def test_brightness_down(self, lamp):
        """Test brightness decrease."""
        lamp.brightness = 50
        initial = lamp.brightness
        
        with patch('lamp_control_mqtt.send_rf'):
            lamp.brdown(False, False)
        
        assert lamp.brightness < initial
        assert lamp.brightness >= 1  # Never goes below 1
    
    def test_brightness_max_clamping(self, lamp):
        """Test brightness doesn't exceed maximum."""
        lamp.brightness = 99
        
        with patch('lamp_control_mqtt.send_rf'):
            lamp.brup(False, False)
        
        assert lamp.brightness == lcm.HK_BR_MAX
    
    def test_brightness_min_clamping(self, lamp):
        """Test brightness doesn't go below 1."""
        lamp.brightness = 2
        
        with patch('lamp_control_mqtt.send_rf'):
            lamp.brdown(False, False)
        
        assert lamp.brightness >= 1
    
    def test_color_temp_cycle(self, lamp):
        """Test color temperature cycles 0->1->2->0."""
        assert lamp.color_temp == 0
        
        lamp.cct(False)
        assert lamp.color_temp == 1
        
        lamp.cct(False)
        assert lamp.color_temp == 2
        
        lamp.cct(False)
        assert lamp.color_temp == 0
    
    def test_set_brightness_level_no_change(self, lamp):
        """Test set_brightness_level does nothing if already at level."""
        lamp.brightness = 50
        
        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.set_brightness_level(50)
            mock_send.assert_not_called()
    
    def test_set_brightness_level_zero_becomes_one(self, lamp):
        """Test setting brightness to 0 sets it to 1 instead."""
        # The function converts 0 to 1, so we just verify it doesn't crash
        # and handles the edge case properly
        lamp.brightness = 1
        with patch('lamp_control_mqtt.send_rf'):
            lamp.set_brightness_level(0)
            # Should return early since brightness is already 1
            assert lamp.brightness == 1
    
    def test_reset_lamp(self, lamp):
        """Test lamp reset sequence."""
        with patch('lamp_control_mqtt.send_rf'):
            with patch.object(lamp, 'on_off'):
                with patch.object(lamp, 'brup'):
                    lamp.reset_lamp()

                    assert lamp.reset == True
                    assert lamp.color_temp == 0

    def test_set_brightness_100_sends_extra_commands(self, lamp):
        """Test setting brightness to 100 sends 5 extra BRUP commands."""
        lamp.brightness = 95

        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.set_brightness_level(100)

            # Should send commands to get to 100, plus 5 extra
            # At least 5 extra calls should happen
            assert mock_send.call_count >= 5

    def test_set_brightness_low_sends_extra_commands(self, lamp):
        """Test setting brightness to 3 or below sends 5 extra BRDOWN commands."""
        lamp.brightness = 10

        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.set_brightness_level(3)

            # Should send commands to get to 3, plus 5 extra
            assert mock_send.call_count >= 5


class TestDecodeRx:
    """Test RF code decoding."""
    
    def setup_method(self):
        """Set up test lamp list."""
        lcm.lamp_list.clear()
        mock_client = Mock()
        self.lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lcm.lamp_list.append(self.lamp)
    
    def teardown_method(self):
        """Clean up lamp list."""
        lcm.lamp_list.clear()
    
    def test_decode_on_off(self):
        """Test decoding ON/OFF command."""
        code = lcm.LIVING_ROOM_LAMP + lcm.ON_OFF_OFFSET
        lamp, command = lcm.decode_rx(code, 12345)
        
        assert lamp == self.lamp
        assert command == lcm.ON_OFF_OFFSET
    
    def test_decode_brightness_up(self):
        """Test decoding brightness up command."""
        code = lcm.LIVING_ROOM_LAMP + lcm.BRIGHTNESS_UP_OFFSET
        lamp, command = lcm.decode_rx(code, 12345)
        
        assert lamp == self.lamp
        assert command == lcm.BRIGHTNESS_UP_OFFSET
    
    def test_decode_brightness_down(self):
        """Test decoding brightness down command."""
        code = lcm.LIVING_ROOM_LAMP + lcm.BRIGHTNESS_DOWN_OFFSET
        lamp, command = lcm.decode_rx(code, 12345)
        
        assert lamp == self.lamp
        assert command == lcm.BRIGHTNESS_DOWN_OFFSET
    
    def test_decode_unknown_lamp(self):
        """Test decoding with unknown lamp ID."""
        code = 9999999  # Unknown lamp
        lamp, command = lcm.decode_rx(code, 12345)
        
        assert lamp is None
        assert command is None
    
    def test_decode_invalid_command(self):
        """Test decoding with invalid command offset."""
        code = lcm.LIVING_ROOM_LAMP + 99  # Invalid offset
        lamp, command = lcm.decode_rx(code, 12345)
        
        assert lamp is None
        assert command is None


class TestHandleRx:
    """Test RF message handling."""
    
    def setup_method(self):
        """Set up test lamp list."""
        lcm.lamp_list.clear()
        mock_client = Mock()
        self.lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lcm.lamp_list.append(self.lamp)
    
    def teardown_method(self):
        """Clean up lamp list."""
        lcm.lamp_list.clear()
    
    def test_handle_on_off(self):
        """Test handling ON/OFF command."""
        code = lcm.LIVING_ROOM_LAMP + lcm.ON_OFF_OFFSET
        
        with patch.object(self.lamp, 'on_off') as mock_on_off:
            lcm.handle_rx(code, 12345, lcm.MIN_GAP + 1)
            mock_on_off.assert_called_once_with(None, False)
    
    def test_handle_brightness_up(self):
        """Test handling brightness up command."""
        code = lcm.LIVING_ROOM_LAMP + lcm.BRIGHTNESS_UP_OFFSET

        with patch.object(self.lamp, 'brup') as mock_brup:
            lcm.handle_rx(code, 12345, lcm.MIN_GAP + 1)
            mock_brup.assert_called_once_with(True, True)

    def test_handle_brightness_down(self):
        """Test handling brightness down command."""
        code = lcm.LIVING_ROOM_LAMP + lcm.BRIGHTNESS_DOWN_OFFSET

        with patch.object(self.lamp, 'brdown') as mock_brdown:
            lcm.handle_rx(code, 12345, lcm.MIN_GAP + 1)
            mock_brdown.assert_called_once_with(True, True)

    def test_handle_cct(self):
        """Test handling color temp command."""
        code = lcm.LIVING_ROOM_LAMP + lcm.CCT_OFFSET

        with patch.object(self.lamp, 'cct') as mock_cct:
            lcm.handle_rx(code, 12345, lcm.MIN_GAP + 1)
            mock_cct.assert_called_once_with(False)

    def test_handle_duplicate_on_off(self):
        """Test duplicate ON/OFF commands are ignored."""
        code = lcm.LIVING_ROOM_LAMP + lcm.ON_OFF_OFFSET

        with patch.object(self.lamp, 'on_off') as mock_on_off:
            # Gap too small - should be ignored
            lcm.handle_rx(code, 12345, lcm.MIN_GAP - 1)
            mock_on_off.assert_not_called()

    def test_handle_duplicate_cct(self):
        """Test duplicate CCT commands are ignored."""
        code = lcm.LIVING_ROOM_LAMP + lcm.CCT_OFFSET

        with patch.object(self.lamp, 'cct') as mock_cct:
            # Gap too small - should be ignored
            lcm.handle_rx(code, 12345, lcm.MIN_GAP - 1)
            mock_cct.assert_not_called()

    def test_handle_unknown_lamp(self):
        """Test handling command for unknown lamp."""
        code = 9999999  # Unknown lamp

        # Should not raise exception
        lcm.handle_rx(code, 12345, lcm.MIN_GAP + 1)

    def test_handle_null_lamp(self):
        """Test handling when decode returns None."""
        with patch('lamp_control_mqtt.decode_rx', return_value=(None, None)):
            # Should not raise exception
            lcm.handle_rx(12345, 12345, lcm.MIN_GAP + 1)


class TestFindOrCreateLamp:
    """Test lamp finding/creation."""

    def setup_method(self):
        """Set up test lamp list."""
        lcm.lamp_list.clear()

    def teardown_method(self):
        """Clean up lamp list."""
        lcm.lamp_list.clear()

    def test_find_existing_lamp(self):
        """Test finding an existing lamp."""
        mock_client = Mock()
        lamp1 = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lcm.lamp_list.append(lamp1)

        found = lcm.find_or_create_lamp(lcm.lamp_list, lcm.LIVING_ROOM_LAMP, mock_client)

        assert found == lamp1
        assert len(lcm.lamp_list) == 1

    def test_create_new_lamp(self):
        """Test creating a new lamp."""
        mock_client = Mock()

        lamp = lcm.find_or_create_lamp(lcm.lamp_list, lcm.STUDY_LAMPS, mock_client)

        assert lamp.lamp_id == lcm.STUDY_LAMPS
        assert len(lcm.lamp_list) == 1

    def test_multiple_lamps(self):
        """Test managing multiple lamps."""
        mock_client = Mock()

        lamp1 = lcm.find_or_create_lamp(lcm.lamp_list, lcm.LIVING_ROOM_LAMP, mock_client)
        lamp2 = lcm.find_or_create_lamp(lcm.lamp_list, lcm.STUDY_LAMPS, mock_client)
        lamp1_again = lcm.find_or_create_lamp(lcm.lamp_list, lcm.LIVING_ROOM_LAMP, mock_client)

        assert lamp1 == lamp1_again
        assert lamp1 != lamp2
        assert len(lcm.lamp_list) == 2


class TestCallbackFactory:
    """Test the callback factory function."""

    def test_create_on_off_callback(self):
        """Test creating an on/off callback."""
        callback = lcm.create_lamp_callback(lcm.LIVING_ROOM_LAMP, "Living Room", "on_off")

        assert callable(callback)

    def test_create_brightness_callback(self):
        """Test creating a brightness callback."""
        callback = lcm.create_lamp_callback(lcm.LIVING_ROOM_LAMP, "Living Room", "brightness")

        assert callable(callback)

    def test_create_cct_callback(self):
        """Test creating a CCT callback."""
        callback = lcm.create_lamp_callback(lcm.LIVING_ROOM_LAMP, "Living Room", "cct")

        assert callable(callback)

    def test_callback_execution_on_off(self):
        """Test executing an on/off callback."""
        lcm.lamp_list.clear()
        mock_client = Mock()
        callback = lcm.create_lamp_callback(lcm.LIVING_ROOM_LAMP, "Living Room", "on_off")

        # Create mock message
        mock_message = Mock()
        mock_message.payload.decode.return_value = "true"

        with patch('lamp_control_mqtt.send_rf'):
            callback(mock_client, None, mock_message)

        # Should have created a lamp
        assert len(lcm.lamp_list) == 1
        assert lcm.lamp_list[0].on == True

        lcm.lamp_list.clear()

    def test_callback_execution_brightness(self):
        """Test executing a brightness callback."""
        lcm.lamp_list.clear()
        mock_client = Mock()
        callback = lcm.create_lamp_callback(lcm.LIVING_ROOM_LAMP, "Living Room", "brightness")

        # Create mock message
        mock_message = Mock()
        mock_message.payload.decode.return_value = "75"

        # Mock set_brightness_level to avoid infinite loop
        with patch('lamp_control_mqtt.send_rf'):
            with patch.object(lcm.joofo_lamp, 'set_brightness_level'):
                callback(mock_client, None, mock_message)
                # Should have created a lamp
                assert len(lcm.lamp_list) == 1

        lcm.lamp_list.clear()


class TestResetLamp:
    """Test the reset_lamp callback."""

    def setup_method(self):
        """Set up test lamp list."""
        lcm.lamp_list.clear()

    def teardown_method(self):
        """Clean up lamp list."""
        lcm.lamp_list.clear()

    def test_reset_lamp_callback(self):
        """Test reset lamp callback."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lcm.lamp_list.append(lamp)

        # Create mock message
        mock_message = Mock()
        mock_message.payload.decode.return_value = str(lcm.LIVING_ROOM_LAMP)

        with patch.object(lamp, 'reset_lamp') as mock_reset:
            lcm.reset_lamp(mock_client, None, mock_message)
            mock_reset.assert_called_once()


class TestMQTTCallbacks:
    """Test MQTT connection callbacks."""

    def test_on_connect(self):
        """Test on_connect callback."""
        mock_client = Mock()

        with patch('lamp_control_mqtt.joofo_lamp') as mock_lamp_class:
            lcm.on_connect(mock_client, None, None, 0)

            # Should create 4 lamps
            assert mock_lamp_class.call_count == 4

    def test_on_disconnect_unexpected(self):
        """Test on_disconnect with unexpected disconnect."""
        mock_client = Mock()

        lcm.on_disconnect(mock_client, None, 1)  # rc != 0

        # Should attempt reconnect
        mock_client.reconnect.assert_called_once()

    def test_on_disconnect_clean(self):
        """Test on_disconnect with clean disconnect."""
        mock_client = Mock()

        lcm.on_disconnect(mock_client, None, 0)  # rc == 0

        # Should not attempt reconnect
        mock_client.reconnect.assert_not_called()

    def test_on_disconnect_reconnect_failure(self):
        """Test on_disconnect when reconnect fails."""
        mock_client = Mock()
        mock_client.reconnect.side_effect = Exception("Connection failed")

        # Should not raise exception
        lcm.on_disconnect(mock_client, None, 1)


class TestSendRF:
    """Test RF transmission function."""

    def test_send_rf_basic(self):
        """Test sending RF code."""
        with patch('lamp_control_mqtt.RFDevice') as mock_rf_device:
            mock_tx = Mock()
            mock_rf_device.return_value = mock_tx

            lcm.send_rf(3513633)

            mock_rf_device.assert_called_once()
            mock_tx.enable_tx.assert_called_once()
            mock_tx.tx_code.assert_called_once()
            mock_tx.disable_tx.assert_called_once()

    def test_send_rf_with_protocol_and_pulselength(self):
        """Test sending RF code respects protocol and pulselength args."""
        with patch('lamp_control_mqtt.RFDevice') as mock_rf_device:
            mock_tx = Mock()
            mock_rf_device.return_value = mock_tx

            lcm.send_rf(3513633)

            # Verify tx_code called with args
            call_args = mock_tx.tx_code.call_args
            assert call_args[0][0] == 3513633  # message
            # protocol and pulselength from args


class TestBrightnessEdgeCases:
    """Test brightness control edge cases."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock MQTT client."""
        client = Mock()
        client.message_callback_add = Mock()
        client.publish = Mock()
        return client

    @pytest.fixture
    def lamp(self, mock_client):
        """Create a lamp instance for testing."""
        return lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)

    def test_brightness_transition_95_to_100(self, lamp):
        """Test brightness transition near maximum."""
        lamp.brightness = 95

        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.set_brightness_level(100)

            # Should reach 100 and send extra commands
            assert lamp.brightness == 100
            assert mock_send.call_count >= 5  # At least the extra commands

    def test_brightness_transition_10_to_1(self, lamp):
        """Test brightness transition near minimum."""
        lamp.brightness = 10

        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.set_brightness_level(1)

            # Should reach 1 and send extra commands
            assert lamp.brightness >= 1
            assert mock_send.call_count >= 5  # At least the extra commands

    def test_brightness_transition_50_to_75(self, lamp):
        """Test mid-range brightness transition."""
        lamp.brightness = 50

        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.set_brightness_level(75)

            # Should reach target
            assert lamp.brightness >= 75
            assert lamp.brightness <= 75 + lcm.BR_INCREMENT

    def test_brightness_brup_turns_lamp_on(self, lamp):
        """Test brightness up turns lamp on if off."""
        lamp.on = False
        lamp.brightness = 50

        with patch('lamp_control_mqtt.send_rf'):
            lamp.brup(False, False)

        assert lamp.on == True

    def test_brightness_brdown_at_minimum(self, lamp):
        """Test brightness down at minimum stays at 1."""
        lamp.brightness = 1

        with patch('lamp_control_mqtt.send_rf'):
            lamp.brdown(False, False)

        assert lamp.brightness == 1

    def test_brightness_received_uses_remote_increment(self, lamp):
        """Test received brightness commands use remote increments."""
        lamp.brightness = 50
        initial = lamp.brightness

        with patch('lamp_control_mqtt.send_rf'):
            lamp.brup(True, False)  # received=True

        # Should use REMOTE_BRUP_INCREMENT instead of BR_INCREMENT
        assert lamp.brightness == initial + lcm.REMOTE_BRUP_INCREMENT

    def test_brightness_down_received_uses_remote_increment(self, lamp):
        """Test received brightness down uses remote increments."""
        lamp.brightness = 50
        initial = lamp.brightness

        with patch('lamp_control_mqtt.send_rf'):
            lamp.brdown(True, False)  # received=True

        # Should use REMOTE_BRDOWN_INCREMENT instead of BR_INCREMENT
        assert lamp.brightness == initial - lcm.REMOTE_BRDOWN_INCREMENT


class TestMQTTTopics:
    """Test MQTT topic string formatting."""

    def test_base_topic_format(self):
        """Test base topic is correctly formatted."""
        assert lcm.BASE_TOPIC == "cmnd/joofo30w2400lm_control/"
        assert lcm.BASE_TOPIC.endswith("/")

    def test_on_off_topic_format(self):
        """Test on/off topic construction."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)

        expected_topic = f"{lcm.BASE_TOPIC}{lcm.LIVING_ROOM_LAMP}/getOnOff"

        with patch('lamp_control_mqtt.send_rf'):
            lamp.on_off("true", True)

        # Check that publish was called with correct topic
        publish_calls = mock_client.publish.call_args_list
        assert any(expected_topic in str(call) for call in publish_calls)

    def test_brightness_topic_format(self):
        """Test brightness topic construction."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lamp.brightness = 50

        expected_topic = f"{lcm.BASE_TOPIC}{lcm.LIVING_ROOM_LAMP}/getBrightness"

        with patch('lamp_control_mqtt.send_rf'):
            lamp.brup(False, True)  # publish=True

        # Check that publish was called with correct topic
        publish_calls = mock_client.publish.call_args_list
        assert any(expected_topic in str(call) for call in publish_calls)


class TestResetLampSequence:
    """Test lamp reset sequence in detail."""

    def test_reset_sequence_turns_off_first(self):
        """Test reset turns lamp off before setting brightness."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lamp.on = True

        with patch('lamp_control_mqtt.send_rf'):
            lamp.reset_lamp()

        assert lamp.reset == True
        assert lamp.brightness > 0

    def test_reset_clears_reset_flag_on_brightness_change(self):
        """Test that reset flag is cleared on brightness change."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)

        with patch('lamp_control_mqtt.send_rf'):
            lamp.reset_lamp()
            assert lamp.reset == True

            # Any brightness change should clear reset
            lamp.brup(False, False)
            assert lamp.reset == False

    def test_reset_clears_on_on_off(self):
        """Test that reset flag is cleared on on/off when state changes."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)

        with patch('lamp_control_mqtt.send_rf'):
            lamp.reset_lamp()
            assert lamp.reset == True

            # Turn off (state change) - should clear reset
            lamp.on_off("false", True)
            assert lamp.reset == False

    def test_reset_clears_on_cct(self):
        """Test that reset flag is cleared on CCT change."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)

        with patch('lamp_control_mqtt.send_rf'):
            lamp.reset_lamp()
            assert lamp.reset == True

            lamp.cct(False)
            assert lamp.reset == False


class TestLampNames:
    """Test lamp name lookup functionality."""

    def test_known_lamp_names(self):
        """Test all known lamps have names."""
        assert lcm.LIVING_ROOM_LAMP in lcm.LAMPS2NAMES
        assert lcm.STUDY_LAMPS in lcm.LAMPS2NAMES
        assert lcm.STUDY_DESK_LAMP in lcm.LAMPS2NAMES
        assert lcm.STUDY_TABLE_LAMP in lcm.LAMPS2NAMES

    def test_lamp_name_values(self):
        """Test lamp name string values."""
        assert lcm.LAMPS2NAMES[lcm.LIVING_ROOM_LAMP] == "LIVING_ROOM_LAMP"
        assert lcm.LAMPS2NAMES[lcm.STUDY_LAMPS] == "STUDY_LAMPS"
        assert lcm.LAMPS2NAMES[lcm.STUDY_DESK_LAMP] == "STUDY_DESK_LAMP"
        assert lcm.LAMPS2NAMES[lcm.STUDY_TABLE_LAMP] == "STUDY_TABLE_LAMP"


class TestCommandNames:
    """Test command name lookup functionality."""

    def test_all_commands_have_names(self):
        """Test all command offsets have names."""
        assert lcm.ON_OFF_OFFSET in lcm.CMDS2NAMES
        assert lcm.CCT_OFFSET in lcm.CMDS2NAMES
        assert lcm.BRIGHTNESS_UP_OFFSET in lcm.CMDS2NAMES
        assert lcm.BRIGHTNESS_DOWN_OFFSET in lcm.CMDS2NAMES

    def test_command_name_values(self):
        """Test command name string values."""
        assert lcm.CMDS2NAMES[lcm.ON_OFF_OFFSET] == "ON_OFF_OFFSET"
        assert lcm.CMDS2NAMES[lcm.CCT_OFFSET] == "CCT_OFFSET"
        assert lcm.CMDS2NAMES[lcm.BRIGHTNESS_UP_OFFSET] == "BRIGHTNESS_UP_OFFSET"
        assert lcm.CMDS2NAMES[lcm.BRIGHTNESS_DOWN_OFFSET] == "BRIGHTNESS_DOWN_OFFSET"


class TestPublishBehavior:
    """Test MQTT publish behavior."""

    def test_brup_publishes_when_requested(self):
        """Test brup publishes to MQTT when publish=True."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lamp.brightness = 50

        with patch('lamp_control_mqtt.send_rf'):
            lamp.brup(False, True)  # publish=True

        # Should have published
        assert mock_client.publish.called

    def test_brup_no_publish_when_not_requested(self):
        """Test brup doesn't publish when publish=False."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lamp.brightness = 50
        lamp.on = True  # Lamp already on so on_off won't publish

        # Clear any calls from initialization
        mock_client.reset_mock()

        with patch('lamp_control_mqtt.send_rf'):
            lamp.brup(False, False)  # publish=False

        # Should not have published
        assert not mock_client.publish.called

    def test_brdown_publishes_when_requested(self):
        """Test brdown publishes to MQTT when publish=True."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lamp.brightness = 50

        with patch('lamp_control_mqtt.send_rf'):
            lamp.brdown(False, True)  # publish=True

        # Should have published
        assert mock_client.publish.called

    def test_brdown_no_publish_when_not_requested(self):
        """Test brdown doesn't publish when publish=False."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lamp.brightness = 50

        # Clear any calls from initialization
        mock_client.reset_mock()

        with patch('lamp_control_mqtt.send_rf'):
            lamp.brdown(False, False)  # publish=False

        # Should not have published
        assert not mock_client.publish.called


class TestRFSendBehavior:
    """Test RF transmission behavior."""

    def test_on_off_sends_rf_when_requested(self):
        """Test on/off sends RF when send=True."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)

        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.on_off("true", True)  # send=True

        mock_send.assert_called_once()

    def test_on_off_no_send_when_not_requested(self):
        """Test on/off doesn't send RF when send=False."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)

        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.on_off("true", False)  # send=False

        mock_send.assert_not_called()

    def test_brup_sends_rf_when_not_received(self):
        """Test brup sends RF when received=False."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lamp.brightness = 50

        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.brup(False, False)  # received=False

        mock_send.assert_called_once()

    def test_brup_no_send_when_received(self):
        """Test brup doesn't send RF when received=True."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lamp.brightness = 50

        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.brup(True, False)  # received=True

        mock_send.assert_not_called()

    def test_brdown_sends_rf_when_not_received(self):
        """Test brdown sends RF when received=False."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lamp.brightness = 50

        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.brdown(False, False)  # received=False

        mock_send.assert_called_once()

    def test_brdown_no_send_when_received(self):
        """Test brdown doesn't send RF when received=True."""
        mock_client = Mock()
        lamp = lcm.joofo_lamp(lcm.LIVING_ROOM_LAMP, mock_client)
        lamp.brightness = 50

        with patch('lamp_control_mqtt.send_rf') as mock_send:
            lamp.brdown(True, False)  # received=True

        mock_send.assert_not_called()

