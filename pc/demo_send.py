"""
demo_send.py  –  Send packets from the PC to the Pico (optional two-way test).

Usage:
    python demo_send.py --port /dev/ttyACM0
"""

import argparse
import time
from protocol import CustomProtocol

def main():
    parser = argparse.ArgumentParser(description="Send packets from PC to Pico")
    parser.add_argument("--port", required=True, help="Serial port")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    with CustomProtocol(port=args.port, baud_rate=args.baud) as proto:
        print("Sending test packets...\n")

        proto.send("Hello Pico!")
        print("Sent string: 'Hello Pico!'")
        time.sleep(0.5)

        proto.send(42)
        print("Sent int: 42")
        time.sleep(0.5)

        proto.send(3.14)
        print("Sent float: 3.14")
        time.sleep(0.5)

        print("\nDone.")

if __name__ == "__main__":
    main()
