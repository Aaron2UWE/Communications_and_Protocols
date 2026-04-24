"""
test_protocol.py -- Unit test suite for the CustomProtocol PC-side implementation.

Run with:
    python test_protocol.py

No hardware required. All tests operate on in-memory byte buffers.
"""

import struct
import sys
import traceback
from protocol import (
    CustomProtocol,
    Packet,
    ProtocolChecksumError,
    ProtocolFramingError,
    ProtocolLengthError,
    PROTO_START,
    PROTO_END,
    PROTO_TYPE_STRING,
    PROTO_TYPE_INT,
    PROTO_TYPE_FLOAT,
    PROTO_TYPE_ARRAY,
    PROTO_TYPE_DICT,
)

# --- Test Framework -----------------------------------------------------------

_results = []

def run_test(name, fn):
    try:
        fn()
        _results.append((name, "PASS", None))
        print(f"  PASS  {name}")
    except Exception as e:
        _results.append((name, "FAIL", e))
        print(f"  FAIL  {name}")
        traceback.print_exc()

def section(title):
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")

# --- Helpers -----------------------------------------------------------------

def build_raw_packet(type_: int, seq: int, payload: bytes) -> bytes:
    """Manually assemble a valid binary packet."""
    csum = CustomProtocol._checksum(type_, seq, payload)
    return bytes([PROTO_START, type_, seq, len(payload)]) + payload + bytes([csum, PROTO_END])

def decode_packet(raw: bytes) -> Packet:
    """Feed raw bytes into a Packet object by simulating receive() parsing."""
    # Parse manually, mirroring receive() logic
    assert raw[0] == PROTO_START
    type_ = raw[1]
    seq   = raw[2]
    length = raw[3]
    payload = raw[4:4 + length]
    checksum = raw[4 + length]
    end_byte = raw[4 + length + 1]

    if end_byte != PROTO_END:
        raise ProtocolFramingError(f"Bad END byte: 0x{end_byte:02X}")
    expected = CustomProtocol._checksum(type_, seq, payload)
    if checksum != expected:
        raise ProtocolChecksumError("Checksum mismatch")
    return Packet(type_=type_, seq=seq, payload=payload)

def make_proto() -> CustomProtocol:
    """Return a CustomProtocol instance without opening a serial port."""
    p = CustomProtocol.__new__(CustomProtocol)
    p._seq = 0
    p._serial = None
    return p

# --- Section 1: Packet Framing ------------------------------------------------

section("1. Packet Framing")

def test_start_byte():
    raw = build_raw_packet(PROTO_TYPE_STRING, 0, b"test")
    assert raw[0] == 0xAA, f"Expected START 0xAA, got 0x{raw[0]:02X}"

run_test("START byte is 0xAA", test_start_byte)

def test_end_byte():
    raw = build_raw_packet(PROTO_TYPE_STRING, 0, b"test")
    assert raw[-1] == 0xFF, f"Expected END 0xFF, got 0x{raw[-1]:02X}"

run_test("END byte is 0xFF", test_end_byte)

def test_length_field():
    payload = b"Hello"
    raw = build_raw_packet(PROTO_TYPE_STRING, 0, payload)
    assert raw[3] == len(payload), "LENGTH field mismatch"

run_test("LENGTH field matches payload size", test_length_field)

def test_total_packet_size():
    payload = b"ABCDE"
    raw = build_raw_packet(PROTO_TYPE_STRING, 0, payload)
    assert len(raw) == 6 + len(payload), "Total packet size wrong"

run_test("Total packet size = 6 + len(payload)", test_total_packet_size)

def test_empty_payload():
    raw = build_raw_packet(PROTO_TYPE_STRING, 0, b"")
    pkt = decode_packet(raw)
    assert pkt.payload == b""

run_test("Empty payload (LENGTH=0) frames correctly", test_empty_payload)

def test_max_payload():
    payload = b"A" * 255
    raw = build_raw_packet(PROTO_TYPE_STRING, 0, payload)
    pkt = decode_packet(raw)
    assert pkt.payload == payload

run_test("Maximum payload (LENGTH=255) frames correctly", test_max_payload)

def test_seq_field_stored():
    raw = build_raw_packet(PROTO_TYPE_INT, 42, struct.pack("<i", 0))
    pkt = decode_packet(raw)
    assert pkt.seq == 42

run_test("SEQ field is stored in decoded packet", test_seq_field_stored)

# --- Section 2: Checksum ------------------------------------------------------

