# Home Automation - MQTT/RF Bridge for Smart Lamps

[![Tests](https://github.com/paf0186/home_automation/actions/workflows/test.yml/badge.svg)](https://github.com/paf0186/home_automation/actions/workflows/test.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Code Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen.svg)](test_lamp_control.py)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Raspberry Pi-based home automation system that bridges MQTT (Homebridge) with 433/315MHz RF-controlled smart lamps. This allows controlling RF lamps through Apple HomeKit while maintaining compatibility with physical RF remotes.

## Features

- **Bidirectional Control**: Control lamps via HomeKit or physical RF remotes
- **State Synchronization**: RF remote commands update HomeKit state automatically
- **Multiple Lamps**: Support for multiple independent lamps
- **Brightness Control**: 36-level lamp brightness mapped to HomeKit's 100-level scale
- **Color Temperature**: Cycle through 3 color temperature settings
- **Duplicate Filtering**: Intelligent filtering of duplicate RF commands
- **MQTT Integration**: Full integration with Homebridge via MQTT
- **Auto-Reconnect**: Automatic MQTT reconnection on disconnect

## Hardware Requirements

- **Raspberry Pi** (any model with GPIO)
- **433MHz/315MHz RF Transmitter Module** (connected to GPIO pin 4 by default)
- **433MHz/315MHz RF Receiver Module** (connected to GPIO pin 23 by default)
- **Compatible RF Lamps** (tested with Joofo 30W 2400lm lamps)

## Software Requirements

- Python 3.6+
- Homebridge with MQTT plugin
- MQTT broker (e.g., Mosquitto)

## Installation

### 1. Install System Dependencies

```bash
# Install MQTT broker
sudo apt-get update
sudo apt-get install mosquitto mosquitto-clients

# Install Python dependencies
pip3 install -r requirements.txt
```

### 2. Configure Lamp IDs

Edit `lamp_control_mqtt.py` to set your lamp RF codes:

```python
LIVING_ROOM_LAMP = 3513633
STUDY_LAMPS = 13470497
STUDY_DESK_LAMP = 9513633
STUDY_TABLE_LAMP = 4513633
```

To find your lamp's RF code, run the receiver:

```bash
python3 lamp_control_mqtt.py -r 23
# Press a button on your lamp's remote and note the code
```

### 3. Configure Homebridge

Copy the MQTT accessory configuration from `config.json` to your Homebridge config.

### 4. Run as a Service

```bash
# Copy the service file
sudo cp mqtt_lamp_control_rf.service /etc/systemd/system/

# Enable and start the service
sudo systemctl enable mqtt_lamp_control_rf
sudo systemctl start mqtt_lamp_control_rf

# Check status
sudo systemctl status mqtt_lamp_control_rf
```

## Usage

### Manual Control

```bash
# Run in foreground (for testing)
python3 lamp_control_mqtt.py

# Send a single RF command
python3 lamp_control_mqtt.py -c 3513633

# Specify custom GPIO pins
python3 lamp_control_mqtt.py -g 17 -r 27
```

### MQTT Topics

The system subscribes to these MQTT topics:

- `cmnd/joofo30w2400lm_control/{LAMP_ID}/setOnOff` - Turn lamp on/off ("true"/"false")
- `cmnd/joofo30w2400lm_control/{LAMP_ID}/setBrightness` - Set brightness (0-100)
- `cmnd/joofo30w2400lm_control/{LAMP_ID}/setcct` - Cycle color temperature
- `cmnd/joofo30w2400lm_control/setReset` - Reset lamp to default state

And publishes status to:

- `cmnd/joofo30w2400lm_control/{LAMP_ID}/getOnOff` - Current on/off state
- `cmnd/joofo30w2400lm_control/{LAMP_ID}/getBrightness` - Current brightness

## Development

### Running Tests

```bash
# Install test dependencies
pip3 install -r requirements-test.txt

# Run all tests
pytest test_lamp_control.py -v

# Run with coverage
pytest test_lamp_control.py --cov=lamp_control_mqtt --cov-report=term-missing
```

**Test Coverage: 96%** with **79 passing tests**

The test suite includes:
- Unit tests for all lamp control functions
- RF transmission and reception tests
- MQTT integration tests
- Edge case and error handling tests
- Main entry point tests (single command & daemon mode)

### Code Structure

- `lamp_control_mqtt.py` - Main application (275 statements)
- `test_lamp_control.py` - Comprehensive test suite (79 tests)
- `.github/workflows/test.yml` - CI/CD pipeline (Python 3.8-3.11)
- `config.json` - Homebridge MQTT configuration
- `mqtt_lamp_control_rf.service` - Systemd service file
- `rf_sniffer.py` - RF diagnostic tool for discovering lamp codes

### Key Components

- **`joofo_lamp` class** - Manages individual lamp state and commands
- **`create_lamp_callback()`** - Factory function for MQTT callbacks
- **`decode_rx()`** - Decodes RF codes to lamp ID and command
- **`handle_rx()`** - Processes received RF commands
- **`send_rf()`** - Transmits RF commands

## Troubleshooting

### Lamp doesn't respond to HomeKit commands

1. Check MQTT broker is running: `systemctl status mosquitto`
2. Check service is running: `systemctl status mqtt_lamp_control_rf`
3. Check logs: `journalctl -u mqtt_lamp_control_rf -f`
4. Verify GPIO connections (TX on pin 4, RX on pin 23)

### RF remote commands not updating HomeKit

1. Verify RF receiver is connected to correct GPIO pin
2. Check that lamp RF codes are correctly configured
3. Test receiver: `python3 lamp_control_mqtt.py` and press remote buttons

### MQTT connection issues

1. Verify MQTT broker address in code (default: localhost)
2. Check MQTT broker logs: `journalctl -u mosquitto -f`
3. Test MQTT manually: `mosquitto_pub -t test -m "hello"`

## RF Command Protocol

Lamps use a simple offset-based protocol:

- **Base Code**: Each lamp has a unique base RF code
- **Command Offsets**:
  - `+0` - On/Off toggle
  - `+1` - Color temperature cycle
  - `+3` - Brightness up
  - `+7` - Brightness down

Example: For lamp with base code `3513633`:
- On/Off: `3513633`
- CCT: `3513634`
- Brightness Up: `3513636`
- Brightness Down: `3513640`

## License

See LICENSE file for details.

## Credits

RF communication based on [rpi-rf](https://github.com/milaq/rpi-rf) by Suat Özgür and Micha LaQua.
