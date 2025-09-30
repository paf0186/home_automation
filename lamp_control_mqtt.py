# Original credit: https://github.com/milaq/rpi-rf
# Copyright (c) 2016 Suat Özgür, Micha LaQua

import argparse
import logging
import time
import paho.mqtt.client as mqtt
import math
from math import ceil
from time import sleep

from RPi import GPIO
from rpi_rf import RFDevice

logging.basicConfig(level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S',
                    format='%(asctime)-15s - [%(levelname)s] %(module)s: %(message)s',)

parser = argparse.ArgumentParser(description='Sends a decimal code via a 433/315MHz GPIO device')
parser.add_argument('-c', dest='code', type=int,
                    help="Decimal code to send")
parser.add_argument('-g', dest='gpio_tx', type=int, default=4,
                    help="GPIO transmit pin (Default: 4)")
parser.add_argument('-r', dest='gpio_rx', type=int, default=23,
                    help="GPIO receive pin (Default: 23)")
parser.add_argument('-p', dest='pulselength', type=int, default=None,
                    help="Pulselength (Default: 350)")
parser.add_argument('-t', dest='protocol', type=int, default=None,
                    help="Protocol (Default: 1)")
args = parser.parse_args()

if args.protocol:
    protocol = args.protocol
else:
    protocol = "default"
if args.pulselength:
    pulselength = args.pulselength
else:
    pulselength = "default"

# RF Command offsets - these are added to the lamp base ID to form RF codes
ON_OFF_OFFSET = 0
CCT_OFFSET = 1
BRIGHTNESS_UP_OFFSET = 3
BRIGHTNESS_DOWN_OFFSET = 7
MAX_OFFSET = BRIGHTNESS_DOWN_OFFSET
CMDS2NAMES = {
    ON_OFF_OFFSET: "ON_OFF_OFFSET",
    CCT_OFFSET: "CCT_OFFSET",
    BRIGHTNESS_UP_OFFSET: "BRIGHTNESS_UP_OFFSET",
    BRIGHTNESS_DOWN_OFFSET: "BRIGHTNESS_DOWN_OFFSET"
}

# Brightness levels
BR_LEVELS = 36  # Number of brightness steps the lamp supports
REMOTE_BRUP_LEVELS = 30  # Estimated brightness steps from physical remote (up)
REMOTE_BRDOWN_LEVELS = 34  # Estimated brightness steps from physical remote (down)
HK_BR_MAX = 100  # HomeKit brightness scale (0-100)
BR_INCREMENT = HK_BR_MAX / BR_LEVELS
REMOTE_BRUP_INCREMENT = HK_BR_MAX / REMOTE_BRUP_LEVELS
REMOTE_BRDOWN_INCREMENT = HK_BR_MAX / REMOTE_BRDOWN_LEVELS

# RF timing constants
# Minimum gap (in microseconds) between RF messages to be considered separate button presses
# Messages closer than this are treated as duplicates from the same button press
MIN_GAP = 200000  # 200ms in microseconds
RF_DELAY = 0.05  # Delay after sending RF command (seconds)
RF_POLL_INTERVAL = 0.0001  # How often to check for new RF messages (seconds)

# MQTT topics
BASE_TOPIC = "cmnd/joofo30w2400lm_control/"
RESET_TOPIC = "Reset"
ON_OFF_TOPIC = "OnOff"
BRIGHTNESS_TOPIC = "Brightness"
CCT_TOPIC = "cct"

LIVING_ROOM_LAMP = 3513633
STUDY_LAMPS = 13470497
STUDY_DESK_LAMP = 9513633
STUDY_TABLE_LAMP = 4513633
LAMPS2NAMES={LIVING_ROOM_LAMP : "LIVING_ROOM_LAMP", STUDY_LAMPS : "STUDY_LAMPS", STUDY_DESK_LAMP : "STUDY_DESK_LAMP", STUDY_TABLE_LAMP : "STUDY_TABLE_LAMP"}

