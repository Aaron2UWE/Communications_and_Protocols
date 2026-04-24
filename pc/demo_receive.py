"""
demo_receive.py  –  Receive and display all packet types from the Pico.

Usage:
    python demo_receive.py --port /dev/tty.usbmodem101   # Mac
    python demo_receive.py --port /dev/ttyACM0           # Linux
    python demo_receive.py --port COM3                   # Windows
"""

import argparse
import sys
from protocol import (
    CustomProtocol,
    ProtocolChecksumError,
    ProtocolFramingError,
    ProtocolLengthError,
    PROTO_TYPE_ARRAY,
    PROTO_TYPE_DICT,
)

def pretty_print(packet):
    value = packet.decoded_value()
    if packet.type == PROTO_TYPE_ARRAY:
        print(f"[SEQ {packet.seq:03d}] ARRAY  ({len(value)} elements): {value}")
    elif packet.type == PROTO_TYPE_DICT:
        print(f"[SEQ {packet.seq:03d}] DICT   ({len(value)} keys):")
        for k, v in value.items():
            print(f"           {k}: {v}")
    else:
        print(f"[SEQ {packet.seq:03d}] {packet!r}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    print(f"Connecting to {args.port} ...")
    with CustomProtocol(port=args.port, baud_rate=args.baud) as proto:
        print("Connected. Waiting for packets (Ctrl+C to quit)...\n")
        while True:
            try:
                pretty_print(proto.receive())
            except ProtocolChecksumError as e:
                print(f"  [!] Checksum error: {e}", file=sys.stderr)
            except ProtocolFramingError as e:
                print(f"  [!] Framing error: {e}", file=sys.stderr)
            except ProtocolLengthError as e:
                print(f"  [!] Length error: {e}", file=sys.stderr)
            except KeyboardInterrupt:
                print("\nDisconnecting.")
                break

if __name__ == "__main__":
    main()