section("2. Checksum")

def test_checksum_correct():
    payload = b"Hello"
    raw = build_raw_packet(PROTO_TYPE_STRING, 0, payload)
    pkt = decode_packet(raw)   # would raise ProtocolChecksumError if wrong
    assert True

run_test("Valid packet passes checksum", test_checksum_correct)

def test_checksum_detects_payload_corruption():
    raw = bytearray(build_raw_packet(PROTO_TYPE_STRING, 0, b"Hello"))
    raw[5] ^= 0xFF   # corrupt first payload byte
    try:
        decode_packet(bytes(raw))
        assert False, "Should have raised ProtocolChecksumError"
    except ProtocolChecksumError:
        pass

run_test("Corrupted payload byte raises ProtocolChecksumError", test_checksum_detects_payload_corruption)

def test_checksum_detects_type_corruption():
    raw = bytearray(build_raw_packet(PROTO_TYPE_STRING, 0, b"Hi"))
    raw[1] ^= 0x10   # corrupt TYPE byte
    try:
        decode_packet(bytes(raw))
        assert False, "Should have raised ProtocolChecksumError"
    except ProtocolChecksumError:
        pass

run_test("Corrupted TYPE byte raises ProtocolChecksumError", test_checksum_detects_type_corruption)

def test_checksum_detects_seq_corruption():
    raw = bytearray(build_raw_packet(PROTO_TYPE_STRING, 5, b"Hi"))
    raw[2] ^= 0x01   # corrupt SEQ byte
    try:
        decode_packet(bytes(raw))
        assert False, "Should have raised ProtocolChecksumError"
    except ProtocolChecksumError:
        pass

run_test("Corrupted SEQ byte raises ProtocolChecksumError", test_checksum_detects_seq_corruption)

def test_checksum_is_xor_of_all_preceding():
    type_, seq, payload = PROTO_TYPE_INT, 7, struct.pack("<i", 100)
    expected = PROTO_START ^ type_ ^ seq ^ len(payload)
    for b in payload:
        expected ^= b
    computed = CustomProtocol._checksum(type_, seq, payload)
    assert computed == (expected & 0xFF)

run_test("Checksum equals XOR of all header + payload bytes", test_checksum_is_xor_of_all_preceding)

def test_bad_end_byte_raises_framing_error():
    raw = bytearray(build_raw_packet(PROTO_TYPE_STRING, 0, b"Hi"))
    raw[-1] = 0x00   # replace END with 0x00
    try:
        decode_packet(bytes(raw))
        assert False, "Should have raised ProtocolFramingError"
    except ProtocolFramingError:
        pass

run_test("Wrong END byte raises ProtocolFramingError", test_bad_end_byte_raises_framing_error)

# --- Section 3: Primitive Encode / Decode ------------------------------------

section("3. Primitive Encode / Decode")

def test_string_roundtrip():
    proto = make_proto()
    payload = "Hello from Pico!".encode()
    raw = build_raw_packet(PROTO_TYPE_STRING, 0, payload)
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == "Hello from Pico!"

run_test("String roundtrip", test_string_roundtrip)

def test_string_utf8():
    proto = make_proto()
    text = "Angstrom"
    payload = text.encode("utf-8")
    raw = build_raw_packet(PROTO_TYPE_STRING, 0, payload)
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == text

run_test("UTF-8 string roundtrip", test_string_utf8)

def test_int_positive():
    payload = struct.pack("<i", 12345)
    raw = build_raw_packet(PROTO_TYPE_INT, 0, payload)
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == 12345

run_test("Positive int roundtrip", test_int_positive)

def test_int_negative():
    payload = struct.pack("<i", -42)
    raw = build_raw_packet(PROTO_TYPE_INT, 0, payload)
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == -42

run_test("Negative int roundtrip", test_int_negative)

def test_int_zero():
    payload = struct.pack("<i", 0)
    raw = build_raw_packet(PROTO_TYPE_INT, 0, payload)
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == 0

run_test("Zero int roundtrip", test_int_zero)

def test_int_max():
    payload = struct.pack("<i", 2**31 - 1)
    raw = build_raw_packet(PROTO_TYPE_INT, 0, payload)
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == 2**31 - 1

run_test("INT32_MAX roundtrip", test_int_max)

def test_int_min():
    payload = struct.pack("<i", -(2**31))
    raw = build_raw_packet(PROTO_TYPE_INT, 0, payload)
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == -(2**31)

