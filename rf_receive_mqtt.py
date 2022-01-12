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

debug = True

# Command offsets
ON_OFF_OFFSET = 0
MAX_OFFSET = 0
CMDS2NAMES={ON_OFF_OFFSET : "ON_OFF_OFFSET"}

# If a gap between two messages is less than this, they're from the same button
# press.
MIN_GAP=200000

BASE_TOPIC = "cmnd/sonoff_remote/"
ON_OFF_TOPIC = "OnOff"

RF_DELAY = 0.05

BUTTON1=14119976
BUTTON2=14119980
BUTTON3=14119972
BUTTON4=14119977
BUTTON5=14119970
BUTTON6=14119973
BUTTON7=14119969
BUTTON8=14119971
BUTTONS2NAMES={BUTTON1 : "BUTTON1", BUTTON2 : "BUTTON2", BUTTON3 : "BUTTON3", BUTTON4 : "BUTTON4", BUTTON5 : "BUTTON5", BUTTON6 : "BUTTON6", BUTTON7 : "BUTTON7", BUTTON8 : "BUTTON8"}

button_list = []
for button in BUTTONS2NAMES.keys():
    button_list.append(button)

class joofo_lamp:
    # This is the numeric value used as the base for commands
    lamp_id = 0
    # on_off state
    on = False
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


    def on_off(self, setting, send):
        topic_string = "{}{}/{}{}".format(BASE_TOPIC,str(self.lamp_id),"get",ON_OFF_TOPIC)
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
            print("Status: " + status)
            print(topic_string)
            client.publish(topic_string, payload=status, qos=0, retain=False)
            if send:
                send_rf(self.lamp_id + ON_OFF_OFFSET)

def handle_rx(code, timestamp, gap):
    button, command = decode_rx(code, timestamp)
    if command == ON_OFF_OFFSET:
        # This command is from a single button press
        if gap < MIN_GAP:
            print("Skipping command")
            return

#TODO: This is where things get changed, I think!
#We only need one send function...
#    if command == ON_OFF_OFFSET:
#        lamp.on_off(None, False)

    return

# Decode a message off the wire
def decode_rx(code, timestamp):
    target_button=None
    for button in button_list:
        if abs(int(code) - int(button)) <= MAX_OFFSET:
            target_button=button

    if target_button is None:
        print("Switch not found!  Code: " + str(code))
        return (None,None)
    command = int(code) - int(target_button)
    if command not in CMDS2NAMES.keys():
        print("Command not found!  Code: " + str(code))
        return (None, None)
    print("Code: " + str(code) + " TS: " + str(timestamp))
    print(BUTTONS2NAMES[target_button])
    print(CMDS2NAMES[command])
    return (target_button,command)

def send_rf(message):
    print("Sending: " + str(message))
    txdevice = RFDevice(args.gpio_tx, tx_repeat=2)
    txdevice.enable_tx()
    txdevice.tx_code(int(message), args.protocol, args.pulselength)
    txdevice.disable_tx()
    GPIO.cleanup(args.gpio_tx)
    sleep(RF_DELAY)

def on_disconnect(mqttc, userdata, rc):
    print("Disconnected.  Will try to reconnect.")

def on_connect(mqttc, obj, flags, rc):
    print("Connected.")
    topic_string = "{}#".format(BASE_TOPIC)
    print("Subscribing to:" + topic_string)
    client.subscribe(topic_string, qos=0)

client =mqtt.Client("homebridge_mqtt_rf_remote_client")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.connect("192.168.50.222")

if args.code:
    print("Sending one message.")
    logging.info(str(args.code) +
                 " [protocol: " + str(protocol) +
                 ", pulselength: " + str(pulselength) + "]")
    txdevice = RFDevice(args.gpio_tx, tx_repeat=2)
    txdevice.enable_tx()
    txdevice.tx_code(args.code, args.protocol, args.pulselength)
    txdevice.cleanup()
    sleep(RF_DELAY)
else:
    logging.info("Waiting for mqtt messages.")
    #client.loop_forever()
    rxdevice = RFDevice(args.gpio_rx)
    rxdevice.enable_rx()
    # We check this every time this thread blocks, hence the sleep in the loop
    # below.
    #client.loop_forever()
    client.loop_start()
    timestamp = None
    # This loop handles receiving rf messages, but also sleeps to check mqtt
    # queue
    while True:
        if rxdevice.rx_code_timestamp != timestamp:
            # Don't ignore the first command
            gap = MIN_GAP + 1
            if timestamp is not None:
                gap = rxdevice.rx_code_timestamp - timestamp
            print("Gap: " + str(gap))
            timestamp = rxdevice.rx_code_timestamp
            code = rxdevice.rx_code
            handle_rx(code, timestamp, gap)
            #print(str(code) +
            #             " [pulselength " + str(rxdevice.rx_pulselength) +
            #             ", protocol " + str(rxdevice.rx_proto) + "] " + str(timestamp))
        # Basically we check for new RF messages this often.
        # This was determined experimentally - checking more often than this
        # didn't result in changes to message timestamps
        sleep(0.0001)
