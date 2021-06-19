# Original credit: https://github.com/milaq/rpi-rf
# Copyright (c) 2016 Suat Özgür, Micha LaQua

import argparse
import logging
import time
import paho.mqtt.client as mqtt
from time import sleep

from rpi_rf import RFDevice

logging.basicConfig(level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S',
                    format='%(asctime)-15s - [%(levelname)s] %(module)s: %(message)s',)

parser = argparse.ArgumentParser(description='Sends a decimal code via a 433/315MHz GPIO device')
parser.add_argument('-c', dest='code', type=int,
                    help="Decimal code to send")
parser.add_argument('-g', dest='gpio', type=int, default=17,
                    help="GPIO pin (Default: 17)")
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

CHANNEL_BASE = "cmnd/joofo30w2400lm_control/"

class joofo_lamp:
    # This is the numeric value used as the base for commands
    lamp_id = 0
    # on_off state
    on = False
    # Range from 0-10; 0 is off
    brightness = 0
    # reset to on at 1 brightness & no other changes made
    reset = False
    # Can't determine this, but let's just put it in
    color_temp = 0

    def __init__(self, lamp_id, client):
        self.lamp_id = lamp_id
        # TODO:
        # Do channels/listening/etc

    # If it's on, turn it off.  Otherwise, do nothing.
    def turn_off(self):
        if self.on:
            self.reset = False
            send_rf(self.lamp_id + ON_OFF_OFFSET)
            self.on = False

    def send_onoff(self):
        self.reset = False
        self.on = not self.on
        send_rf(self.lamp_id + ON_OFF_OFFSET)

    def send_brup(self):
        self.reset = False
        if self.brightness < 10:
            self.brightness += 1
        send_rf(self.lamp_id + BRIGHTNESS_UP_OFFSET)

    def send_brdown(self):
        self.reset = False
        if self.brightness > 1:
            self.brightness -= 1
        send_rf(self.lamp_id + BRIGHTNESS_DOWN_OFFSET)

    def send_CCT(self):
        self.reset = False
        self.color_temp += 1
        # Trivial 0-1-2 cycle
        if self.color_temp == 3:
            self.color_temp = 0
        send_rf(self.lamp_id + CCT_OFFSET)

    def set_brightness_level(self, level):
        # Using brightness change to turn the lamp on
        # means it starts at zero
        # ... probably?  That's probably how HomeKit works?
        # Maybe it sends an on signal first???
        # TODO
        #if not self.on:
        #    self.brightness = 0

        # Lamp has 10 brightness levels (plus off)
        # but HomeKit has 100 brightness levels
        if level > 0 and level < 10:
            level = 10
        level = round(level/10)*10
        
        if level == 0:
            self.turn_off()
            return

        # No need to change it
        if level == self.brightness:
            return

        # Take the brightness to the required level
        while level < self.brightness:
            self.send_brup()

        while level > self.brightness:
            self.send_brdown()

    def reset_lamp(self):
        # After this, lamp is known "on"
        self.send_brup(self)
        # After this, lamp is known "off"
        self.send_onoff(self)
        # After this, lamp is known on at brightness 1
        self.send_brup(self)

        self.reset = True
        self.on = True
        self.brightness = 1 
        # Can't actually change the temp, but eh
        self.color_temperature = 0

# Command offsets
ON_OFF_OFFSET = 0
# Errors inserted so you can't run until you fix these
BRIGHTNESS_UP_OFFSET = 3
BRIGHTNESS_DOWN_OFFSET = 7
CCT_OFFSET = 1

BASE_TOPIC = "cmnd/joofo30w2400lm_control/"
ADVERTISE_TOPIC = "Advertise"
RESET_TOPIC = "Reset"
ON_OFF_TOPIC = "OnOff"
BRIGHTNESS_TOPIC = "Brightness"
CCT_TOPIC = "CCT"

lamp_list = []

def find_or_create_lamp(lamp_list, lamp_id):
    for item in lamp_list:
        if item.lamp_id == lamp_id:
            return item

    new_lamp = joofo_lamp(lamp_id)
    lamp_list.append(new_lamp)

    return new_lamp

def send_rf(message):
    logging.info("Sending:" + payload +
                 " [protocol: " + str(protocol) +
                 ", pulselength: " + str(pulselength) + "]")
    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    rfdevice.tx_code(int(message), args.protocol, args.pulselength)
    rfdevice.cleanup()

# On startup, we sign up to the advertise channel
# And we get the message off there
# We also sign up to the "Reset" channel
# And process messages from there the same way
# That is to say, receiving a message causes us to create
# a lamp if one does not exist

# So that is forever the handling of the advertise channel
# The reset button has the additional feature of creating a
# lamp, and then attempting a reset

def on_message(client, userdata, message):
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    logging.info("Sending:" + payload +
                 " [protocol: " + str(protocol) +
                 ", pulselength: " + str(pulselength) + "]")
    send_rf(payload)

#mqtt
client =mqtt.Client("homebridge_mqtt_rfclient")
client.on_message=on_message
client.connect("localhost")
client.loop_start()
client.subscribe("{}#".format(BASE_TOPIC), qos=0)

LIVING_ROOM_LAMP = 3513633
STUDY_LAMP = 13470497
find_or_create_lamp(lamp_list, LIVING_ROOM_LAMP - 15, client)
find_or_create_lamp(lamp_list, STUDY_LAMP - 15, client)


if args.code:
    print("Sending one message.")
    logging.info(str(args.code) +
                 " [protocol: " + str(protocol) +
                 ", pulselength: " + str(pulselength) + "]")
    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    rfdevice.tx_code(args.code, args.protocol, args.pulselength)
    rfdevice.cleanup()
else:
    logging.info("Waiting for mqtt messages.")
    while True:
        sleep(600)
