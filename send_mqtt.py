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

def on_message(client, userdata, message):
    payload=str(message.payload.decode("utf-8"))
    logging.info("received message =" + payload)
    logging.info("Sending:" + payload +
                 " [protocol: " + str(protocol) +
                 ", pulselength: " + str(pulselength) + "]")
    rfdevice = RFDevice(args.gpio)
    rfdevice.enable_tx()
    rfdevice.tx_code(int(payload), args.protocol, args.pulselength)
    rfdevice.cleanup()

#mqtt
client =mqtt.Client("homebridge_mqtt_rfclient")
client.on_message=on_message
client.connect("localhost")
client.loop_start()
client.subscribe("cmnd/joofo30w2400lm/#", qos=0)


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
