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

