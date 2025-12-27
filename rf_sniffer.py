#!/usr/bin/env python3
"""
RF Sniffer - Listen for all RF signals and decode them

This tool listens for RF signals and shows:
1. Raw RF codes received
2. Decoded lamp ID and command (if recognized)
3. Timing information (gaps between signals)
4. Whether signals look like echoes/responses

Run this while the main lamp_control_mqtt.py is running to see
if lamps echo back commands or if there's any feedback mechanism.

Usage:
    python3 rf_sniffer.py [-r GPIO_PIN]
"""

import argparse
import logging
import time
from time import sleep
from datetime import datetime

from RPi import GPIO
from rpi_rf import RFDevice

# Import constants from main module
import lamp_control_mqtt as lcm

logging.basicConfig(
    level=logging.INFO, datefmt="%Y-%m-%d %H:%M:%S", format="%(asctime)-15s - %(message)s"
)


# Color codes for terminal output
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def decode_rf_code(code):
    """
    Decode an RF code into lamp ID and command.
    Returns (lamp_id, lamp_name, command_offset, command_name) or None if unknown.
    """
    # Try to match against known lamps
    known_lamps = {
        lcm.LIVING_ROOM_LAMP: "Living Room",
        lcm.STUDY_LAMPS: "Study",
        lcm.STUDY_DESK_LAMP: "Study Desk",
        lcm.STUDY_TABLE_LAMP: "Study Table",
    }

    for lamp_id, lamp_name in known_lamps.items():
        # Check if this code could be from this lamp
        if lamp_id <= code <= lamp_id + lcm.MAX_OFFSET:
            offset = code - lamp_id
            if offset in lcm.CMDS2NAMES:
                return lamp_id, lamp_name, offset, lcm.CMDS2NAMES[offset]

    return None


def format_decoded(decoded):
    """Format decoded information with colors."""
    if decoded is None:
        return f"{Colors.FAIL}UNKNOWN{Colors.ENDC}"

    lamp_id, lamp_name, offset, cmd_name = decoded

    # Color code by command type
    if offset == lcm.ON_OFF_OFFSET:
        color = Colors.OKGREEN
    elif offset == lcm.CCT_OFFSET:
        color = Colors.OKCYAN
    elif offset == lcm.BRIGHTNESS_UP_OFFSET:
        color = Colors.WARNING
    elif offset == lcm.BRIGHTNESS_DOWN_OFFSET:
        color = Colors.OKBLUE
    else:
        color = Colors.ENDC

    return f"{color}{lamp_name}{Colors.ENDC} - {color}{cmd_name}{Colors.ENDC}"


def main():
    parser = argparse.ArgumentParser(description="RF Signal Sniffer")
    parser.add_argument(
        "-r", dest="gpio_rx", type=int, default=23, help="GPIO receive pin (Default: 23)"
    )
    args = parser.parse_args()

    print(f"\n{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}RF Signal Sniffer{Colors.ENDC}")
    print(f"{Colors.BOLD}{'='*70}{Colors.ENDC}\n")
    print(f"Listening on GPIO pin {args.gpio_rx}...")
    print(f"Press Ctrl+C to exit\n")
    print(f"{Colors.BOLD}Known Lamps:{Colors.ENDC}")
    print(f"  Living Room:  {lcm.LIVING_ROOM_LAMP}")
    print(f"  Study:        {lcm.STUDY_LAMPS}")
    print(f"  Study Desk:   {lcm.STUDY_DESK_LAMP}")
    print(f"  Study Table:  {lcm.STUDY_TABLE_LAMP}")
    print(f"\n{Colors.BOLD}Watching for signals...{Colors.ENDC}\n")

    rxdevice = RFDevice(args.gpio_rx)
    rxdevice.enable_rx()

    last_timestamp = None
    last_code = None
    signal_count = 0

    try:
        while True:
            if rxdevice.rx_code_timestamp != last_timestamp:
                signal_count += 1
                timestamp = rxdevice.rx_code_timestamp
                code = rxdevice.rx_code

                # Calculate gap from previous signal
                gap = None
                gap_ms = None
                if last_timestamp is not None:
                    gap = timestamp - last_timestamp
                    gap_ms = gap / 1000.0  # Convert to milliseconds

                # Decode the signal
                decoded = decode_rf_code(code)

                # Check if this looks like a duplicate/echo
                is_duplicate = False
                if last_code == code and gap is not None and gap < lcm.MIN_GAP:
                    is_duplicate = True

                # Format output
                time_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]

                print(f"{Colors.BOLD}[{signal_count:04d}]{Colors.ENDC} {time_str}")
                print(f"  Code: {Colors.BOLD}{code}{Colors.ENDC}")
                print(f"  Decoded: {format_decoded(decoded)}")

                if gap_ms is not None:
                    gap_color = Colors.FAIL if is_duplicate else Colors.ENDC
                    print(f"  Gap: {gap_color}{gap_ms:.1f}ms{Colors.ENDC}", end="")
                    if is_duplicate:
                        print(
                            f" {Colors.FAIL}(DUPLICATE - gap < {lcm.MIN_GAP/1000:.0f}ms){Colors.ENDC}"
                        )
                    else:
                        print()

                # Check if this could be an echo
                if decoded is not None and gap_ms is not None:
                    lamp_id, lamp_name, offset, cmd_name = decoded

                    # If we see the same command twice in quick succession,
                    # it could be: 1) button held down, 2) echo from lamp, 3) our retry
                    if 50 < gap_ms < 500:  # Between 50ms and 500ms
                        print(
                            f"  {Colors.WARNING}⚠ Possible echo/response? (gap={gap_ms:.1f}ms){Colors.ENDC}"
                        )

                print()  # Blank line between signals

                last_timestamp = timestamp
                last_code = code

            sleep(0.0001)  # Same polling rate as main program

    except KeyboardInterrupt:
        print(f"\n{Colors.BOLD}Shutting down...{Colors.ENDC}")
        print(f"Total signals received: {signal_count}")
    finally:
        rxdevice.cleanup()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