lamp_list = []

def reset_lamp(client, userdata, message):
    payload=str(message.payload.decode("utf-8"))
    logging.info(f"received message = {payload}")
    logging.debug(f"on reset lamp {payload}")
    lamp = find_or_create_lamp(lamp_list, int(payload), client)
    lamp.reset_lamp()

def create_lamp_callback(lamp_id, lamp_name, command_type):
    """Factory function to create MQTT callbacks for lamp commands.

    Args:
        lamp_id: The numeric ID of the lamp
        lamp_name: Human-readable name for logging (e.g., "LR", "ST desk")
        command_type: Type of command - 'on_off', 'brightness', or 'cct'

    Returns:
        A callback function for MQTT message handling
    """
    def callback(client, userdata, message):
        payload = str(message.payload.decode("utf-8"))
        logging.info(f"received message = {payload}")
        logging.debug(f"{lamp_name} {command_type} lamp")

        lamp = find_or_create_lamp(lamp_list, lamp_id, client)

        if command_type == 'on_off':
            lamp.on_off(payload, True)
        elif command_type == 'brightness':
            lamp.set_brightness_level(int(payload))
        elif command_type == 'cct':
            lamp.cct(True)

    return callback

class joofo_lamp:
    def __init__(self, lamp_id, client):
        # This is the numeric value used as the base for commands
        self.lamp_id = lamp_id
        # mqtt client
        self.client = client
        # on_off state
        self.on = False
        # Range from 0-HK_BR_MAX; 0 is off
        self.brightness = 0
        # reset to on at BR_INCREMENT brightness & no other changes made
        self.reset = False
        # Can't determine this, but let's just put it in
        self.color_temp = 0

        # Get lamp name for logging
        lamp_name = LAMPS2NAMES.get(lamp_id, f"UNKNOWN_{lamp_id}")

        # Subscribe to reset topic (shared by all lamps)
        topic_string = f"{BASE_TOPIC}set{RESET_TOPIC}"
        logging.info(f"RESET TOPIC SUB: {topic_string}")
        client.message_callback_add(topic_string, reset_lamp)

        # Subscribe to lamp-specific topics using factory function
        commands = [
            ('on_off', ON_OFF_TOPIC),
            ('brightness', BRIGHTNESS_TOPIC),
            ('cct', CCT_TOPIC)
        ]

        for command_type, topic_suffix in commands:
            topic_string = f"{BASE_TOPIC}{lamp_id}/set{topic_suffix}"
            logging.info(f"{topic_suffix.upper()} TOPIC SUB: {topic_string}")
            callback = create_lamp_callback(lamp_id, lamp_name, command_type)
            client.message_callback_add(topic_string, callback)

    def on_off(self, setting, send):
        topic_string = f"{BASE_TOPIC}{self.lamp_id}/get{ON_OFF_TOPIC}"
        if setting == "true":
            on = True
        elif setting == "false":
            on = False
        else:
            on = None

        if self.on != on:
            self.reset = False
            self.on = not self.on
            if self.on:
                status = "true"
            else:
                status = "false"
            logging.debug(f"Status: {status}")
            logging.debug(f"Publishing to: {topic_string}")
            self.client.publish(topic_string, payload=status, qos=0, retain=False)
            if send:
                send_rf(self.lamp_id + ON_OFF_OFFSET)

    def brup(self, received, publish):
        topic_string = f"{BASE_TOPIC}{self.lamp_id}/get{BRIGHTNESS_TOPIC}"
        self.reset = False
        self.on_off("true", False)
        if self.brightness < HK_BR_MAX:
            if not received:
                self.brightness += BR_INCREMENT
            else:
                self.brightness += REMOTE_BRUP_INCREMENT
        if self.brightness > HK_BR_MAX:
            self.brightness = HK_BR_MAX
        logging.debug(f"brup {self.brightness}")
        status=math.ceil(self.brightness)
        logging.debug(f"Brightness status: {status}")
        if publish:
            logging.debug(f"PUBLISHING (brup) {topic_string}")
            self.client.publish(topic_string, payload=status, qos=0, retain=False)
        if not received:
            send_rf(self.lamp_id + BRIGHTNESS_UP_OFFSET)

    def brdown(self, received, publish):
        topic_string = f"{BASE_TOPIC}{self.lamp_id}/get{BRIGHTNESS_TOPIC}"
        self.reset = False
        if self.brightness > 1:
            if not received:
                self.brightness -= BR_INCREMENT
            else:
                self.brightness -= REMOTE_BRDOWN_INCREMENT
        if self.brightness <= 0:
            self.brightness = 1
        logging.debug(f"brdown {self.brightness}")
        status=math.ceil(self.brightness)
        logging.debug(f"Brightness status: {status}")
        if publish:
            logging.debug(f"PUBLISHING (brdown) {topic_string}")
            self.client.publish(topic_string, payload=status, qos=0, retain=False)
        if not received:
            send_rf(self.lamp_id + BRIGHTNESS_DOWN_OFFSET)

    def cct(self, send):
        # Not sure what to do here - these color temps don't really match
        # And I can't reset them...  Hm.
        self.reset = False
        self.color_temp += 1
        # Trivial 0-1-2 cycle
        if self.color_temp == 3:
            self.color_temp = 0

    def set_brightness_level(self, level):
        logging.debug(f"Setting brightness, requested: {level}")
        # Lamp has BR_LEVELS brightness levels (plus off)
        # but HomeKit has 100 brightness levels
        # We store HomeKit brightness internally & convert in tx/rx with lamp

        # Turning brightness to zero is handled by turning the lamp off from
        # homekit
        if level == 0:
            level = 1

        # No need to change it
        if level == math.ceil(self.brightness):
            return

        logging.debug(f"Rounded: {level}")

        # Take the brightness to the required level
        if self.brightness < level:
            while self.brightness < level:
                # Only publish the last time
                if self.brightness + BR_INCREMENT >= level:
                    logging.debug(f"PUBLISHING, level: {level} br: {self.brightness}")
                    self.brup(False, True)
                else:
                    self.brup(False, False)
                logging.debug(f"Level: {level}")
        elif self.brightness > level:
            while self.brightness > level:
                if self.brightness - BR_INCREMENT <= level:
                    logging.debug(f"PUBLISHING, level: {level} br: {self.brightness}")
                    self.brdown(False, True)
                else:
                    self.brdown(False, False)
                logging.debug(f"Level: {level}")

        # Do a few extras at the boundary to account for inconsistencies in the
        # lamp receiver
        if level == 100:
            self.brup(False, False)
            self.brup(False, False)
            self.brup(False, False)
            self.brup(False, False)
        if level <= BR_INCREMENT:
            self.brdown(False, False)
            self.brdown(False, False)
            self.brdown(False, False)
            self.brdown(False, False)

    def reset_lamp(self):
        # After this, lamp is known "on", brightness indeterminate
        self.brup(False, False)
        # After: Lamp is off
        self.on_off("false", True)
        self.brightness = 1
        # After: Lamp brightness is now 1 + BR_INCREMENT
        self.brup(False, True)

        self.reset = True
        # Turning the lamp on with BRUP sets the brightness to 2
        # Rather than 1...... which is a weird choice, but hey
        # It wasn't MY choice

        # Can't actually change the temp, but eh
        self.color_temperature = 0

