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
CCT_OFFSET = 1
BRIGHTNESS_UP_OFFSET = 3
BRIGHTNESS_DOWN_OFFSET = 7
MAX_OFFSET=BRIGHTNESS_DOWN_OFFSET
CMDS2NAMES={ON_OFF_OFFSET : "ON_OFF_OFFSET", CCT_OFFSET : "CCT_OFFSET", BRIGHTNESS_UP_OFFSET : "BRIGHTNESS_UP_OFFSET", BRIGHTNESS_DOWN_OFFSET : "BRIGHTNESS_DOWN_OFFSET"}
BR_LEVELS=36
REMOTE_BRUP_LEVELS=30
REMOTE_BRDOWN_LEVELS=34
HK_BR_MAX=100
BR_INCREMENT=HK_BR_MAX/BR_LEVELS
REMOTE_BRUP_INCREMENT=HK_BR_MAX/REMOTE_BRUP_LEVELS
REMOTE_BRDOWN_INCREMENT=HK_BR_MAX/REMOTE_BRDOWN_LEVELS

# If a gap between two messages is less than this, they're from the same button
# press.  For on/off and change color temp (cct), they should be disregarded.
# For BR_UP/BR_DOWN, I'm not sure yet - I think not.  Or perhaps the rules are
# different...  There may still be a gap factor.
MIN_GAP=200000

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
LAMPS2NAMES={LIVING_ROOM_LAMP : "LIVING_ROOM_LAMP", STUDY_LAMPS : "STUDY_LAMPS", STUDY_DESK_LAMP : "STUDY_DESK_LAMP", STUDY_TABLE_LAMP : "STUDY_TABLE_LAMP"}

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
    lamp.on_off(payload, True)

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
    lamp.cct(True)

