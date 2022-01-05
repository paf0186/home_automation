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
parser.add_argument('code', metavar='CODE', type=int,
                    help="Decimal code to send")
parser.add_argument('-g', dest='gpio', type=int, default=17,
                    help="GPIO pin (Default: 17)")
parser.add_argument('-p', dest='pulselength', type=int, default=None,
                    help="Pulselength (Default: 350)")
parser.add_argument('-t', dest='protocol', type=int, default=None,
                    help="Protocol (Default: 1)")
parser.add_argument('-s', dest='sendtime', default=None,
                    help="Send time in seconds (Default: 0.1)")
args = parser.parse_args()

rfdevice = RFDevice(args.gpio, tx_repeat=2)
rfdevice.enable_tx()

if args.protocol:
    protocol = args.protocol
else:
    protocol = "default"
if args.pulselength:
    pulselength = args.pulselength
else:
    pulselength = "default"

if args.sendtime:
    sendtime = args.sendtime
else:
    sendtime = 0

timeout = time.time() + float(sendtime)
logging.info(str(args.code) +
             " [protocol: " + str(protocol) +
             ", pulselength: " + str(pulselength) + ", for: " + str(sendtime) + " seconds" + "]")

ON_OFF=3513634
PULSELENGTH=161
PROTO=1
i = 0
while i < 32:
    print("Sending")
    rfdevice.tx_code(args.code, args.protocol, args.pulselength)
    if float(sendtime) != 0:
        print("Sleeping...")
        sleep(0.7)
    #if sendtime == 0:
    #    break
    #elif time.time() > timeout:
    #    break
    i += 1
    sleep(0.05)
rfdevice.cleanup()