run_test("INT32_MIN roundtrip", test_int_min)

def test_float_roundtrip():
    payload = struct.pack("<f", 3.14)
    raw = build_raw_packet(PROTO_TYPE_FLOAT, 0, payload)
    pkt = decode_packet(raw)
    assert abs(pkt.decoded_value() - 3.14) < 0.001

run_test("Float roundtrip (pi)", test_float_roundtrip)

def test_float_negative():
    payload = struct.pack("<f", -273.15)
    raw = build_raw_packet(PROTO_TYPE_FLOAT, 0, payload)
    pkt = decode_packet(raw)
    assert abs(pkt.decoded_value() - (-273.15)) < 0.01

run_test("Negative float roundtrip", test_float_negative)

def test_float_zero():
    payload = struct.pack("<f", 0.0)
    raw = build_raw_packet(PROTO_TYPE_FLOAT, 0, payload)
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == 0.0

run_test("Zero float roundtrip", test_float_zero)

# --- Section 4: Array Encode / Decode ----------------------------------------

section("4. Array Encode / Decode")

def _build_array_payload(elem_type: int, values, fmt: str) -> bytes:
    packed = b"".join(struct.pack(fmt, v) for v in values)
    return bytes([elem_type, len(values)]) + packed

def test_int_array_roundtrip():
    values = [1, -2, 300, -400, 0]
    payload = _build_array_payload(PROTO_TYPE_INT, values, "<i")
    raw = build_raw_packet(PROTO_TYPE_ARRAY, 0, payload)
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == values

run_test("Int array roundtrip (5 elements)", test_int_array_roundtrip)

def test_float_array_roundtrip():
    values = [18.0, 19.2, 20.4, 21.6, 22.8]
    payload = _build_array_payload(PROTO_TYPE_FLOAT, values, "<f")
    raw = build_raw_packet(PROTO_TYPE_ARRAY, 0, payload)
    pkt = decode_packet(raw)
    decoded = pkt.decoded_value()
    for a, b in zip(decoded, values):
        assert abs(a - b) < 0.001, f"{a} != {b}"

run_test("Float array roundtrip (5 elements)", test_float_array_roundtrip)

def test_single_element_array():
    values = [42]
    payload = _build_array_payload(PROTO_TYPE_INT, values, "<i")
    raw = build_raw_packet(PROTO_TYPE_ARRAY, 0, payload)
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == [42]

run_test("Single-element array roundtrip", test_single_element_array)

def test_array_count_field():
    values = [1, 2, 3]
    payload = _build_array_payload(PROTO_TYPE_INT, values, "<i")
    assert payload[1] == 3, "COUNT field in array payload incorrect"

run_test("Array COUNT field reflects element count", test_array_count_field)

def test_array_truncated_raises():
    # Build a payload that claims count=5 but only has 2 elements
    payload = bytes([PROTO_TYPE_INT, 5]) + struct.pack("<i", 1) + struct.pack("<i", 2)
    raw = build_raw_packet(PROTO_TYPE_ARRAY, 0, payload)
    pkt = decode_packet(raw)
    try:
        pkt.decoded_value()
        assert False, "Should have raised ProtocolLengthError"
    except ProtocolLengthError:
        pass

run_test("Truncated array payload raises ProtocolLengthError", test_array_truncated_raises)

def test_array_unsupported_type_raises():
    payload = bytes([0x99, 2]) + b"\x00" * 8  # unsupported element type
    raw = build_raw_packet(PROTO_TYPE_ARRAY, 0, payload)
    pkt = decode_packet(raw)
    try:
        pkt.decoded_value()
        assert False, "Should have raised ProtocolLengthError"
    except ProtocolLengthError:
        pass

run_test("Unsupported array element type raises ProtocolLengthError", test_array_unsupported_type_raises)

def test_array_too_short_raises():
    payload = bytes([PROTO_TYPE_INT])   # missing COUNT byte
    raw = build_raw_packet(PROTO_TYPE_ARRAY, 0, payload)
    pkt = decode_packet(raw)
    try:
        pkt.decoded_value()
        assert False, "Should have raised ProtocolLengthError"
    except ProtocolLengthError:
        pass

run_test("Array payload with no COUNT byte raises ProtocolLengthError", test_array_too_short_raises)

# --- Section 5: Dict Encode / Decode -----------------------------------------

section("5. Dict Encode / Decode")