def on_off_st(client, userdata, message):
    if debug:
        print("ST on off lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_LAMPS, client)
    lamp.on_off(payload, True)

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
    lamp.cct(True)

def on_off_st_desk(client, userdata, message):
    if debug:
        print("ST on off desk lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_DESK_LAMP, client)
    lamp.on_off(payload, True)

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
    lamp.cct(True)

def on_off_st_table(client, userdata, message):
    if debug:
        print("ST on off table lamp")
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    lamp = find_or_create_lamp(lamp_list, STUDY_TABLE_LAMP, client)
    lamp.on_off(payload, True)

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
    lamp.cct(True)

class joofo_lamp:
    # This is the numeric value used as the base for commands
    lamp_id = 0
    # on_off state
    on = False
    # Range from 0-HK_BR_MAX; 0 is off
    brightness = 0
    # reset to on at BR_INCREMENT brightness & no other changes made
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

    def brup(self, received, publish):
        topic_string = "{}{}/{}{}".format(BASE_TOPIC,str(self.lamp_id),"get",BRIGHTNESS_TOPIC)
        self.reset = False
        self.on_off("true", False)
        if self.brightness < HK_BR_MAX:
            if not received:
                self.brightness += BR_INCREMENT
            else:
                #TODO: Add constant here
                # I guess this was an estimate of how far the received ones
                # from the remote move the lamp?  Oh dear...
                self.brightness += REMOTE_BRUP_INCREMENT
                #self.brightness += HK_BR_MAX/25
        if self.brightness > HK_BR_MAX:
            self.brightness = HK_BR_MAX
        if debug:
            print("brup " + str(self.brightness))
        status=math.ceil(self.brightness)
        print(status)
        if publish:
            print("PUBLISHING (brup) " + topic_string)
            client.publish(topic_string, payload=status, qos=0, retain=False)
        if not received:
            send_rf(self.lamp_id + BRIGHTNESS_UP_OFFSET)

    def brdown(self, received, publish):
        topic_string = "{}{}/{}{}".format(BASE_TOPIC,str(self.lamp_id),"get",BRIGHTNESS_TOPIC)
        self.reset = False
        if self.brightness > 1:
            if not received:
                self.brightness -= BR_INCREMENT
            else:
                self.brightness -= REMOTE_BRDOWN_INCREMENT
                #self.brightness -= HK_BR_MAX/25
        if self.brightness <= 0:
            self.brightness = 1
        if debug:
            print("brdown " + str(self.brightness))
        status=math.ceil(self.brightness)
        print(status)
        if publish:
            print("PUBLISHING (brdown) " + topic_string)
            client.publish(topic_string, payload=status, qos=0, retain=False)
        if not received:
            send_rf(self.lamp_id + BRIGHTNESS_DOWN_OFFSET)

    def cct(self, send):
        # Not sure what to do here - these color temps don't really match
        # And I can't reset them...  Hm.
        #topic_string = "{}{}/{}{}".format(BASE_TOPIC,str(self.lamp_id),"get",CCT_TOPIC)
        self.reset = False
        self.color_temp += 1
        # Trivial 0-1-2 cycle
        if self.color_temp == 3:
            self.color_temp = 0
        #if send:
        #    send_rf(self.lamp_id + CCT_OFFSET)

    def set_brightness_level(self, level):
        if debug:
            print("Setting brightness, requested: " + str(level))
        # Lamp has BR_LEVELS brightness levels (plus off)
        # but HomeKit has 100 brightness levels
        # We store HomeKit brightness internally & convert in tx/rx with lamp

        # Turning brightness to zero is handled by turning the lamp off from
        # homekit
        if level == 0:
            level = 1
        
        # Homekit does this for us
        #if level == 0:
        #    self.turn_off()
        #    return

        # No need to change it
        if level == math.ceil(self.brightness):
            return

        if debug:
            print("Rounded: " + str(level))

        # Take the brightness to the required level
        if self.brightness < level:
            while self.brightness < level:
                # Only publish the last time
                if self.brightness + BR_INCREMENT >= level:
                    print("PUBLISHING, level :" + str(level) + "br: " + str(self.brightness))
                    self.brup(False, True)
                else:
                    self.brup(False, False)
                if debug:
                    print("Level: " + str(level))
        elif self.brightness > level:
            while self.brightness > level:
                if self.brightness - BR_INCREMENT <= level:
                    print("PUBLISHING, level :" + str(level) + "br: " + str(self.brightness))
                    self.brdown(False, True)
                else:
                    self.brdown(False, False)
                if debug:
                    print("Level: " + str(level))

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

        # The following method is slower.
        # Lower brightness to minimum level - Does NOT cause lamp to turn off
        # After this, lamp is known on at brightness 1
        # Could probably just use 0-BR_LEVELS, but use 0-BR_LEVELS + 1 to be sure
        #for i in range(0,BR_LEVELS + 1):
        #    print(i)
        #    self.send_brdown(True)

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

    print("Created lamp: " + LAMPS2NAMES[lamp_id] + " (" + str(lamp_id) + ")")
    return new_lamp

def handle_rx(code, timestamp, gap):
    lamp, command = decode_rx(code, timestamp)
    if command == ON_OFF_OFFSET or command == CCT_OFFSET:
        # This command is from a single button press
        if gap < MIN_GAP:
            print("Skipping command")
            return

    if command == ON_OFF_OFFSET:
        lamp.on_off(None, False)

    if command == CCT_OFFSET:
        lamp.cct(False)

    if command == BRIGHTNESS_UP_OFFSET:
        lamp.brup(True, True)

    if command == BRIGHTNESS_DOWN_OFFSET:
        lamp.brdown(True, True)

    return

# Decode a message off the wire
def decode_rx(code, timestamp):
    target_lamp=None
    for lamp in lamp_list:
        if abs(int(code) - int(lamp.lamp_id)) <= MAX_OFFSET:
            target_lamp=lamp

    if target_lamp is None:
        print("Lamp not found!  Code: " + str(code))
        return (None,None)
    command = int(code) - int(target_lamp.lamp_id)
    if command not in CMDS2NAMES.keys():
        print("Command not found!  Code: " + str(code))
        return (None, None)
    print("Code: " + str(code) + " TS: " + str(timestamp))
    print(LAMPS2NAMES[target_lamp.lamp_id])
    print(CMDS2NAMES[command])
    return (target_lamp,command)

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

    find_or_create_lamp(lamp_list, LIVING_ROOM_LAMP, client)
    find_or_create_lamp(lamp_list, STUDY_LAMPS, client)
    find_or_create_lamp(lamp_list, STUDY_DESK_LAMP, client)
    find_or_create_lamp(lamp_list, STUDY_TABLE_LAMP, client)

client =mqtt.Client("homebridge_mqtt_rfclient")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.connect("192.168.50.221")

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
    timestamp = None
    # We check this every time this thread blocks, hence the sleep in the loop
    # below.
    #client.loop_forever()
    client.loop_start()
    # So this loop receives the message
    # and so I have to figure how to match this to the lamp state
    # but I also have to figure out how to make the lamp queryable
    while True:
        if rxdevice.rx_code_timestamp != timestamp:
            # Don't ignore the first command
            gap = MIN_GAP + 1
            if timestamp is not None:
                gap = rxdevice.rx_code_timestamp - timestamp
            print("Gap: " + str(gap))
            timestamp = rxdevice.rx_code_timestamp
            #logging.info(str(rxdevice.rx_code) +
            #             " [pulselength " + str(rxdevice.rx_pulselength) +
            #             ", protocol " + str(rxdevice.rx_proto) + "] " + str(timestamp))
            code = rxdevice.rx_code
            handle_rx(code, timestamp, gap)
            #print(str(code) +
            #             " [pulselength " + str(rxdevice.rx_pulselength) +
            #             ", protocol " + str(rxdevice.rx_proto) + "] " + str(timestamp))
        # Basically we check for new RF messages this often.
        # This was determined experimentally - checking more often than this
        # didn't result in changes to message timestamps
        sleep(0.0001)