def find_or_create_lamp(lamp_list, lamp_id, client):
    for item in lamp_list:
        if item.lamp_id == lamp_id:
            return item

    new_lamp = joofo_lamp(lamp_id, client)
    lamp_list.append(new_lamp)

    logging.info(f"Created lamp: {LAMPS2NAMES[lamp_id]} ({lamp_id})")
    return new_lamp

def handle_rx(code, timestamp, gap):
    lamp, command = decode_rx(code, timestamp)

    if lamp is None or command is None:
        return

    # Skip duplicate commands from same button press
    if command in (ON_OFF_OFFSET, CCT_OFFSET) and gap < MIN_GAP:
        logging.debug("Skipping duplicate command")
        return

    if command == ON_OFF_OFFSET:
        lamp.on_off(None, False)
    elif command == CCT_OFFSET:
        lamp.cct(False)
    elif command == BRIGHTNESS_UP_OFFSET:
        lamp.brup(True, True)
    elif command == BRIGHTNESS_DOWN_OFFSET:
        lamp.brdown(True, True)

# Decode a message off the wire
def decode_rx(code, timestamp):
    target_lamp=None
    for lamp in lamp_list:
        if abs(int(code) - int(lamp.lamp_id)) <= MAX_OFFSET:
            target_lamp=lamp

    if target_lamp is None:
        logging.warning(f"Lamp not found!  Code: {code}")
        return (None,None)
    command = int(code) - int(target_lamp.lamp_id)
    if command not in CMDS2NAMES.keys():
        logging.warning(f"Command not found!  Code: {code}")
        return (None, None)
    logging.info(f"Code: {code} TS: {timestamp}")
    logging.info(f"Lamp: {LAMPS2NAMES[target_lamp.lamp_id]}")
    logging.info(f"Command: {CMDS2NAMES[command]}")
    return (target_lamp,command)