def build_dict_payload(entries: list) -> bytes:
    """entries = list of (key, value) where value is int, float, or str."""
    buf = bytes([len(entries)])
    for key, val in entries:
        kb = key.encode("utf-8")[:15]
        buf += bytes([len(kb)]) + kb
        if isinstance(val, float):
            buf += bytes([PROTO_TYPE_FLOAT]) + struct.pack("<f", val)
        elif isinstance(val, int):
            buf += bytes([PROTO_TYPE_INT]) + struct.pack("<i", val)
        elif isinstance(val, str):
            vb = val.encode("utf-8")[:31]
            buf += bytes([PROTO_TYPE_STRING, len(vb)]) + vb
    return buf

def test_dict_int_values():
    entries = [("count", 7), ("uptime", 1000)]
    payload = build_dict_payload(entries)
    raw = build_raw_packet(PROTO_TYPE_DICT, 0, payload)
    pkt = decode_packet(raw)
    d = pkt.decoded_value()
    assert d["count"] == 7
    assert d["uptime"] == 1000

run_test("Dict with int values roundtrip", test_dict_int_values)

def test_dict_float_values():
    entries = [("temp", 22.5), ("humidity", 55.0)]
    payload = build_dict_payload(entries)
    raw = build_raw_packet(PROTO_TYPE_DICT, 0, payload)
    pkt = decode_packet(raw)
    d = pkt.decoded_value()
    assert abs(d["temp"] - 22.5) < 0.01
    assert abs(d["humidity"] - 55.0) < 0.01

run_test("Dict with float values roundtrip", test_dict_float_values)

def test_dict_string_values():
    entries = [("status", "OK"), ("mode", "idle")]
    payload = build_dict_payload(entries)
    raw = build_raw_packet(PROTO_TYPE_DICT, 0, payload)
    pkt = decode_packet(raw)
    d = pkt.decoded_value()
    assert d["status"] == "OK"
    assert d["mode"] == "idle"

run_test("Dict with string values roundtrip", test_dict_string_values)

def test_dict_mixed_values():
    entries = [("temp", 22.5), ("uptime", 42), ("status", "OK")]
    payload = build_dict_payload(entries)
    raw = build_raw_packet(PROTO_TYPE_DICT, 0, payload)
    pkt = decode_packet(raw)
    d = pkt.decoded_value()
    assert abs(d["temp"] - 22.5) < 0.01
    assert d["uptime"] == 42
    assert d["status"] == "OK"

run_test("Dict with mixed value types roundtrip", test_dict_mixed_values)

def test_dict_empty_raises():
    payload = bytes([0])  # count=0, no entries
    raw = build_raw_packet(PROTO_TYPE_DICT, 0, payload)
    pkt = decode_packet(raw)
    d = pkt.decoded_value()
    assert d == {}

run_test("Empty dict (0 entries) decodes to {}", test_dict_empty_raises)

def test_dict_key_max_length():
    key = "A" * 15   # PROTO_MAX_KEY_LEN
    entries = [(key, 1)]
    payload = build_dict_payload(entries)
    raw = build_raw_packet(PROTO_TYPE_DICT, 0, payload)
    pkt = decode_packet(raw)
    d = pkt.decoded_value()
    assert key in d

run_test("Dict key at maximum length (15 chars) decodes correctly", test_dict_key_max_length)

def test_dict_too_short_raises():
    payload = b""  # completely empty
    raw = build_raw_packet(PROTO_TYPE_DICT, 0, payload)
    pkt = decode_packet(raw)
    try:
        pkt.decoded_value()
        assert False, "Should have raised ProtocolLengthError"
    except ProtocolLengthError:
        pass

run_test("Empty dict payload raises ProtocolLengthError", test_dict_too_short_raises)

# --- Section 6: PC-Side Encoding (CustomProtocol.send helpers) ---------------

section("6. PC-Side Encoding (CustomProtocol._build_packet)")

def test_send_string_type_byte():
    proto = make_proto()
    raw = proto._build_packet(PROTO_TYPE_STRING, "Hi".encode())
    assert raw[1] == PROTO_TYPE_STRING

run_test("_build_packet sets TYPE=STRING correctly", test_send_string_type_byte)

def test_send_int_payload():
    proto = make_proto()
    raw = proto._build_packet(PROTO_TYPE_INT, struct.pack("<i", 999))
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == 999

run_test("_build_packet INT payload encodes correctly", test_send_int_payload)

