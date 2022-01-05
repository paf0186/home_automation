# Original credit: https://github.com/milaq/rpi-rf
# Copyright (c) 2016 Suat Özgür, Micha LaQua

import argparse
import logging
import time
import paho.mqtt.client as mqtt
import math
from math import ceil
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

debug = True

# Command offsets
ON_OFF_OFFSET = 0
# Errors inserted so you can't run until you fix these
BRIGHTNESS_UP_OFFSET = 3
BRIGHTNESS_DOWN_OFFSET = 7
CCT_OFFSET = 1
BR_LEVELS=32

BASE_TOPIC = "cmnd/joofo30w2400lm_control/"
RESET_TOPIC = "Reset"
ON_OFF_TOPIC = "OnOff"
BRIGHTNESS_TOPIC = "Brightness"
CCT_TOPIC = "cct"

RF_DELAY = 0.05

LIVING_ROOM_LAMP = 3513633
STUDY_LAMPS = 13470497
STUDY_DESK_LAMP = 9513633
STUDY_TABLE_LAMP = 4513633

lamp_list = []

def reset_lamp(client, userdata, message):
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    if debug:
        print("on reset lamp " + payload)
    lamp = find_or_create_lamp(lamp_list, int(payload), client)
    lamp.reset_lamp()

def on_off_lr(client, userdata, message):
    if debug:
        print("LR on off lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, LIVING_ROOM_LAMP, client)
    lamp.send_on_off(payload, False)

def set_br_lr(client, userdata, message):
    if debug:
        print("LR set br lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, LIVING_ROOM_LAMP, client)
    lamp.set_brightness_level(int(payload))

def set_cct_lr(client, userdata, message):
    if debug:
        print("LR cct lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, LIVING_ROOM_LAMP, client)
    lamp.send_cct()

def on_off_st(client, userdata, message):
    if debug:
        print("ST on off lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_LAMPS, client)
    lamp.send_on_off(payload, False)

def set_br_st(client, userdata, message):
    if debug:
        print("ST set br lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_LAMPS, client)
    lamp.set_brightness_level(int(payload))

def set_cct_st(client, userdata, message):
    if debug:
        print("ST cct lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_LAMPS, client)
    lamp.send_cct()

def on_off_st_desk(client, userdata, message):
    if debug:
        print("ST on off desk lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_DESK_LAMP, client)
    lamp.send_on_off(payload, False)

def set_br_st_desk(client, userdata, message):
    if debug:
        print("ST set br desk lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_DESK_LAMP, client)
    lamp.set_brightness_level(int(payload))

def set_cct_st_desk(client, userdata, message):
    if debug:
        print("ST cct desk lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_DESK_LAMP, client)
    lamp.send_cct()

def on_off_st_table(client, userdata, message):
    if debug:
        print("ST on off table lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_TABLE_LAMP, client)
    lamp.send_on_off(payload, False)

def set_br_st_table(client, userdata, message):
    if debug:
        print("ST set br table lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_TABLE_LAMP, client)
    lamp.set_brightness_level(int(payload))

def set_cct_st_table(client, userdata, message):
    if debug:
        print("ST cct table lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_TABLE_LAMP, client)
    lamp.send_cct()

class joofo_lamp:
    # This is the numeric value used as the base for commands
    lamp_id = 0
    # on_off state
    on = False
    # Range from 0-BR_LEVELS; 0 is off
    brightness = 0
    # reset to on at 1 brightness & no other changes made
    reset = False
    # Can't determine this, but let's just put it in
    color_temp = 0
    # mqtt client
    client = None

    def __init__(self, lamp_id, client):
        self.lamp_id = lamp_id
        self.client = client
        topic_string = "{}{}{}".format(BASE_TOPIC,"set",RESET_TOPIC)
        print("RESET TOPIC SUB: " + topic_string)
        client.message_callback_add(topic_string, reset_lamp)
        topic_string = "{}{}/{}{}".format(BASE_TOPIC,str(lamp_id),"set",ON_OFF_TOPIC)
        print("ON OFF TOPIC SUB: " + topic_string)
        if lamp_id == LIVING_ROOM_LAMP:
            client.message_callback_add(topic_string, on_off_lr)
        elif lamp_id == STUDY_DESK_LAMP:
            client.message_callback_add(topic_string, on_off_st_desk)
        elif lamp_id == STUDY_TABLE_LAMP:
            client.message_callback_add(topic_string, on_off_st_table)
        elif lamp_id == STUDY_LAMPS:
            client.message_callback_add(topic_string, on_off_st)
        topic_string = "{}{}/{}{}".format(BASE_TOPIC,str(lamp_id),"set",BRIGHTNESS_TOPIC)
        print("SET BRIGHTNESS TOPIC SUB: " + topic_string)
        if lamp_id == LIVING_ROOM_LAMP:
            client.message_callback_add(topic_string, set_br_lr)
        elif lamp_id == STUDY_DESK_LAMP:
            client.message_callback_add(topic_string, set_br_st_desk)
        elif lamp_id == STUDY_TABLE_LAMP:
            client.message_callback_add(topic_string, set_br_st_table)
        elif lamp_id == STUDY_LAMPS:
            client.message_callback_add(topic_string, set_br_st)
        topic_string = "{}{}/{}{}".format(BASE_TOPIC,str(lamp_id),"set",CCT_TOPIC)
        print("SET CCT TOPIC SUB: " + topic_string)
        if lamp_id == LIVING_ROOM_LAMP:
            client.message_callback_add(topic_string, set_cct_lr)
        elif lamp_id == STUDY_DESK_LAMP:
            client.message_callback_add(topic_string, set_cct_st_desk)
        elif lamp_id == STUDY_TABLE_LAMP:
            client.message_callback_add(topic_string, set_cct_st_table)
        elif lamp_id == STUDY_LAMPS:
            client.message_callback_add(topic_string, set_cct_st)


    # If it's on, turn it off.  Otherwise, do nothing.
    #def turn_off(self):
    #    if self.on:
    #        self.reset = False
    #        send_rf(self.lamp_id + ON_OFF_OFFSET)
    #        self.on = False

    def send_on_off(self, setting, reset):
        if setting == "true":
            on = True
        else:
            on = False
        if self.on != on or reset:
            self.reset = False
            self.on = not self.on
            send_rf(self.lamp_id + ON_OFF_OFFSET)

    def send_brup(self):
        self.reset = False
        self.on = True
        if self.brightness < BR_LEVELS:
            self.brightness += 1
        if debug:
            print("brup " + str(self.brightness))
        send_rf(self.lamp_id + BRIGHTNESS_UP_OFFSET)

    def send_brdown(self):
        self.reset = False
        if self.brightness > 1:
            self.brightness -= 1
        if debug:
            print("brdown " + str(self.brightness))
        send_rf(self.lamp_id + BRIGHTNESS_DOWN_OFFSET)

    def send_cct(self):
        self.reset = False
        self.color_temp += 1
        # Trivial 0-1-2 cycle
        if self.color_temp == 3:
            self.color_temp = 0
        send_rf(self.lamp_id + CCT_OFFSET)

    def set_brightness_level(self, level):
        if debug:
            print("Setting brightness, requested: " + str(level))
        # Lamp has 10 brightness levels (plus off)
        # but HomeKit has 100 brightness levels
        # Reduce it to our range and round it - we only have 10 brightness
        # levels
        level = ceil(level*BR_LEVELS/100)
        # Turning brightness to zero is handled by turning the lamp off from
        # homekit
        #if level == 0:
        #    level = 1
        
        # Homekit does this for us
        #if level == 0:
        #    self.turn_off()
        #    return

        # No need to change it
        if level == self.brightness:
            return

        if debug:
            print("Rounded: " + str(level))

        # Take the brightness to the required level
        while self.brightness < level:
            self.send_brup()
            if debug:
                print("Level: " + str(level))

        while self.brightness > level:
            self.send_brdown()
            if debug:
                print("Level: " + str(level))

    def reset_lamp(self):
        # After this, lamp is known "on", brightness indeterminate
        self.send_brup()
        # After: Lamp is off
        self.send_on_off(True, True)
        # After: Lamp brightness is now 2
        self.send_brup()
        # The following method is slower.
        # Lower brightness to minimum level - Does NOT cause lamp to turn off
        # After this, lamp is known on at brightness 1
        # Could probably just use 0-BR_LEVELS, but use 0-BR_LEVELS + 1 to be sure
        #for i in range(0,BR_LEVELS + 1):
        #    print(i)
        #    self.send_brdown()

        self.reset = True
        self.on = True
        # Turning the lamp on with BRUP sets the brightness to 2
        # Rather than 1...... which is a weird choice, but hey
        # It wasn't MY choice
        #TODO: This may need updating
        self.brightness = 2 
        # Can't actually change the temp, but eh
        self.color_temperature = 0

def find_or_create_lamp(lamp_list, lamp_id, client):
    for item in lamp_list:
        if item.lamp_id == lamp_id:
            return item

    new_lamp = joofo_lamp(lamp_id, client)
    lamp_list.append(new_lamp)

    print("Created lamp: " + str(lamp_id))
    return new_lamp

def send_rf(message):
    print("Sending: " + str(message))
    rfdevice = RFDevice(args.gpio, tx_repeat=2)
    rfdevice.enable_tx()
    rfdevice.tx_code(int(message), args.protocol, args.pulselength)
    rfdevice.cleanup()
    sleep(RF_DELAY)

def on_disconnect(mqttc, userdata, rc):
    print("Disconnected.  Will try to reconnect.")

def on_connect(mqttc, obj, flags, rc):
    print("Connected.")
    topic_string = "{}#".format(BASE_TOPIC)
    print("Subscribing to:" + topic_string)
    client.subscribe(topic_string, qos=0)

    lamp_list = []
    find_or_create_lamp(lamp_list, LIVING_ROOM_LAMP, client)
    find_or_create_lamp(lamp_list, STUDY_LAMPS, client)
    find_or_create_lamp(lamp_list, STUDY_DESK_LAMP, client)
    find_or_create_lamp(lamp_list, STUDY_TABLE_LAMP, client)

client =mqtt.Client("homebridge_mqtt_rfclient")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.connect("192.168.50.222")

if args.code:
    print("Sending one message.")
    logging.info(str(args.code) +
                 " [protocol: " + str(protocol) +
                 ", pulselength: " + str(pulselength) + "]")
    rfdevice = RFDevice(args.gpio, tx_repeat=2)
    rfdevice.enable_tx()
    rfdevice.tx_code(args.code, args.protocol, args.pulselength)
    rfdevice.cleanup()
else:
    logging.info("Waiting for mqtt messages.")
    client.loop_forever()
