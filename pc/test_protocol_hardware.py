"""
test_protocol_hardware.py -- Hardware-in-the-loop test runner.

Requires the Pico to be flashed with custom_protocol_test.uf2.

Usage:
    python test_protocol_hardware.py --port /dev/tty.usbmodem101   # Mac
    python test_protocol_hardware.py --port /dev/ttyACM0           # Linux
    python test_protocol_hardware.py --port COM3                   # Windows

After opening the port this script sends a single ACK byte (0x06) to
signal readiness. The Pico waits for that byte before transmitting,
ensuring no packets are missed during USB enumeration. It then sends a
fixed sequence of 29 packets followed by the sentinel string "__DONE__".
This script checks each packet's type, SEQ number, and decoded value,
then prints a per-test result and a final pass/fail summary.

Exit code: 0 = all tests passed, 1 = one or more failures.
"""

import argparse
import math
import sys
from protocol import (
    CustomProtocol,
    ProtocolChecksumError,
    ProtocolFramingError,
    ProtocolLengthError,
    PROTO_TYPE_STRING,
    PROTO_TYPE_INT,
    PROTO_TYPE_FLOAT,
    PROTO_TYPE_ARRAY,
    PROTO_TYPE_DICT,
)

SENTINEL = "__DONE__"
FLOAT_TOL = 1e-3   # tolerance for single-precision float comparisons

# --- Expected packet definitions ---------------------------------------------
#
# Each entry is a dict:
#   seq       - expected SEQ byte
#   type      - expected TYPE byte
#   desc      - human-readable label for output
#   check(v)  - callable that returns (ok: bool, detail: str)

def _str_check(expected):
    def check(v):
        ok = v == expected
        return ok, f"expected {expected!r}, got {v!r}"
    return check

def _int_check(expected):
    def check(v):
        ok = v == expected
        return ok, f"expected {expected}, got {v}"
    return check

def _float_check(expected):
    def check(v):
        if math.isfinite(expected):
            ok = abs(v - expected) / (abs(expected) + 1e-30) < FLOAT_TOL
        else:
            ok = v == expected
        return ok, f"expected ~{expected}, got {v}"
    return check

def _int_array_check(expected):
    def check(v):
        ok = v == expected
        return ok, f"expected {expected}, got {v}"
    return check

def _float_array_check(expected):
    def check(v):
        if len(v) != len(expected):
            return False, f"length mismatch: expected {len(expected)}, got {len(v)}"
        for i, (a, b) in enumerate(zip(v, expected)):
            if abs(a - b) > FLOAT_TOL:
                return False, f"element {i}: expected ~{b}, got {a}"
        return True, ""
    return check

def _dict_check(expected):
    """
    expected is a dict of {key: value} where value may be int, float, or str.
    Float values are compared with FLOAT_TOL.
    """
    def check(v):
        if set(v.keys()) != set(expected.keys()):
            return False, f"key mismatch: expected {set(expected.keys())}, got {set(v.keys())}"
        for k, exp_val in expected.items():
            got_val = v[k]
            if isinstance(exp_val, float):
                if abs(got_val - exp_val) > FLOAT_TOL:
                    return False, f"key {k!r}: expected ~{exp_val}, got {got_val}"
            else:
                if got_val != exp_val:
                    return False, f"key {k!r}: expected {exp_val!r}, got {got_val!r}"
        return True, ""
    return check


EXPECTED = [
    # SEQ 00
    {"seq": 0,  "type": PROTO_TYPE_STRING, "desc": 'STRING "Hello from Pico!"',
     "check": _str_check("Hello from Pico!")},
    # SEQ 01
    {"seq": 1,  "type": PROTO_TYPE_STRING, "desc": 'STRING "" (empty)',
     "check": _str_check("")},
    # SEQ 02-06  Integers
    {"seq": 2,  "type": PROTO_TYPE_INT, "desc": "INT 0",
     "check": _int_check(0)},
    {"seq": 3,  "type": PROTO_TYPE_INT, "desc": "INT 1",
     "check": _int_check(1)},
    {"seq": 4,  "type": PROTO_TYPE_INT, "desc": "INT -1",
     "check": _int_check(-1)},
    {"seq": 5,  "type": PROTO_TYPE_INT, "desc": "INT INT32_MAX (2147483647)",
     "check": _int_check(2147483647)},
    {"seq": 6,  "type": PROTO_TYPE_INT, "desc": "INT INT32_MIN (-2147483648)",
     "check": _int_check(-2147483648)},
    # SEQ 07-10  Floats
    {"seq": 7,  "type": PROTO_TYPE_FLOAT, "desc": "FLOAT 0.0",
     "check": _float_check(0.0)},
    {"seq": 8,  "type": PROTO_TYPE_FLOAT, "desc": "FLOAT 3.14",
     "check": _float_check(3.14)},
    {"seq": 9,  "type": PROTO_TYPE_FLOAT, "desc": "FLOAT -273.15",
     "check": _float_check(-273.15)},
    {"seq": 10, "type": PROTO_TYPE_FLOAT, "desc": "FLOAT 1.0e20",
     "check": _float_check(1.0e20)},
    # SEQ 11-14  Arrays
    {"seq": 11, "type": PROTO_TYPE_ARRAY, "desc": "ARRAY INT [1, -2, 300, -400, 0]",
     "check": _int_array_check([1, -2, 300, -400, 0])},
    {"seq": 12, "type": PROTO_TYPE_ARRAY, "desc": "ARRAY INT [2147483647] (single element)",
     "check": _int_array_check([2147483647])},
    {"seq": 13, "type": PROTO_TYPE_ARRAY, "desc": "ARRAY FLOAT [18.0, 19.2, 20.4, 21.6, 22.8]",
     "check": _float_array_check([18.0, 19.2, 20.4, 21.6, 22.8])},
    {"seq": 14, "type": PROTO_TYPE_ARRAY, "desc": "ARRAY FLOAT [0.0] (single element)",
     "check": _float_array_check([0.0])},
    # SEQ 15-16  Dicts
    {"seq": 15, "type": PROTO_TYPE_DICT,
     "desc": 'DICT {temp:22.5, uptime:42, status:"OK"}',
     "check": _dict_check({"temp": 22.5, "uptime": 42, "status": "OK"})},
    {"seq": 16, "type": PROTO_TYPE_DICT,
     "desc": "DICT {a:1 ... p:16} (16 entries, maximum size)",
     "check": _dict_check({k: i + 1 for i, k in enumerate("abcdefghijklmnop")})},
    # SEQ 17  Special characters
    {"seq": 17, "type": PROTO_TYPE_STRING, "desc": 'STRING special ASCII "!\\"#$%&\'()*+,-./"',
     "check": _str_check("!\"#$%&'()*+,-./")},
    # SEQ 18-19  Sequence continuity
    {"seq": 18, "type": PROTO_TYPE_INT,   "desc": "INT 42 (seq continuity check)",
     "check": _int_check(42)},
    {"seq": 19, "type": PROTO_TYPE_FLOAT, "desc": "FLOAT 42.0 (seq continuity check)",
     "check": _float_check(42.0)},
    # SEQ 20-27  Rapid-fire string burst
    *[
        {"seq": 20 + i, "type": PROTO_TYPE_STRING,
         "desc": f'STRING "PACKET_{20 + i}" (rapid-fire burst)',
         "check": _str_check(f"PACKET_{20 + i}")}
        for i in range(8)
    ],
    # SEQ 28  Sentinel
    {"seq": 28, "type": PROTO_TYPE_STRING, "desc": 'STRING "__DONE__" (sentinel)',
     "check": _str_check(SENTINEL)},
]