def test_send_increments_seq():
    proto = make_proto()
    raw0 = proto._build_packet(PROTO_TYPE_INT, struct.pack("<i", 0))
    raw1 = proto._build_packet(PROTO_TYPE_INT, struct.pack("<i", 1))
    assert raw0[2] == 0
    assert raw1[2] == 1

run_test("Sequence number increments with each packet", test_send_increments_seq)

def test_seq_wraps_at_256():
    proto = make_proto()
    proto._seq = 255
    raw_255 = proto._build_packet(PROTO_TYPE_INT, struct.pack("<i", 0))
    raw_0   = proto._build_packet(PROTO_TYPE_INT, struct.pack("<i", 0))
    assert raw_255[2] == 255
    assert raw_0[2]   == 0

run_test("Sequence number wraps from 255 to 0", test_seq_wraps_at_256)

def test_encode_array_int():
    proto = make_proto()
    payload = proto._encode_array([1, 2, 3])
    assert payload[0] == PROTO_TYPE_INT
    assert payload[1] == 3

run_test("_encode_array infers INT type from first element", test_encode_array_int)

def test_encode_array_float():
    proto = make_proto()
    payload = proto._encode_array([1.0, 2.0])
    assert payload[0] == PROTO_TYPE_FLOAT
    assert payload[1] == 2

run_test("_encode_array infers FLOAT type from first element", test_encode_array_float)

def test_encode_array_empty_raises():
    proto = make_proto()
    try:
        proto._encode_array([])
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

run_test("_encode_array([]) raises ValueError", test_encode_array_empty_raises)

def test_encode_dict_mixed():
    proto = make_proto()
    d = {"temp": 20.0, "count": 5, "status": "OK"}
    payload = proto._encode_dict(d)
    # Re-decode it
    raw = build_raw_packet(PROTO_TYPE_DICT, 0, payload)
    pkt = decode_packet(raw)
    result = pkt.decoded_value()
    assert abs(result["temp"] - 20.0) < 0.01
    assert result["count"] == 5
    assert result["status"] == "OK"

run_test("_encode_dict with mixed types roundtrips correctly", test_encode_dict_mixed)

# --- Section 7: Error / Edge Cases -------------------------------------------

section("7. Error & Edge Cases")

def test_bool_treated_as_int():
    proto = make_proto()
    payload = struct.pack("<i", int(True))
    raw = proto._build_packet(PROTO_TYPE_INT, payload)
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == 1

run_test("bool True encodes as INT value 1", test_bool_treated_as_int)

def test_unknown_type_returns_raw_bytes():
    payload = b"\xDE\xAD\xBE\xEF"
    raw = build_raw_packet(0xAB, 0, payload)  # 0xAB = unknown type
    pkt = decode_packet(raw)
    assert pkt.decoded_value() == payload

run_test("Unknown packet type returns raw bytes", test_unknown_type_returns_raw_bytes)

def test_repr_known_type():
    payload = "Test".encode()
    raw = build_raw_packet(PROTO_TYPE_STRING, 3, payload)
    pkt = decode_packet(raw)
    r = repr(pkt)
    assert "STRING" in r
    assert "Test" in r
    assert "seq=3" in r

run_test("Packet.__repr__ includes type name, seq, and value", test_repr_known_type)

def test_repr_unknown_type():
    raw = build_raw_packet(0xAB, 0, b"\x01")
    pkt = decode_packet(raw)
    r = repr(pkt)
    assert "0xAB" in r

run_test("Packet.__repr__ shows hex for unknown type", test_repr_unknown_type)

def test_checksum_single_byte_payload():
    payload = bytes([0x01])
    csum = CustomProtocol._checksum(PROTO_TYPE_INT, 0, payload)
    assert isinstance(csum, int) and 0 <= csum <= 255

run_test("Checksum with single-byte payload returns valid byte", test_checksum_single_byte_payload)

def test_checksum_empty_payload():
    csum = CustomProtocol._checksum(PROTO_TYPE_STRING, 0, b"")
    expected = PROTO_START ^ PROTO_TYPE_STRING ^ 0 ^ 0
    assert csum == expected

run_test("Checksum with empty payload equals XOR of header fields only", test_checksum_empty_payload)

# --- Summary ------------------------------------------------------------------

total  = len(_results)
passed = sum(1 for _, s, _ in _results if s == "PASS")
failed = total - passed

print(f"\n{'=' * 60}")
print(f"  Results: {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
else:
    print("  -- all tests passed")
print(f"{'=' * 60}\n")

if failed:
    sys.exit(1)