def send_rf(message):
    logging.debug(f"Sending: {message}")
    txdevice = RFDevice(args.gpio_tx, tx_repeat=2)
    txdevice.enable_tx()
    txdevice.tx_code(int(message), args.protocol, args.pulselength)
    txdevice.disable_tx()
    GPIO.cleanup(args.gpio_tx)
    sleep(RF_DELAY)

def on_disconnect(mqttc, userdata, rc):
    if rc != 0:
        logging.warning(f"Unexpected disconnect (rc={rc}). Reconnecting...")
        try:
            mqttc.reconnect()
        except Exception as e:
            logging.error(f"Reconnection failed: {e}")
    else:
        logging.info("Clean disconnect.")

def on_connect(mqttc, obj, flags, rc):
    logging.info("Connected.")
    topic_string = f"{BASE_TOPIC}#"
    logging.info(f"Subscribing to: {topic_string}")
    mqttc.subscribe(topic_string, qos=0)

    find_or_create_lamp(lamp_list, LIVING_ROOM_LAMP, mqttc)
    find_or_create_lamp(lamp_list, STUDY_LAMPS, mqttc)
    find_or_create_lamp(lamp_list, STUDY_DESK_LAMP, mqttc)
    find_or_create_lamp(lamp_list, STUDY_TABLE_LAMP, mqttc)

def main():
    """Main entry point for the application."""
    client = mqtt.Client("homebridge_mqtt_rfclient")
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect("localhost")

    if args.code:
        logging.info("Sending one message.")
        logging.info(f"{args.code} [protocol: {protocol}, pulselength: {pulselength}]")
        txdevice = RFDevice(args.gpio_tx, tx_repeat=2)
        txdevice.enable_tx()
        txdevice.tx_code(args.code, args.protocol, args.pulselength)
        txdevice.cleanup()
        sleep(RF_DELAY)
    else:
        logging.info("Waiting for mqtt messages.")
        rxdevice = RFDevice(args.gpio_rx)
        rxdevice.enable_rx()
        timestamp = None
        client.loop_start()
        while True:
            if rxdevice.rx_code_timestamp != timestamp:
                # Don't ignore the first command
                gap = MIN_GAP + 1
                if timestamp is not None:
                    gap = rxdevice.rx_code_timestamp - timestamp
                logging.debug(f"Gap: {gap}")
                timestamp = rxdevice.rx_code_timestamp
                code = rxdevice.rx_code
                handle_rx(code, timestamp, gap)
            # Poll for new RF messages
            sleep(RF_POLL_INTERVAL)


if __name__ == "__main__":
    main()