# --- Test runner -------------------------------------------------------------

def run(port: str, baud: int) -> int:
    passed = 0
    failed = 0
    errors = 0

    print(f"\nConnecting to {port} at {baud} baud ...")

    with CustomProtocol(port=port, baud_rate=baud, timeout=10.0) as proto:
        # Send the ACK handshake byte so the Pico knows the PC is ready.
        proto._serial.write(bytes([0x06]))
        proto._serial.flush()
        print(f"Connected. Handshake sent. Waiting for {len(EXPECTED)} packets ...\n")
        print(f"  {'SEQ':>3}  {'TYPE':<8}  {'RESULT':<6}  DESCRIPTION")
        print(f"  {'---':>3}  {'----':<8}  {'------':<6}  ---------------------------------------")

        for exp in EXPECTED:
            # Receive next packet, retrying on protocol errors
            try:
                pkt = proto.receive()
            except (ProtocolChecksumError, ProtocolFramingError, ProtocolLengthError) as e:
                print(f"  {'?':>3}  {'?':<8}  {'ERROR':<6}  Protocol error before packet {exp['seq']}: {e}")
                errors += 1
                failed += 1
                continue

            # Check SEQ
            seq_ok = pkt.seq == exp["seq"]

            # Check TYPE
            type_ok = pkt.type == exp["type"]

            # Check value
            try:
                value = pkt.decoded_value()
                val_ok, val_detail = exp["check"](value)
            except Exception as e:
                val_ok, val_detail = False, f"decode raised {e}"

            ok = seq_ok and type_ok and val_ok

            if ok:
                result = "PASS"
                passed += 1
            else:
                result = "FAIL"
                failed += 1

            type_names = {
                PROTO_TYPE_STRING: "STRING",
                PROTO_TYPE_INT:    "INT",
                PROTO_TYPE_FLOAT:  "FLOAT",
                PROTO_TYPE_ARRAY:  "ARRAY",
                PROTO_TYPE_DICT:   "DICT",
            }
            type_label = type_names.get(pkt.type, f"0x{pkt.type:02X}")
            print(f"  {pkt.seq:03d}  {type_label:<8}  {result}  {exp['desc']}")

            if not seq_ok:
                print(f"         -> SEQ mismatch: expected {exp['seq']}, got {pkt.seq}")
            if not type_ok:
                exp_name = type_names.get(exp["type"], f"0x{exp['type']:02X}")
                print(f"         -> TYPE mismatch: expected {exp_name}, got {type_label}")
            if not val_ok:
                print(f"         -> Value mismatch: {val_detail}")

            # Stop cleanly once the sentinel arrives regardless of result
            if pkt.type == PROTO_TYPE_STRING:
                try:
                    if pkt.decoded_value() == SENTINEL:
                        break
                except Exception:
                    pass

    total = passed + failed
    print(f"\n  {'=' * 55}")
    print(f"  Results: {passed}/{total} passed", end="")
    if errors:
        print(f"  ({errors} protocol error(s))", end="")
    if failed == 0:
        print("  -- all tests passed")
    else:
        print(f"  -- {failed} FAILED")
    print(f"  {'=' * 55}\n")

    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="Hardware-in-the-loop test runner for the custom protocol."
    )
    parser.add_argument("--port", required=True, help="Serial port (e.g. /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()
    sys.exit(run(args.port, args.baud))


if __name__ == "__main__":
    main()
