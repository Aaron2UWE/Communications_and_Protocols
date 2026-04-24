"""
CustomProtocol - PC-side implementation
Communicates with the Raspberry Pi Pico over USB Serial.

Packet format:
  [START 0xAA] [TYPE] [SEQ] [LENGTH] [PAYLOAD...] [CHECKSUM] [END 0xFF]

Supported types:
  0x01  STRING   - UTF-8 string
  0x02  INT      - little-endian int32
  0x03  FLOAT    - little-endian IEEE 754 float
  0x04  ARRAY    - typed array of int or float values
  0x05  DICT     - key-value pairs with mixed value types
"""

import serial
import struct
import time
from typing import Any, Optional

# --- Constants --------------------------------------------------------
PROTO_START = 0xAA
PROTO_END   = 0xFF

PROTO_TYPE_STRING = 0x01
PROTO_TYPE_INT    = 0x02
PROTO_TYPE_FLOAT  = 0x03
PROTO_TYPE_ARRAY  = 0x04
PROTO_TYPE_DICT   = 0x05

TYPE_NAMES = {
    PROTO_TYPE_STRING: "STRING",
    PROTO_TYPE_INT:    "INT",
    PROTO_TYPE_FLOAT:  "FLOAT",
    PROTO_TYPE_ARRAY:  "ARRAY",
    PROTO_TYPE_DICT:   "DICT",
}

# --- Errors -----------------------------------------------------------
class ProtocolChecksumError(Exception): pass
class ProtocolFramingError(Exception):  pass
class ProtocolLengthError(Exception):   pass

# --- Packet -----------------------------------------------------------
class Packet:
    def __init__(self, type_: int, seq: int, payload: bytes):
        self.type    = type_
        self.seq     = seq
        self.payload = payload

    def decoded_value(self) -> Any:
        if self.type == PROTO_TYPE_STRING:
            return self.payload.decode("utf-8", errors="replace")

        elif self.type == PROTO_TYPE_INT:
            return struct.unpack("<i", self.payload)[0]

        elif self.type == PROTO_TYPE_FLOAT:
            return struct.unpack("<f", self.payload)[0]

        elif self.type == PROTO_TYPE_ARRAY:
            return _decode_array(self.payload)

        elif self.type == PROTO_TYPE_DICT:
            return _decode_dict(self.payload)

        else:
            return self.payload  # raw bytes for unknown types

    def __repr__(self):
        type_name = TYPE_NAMES.get(self.type, f"0x{self.type:02X}")
        return f"Packet(type={type_name}, seq={self.seq}, value={self.decoded_value()!r})"


# --- Array Decoding ---------------------------------------------------
# Payload: [element_type 1B] [count 1B] [elements...]
def _decode_array(payload: bytes) -> list:
    if len(payload) < 2:
        raise ProtocolLengthError("Array payload too short")

    elem_type = payload[0]
    count     = payload[1]
    data      = payload[2:]
    result    = []

    if elem_type == PROTO_TYPE_INT:
        if len(data) < count * 4:
            raise ProtocolLengthError("Array INT data truncated")
        for i in range(count):
            result.append(struct.unpack_from("<i", data, i * 4)[0])

    elif elem_type == PROTO_TYPE_FLOAT:
        if len(data) < count * 4:
            raise ProtocolLengthError("Array FLOAT data truncated")
        for i in range(count):
            result.append(struct.unpack_from("<f", data, i * 4)[0])

    else:
        raise ProtocolLengthError(f"Unsupported array element type: 0x{elem_type:02X}")

    return result


# --- Dict Decoding ----------------------------------------------------
# Payload: [count 1B] then for each entry:
#   [key_len 1B] [key bytes] [value_type 1B] [value bytes]
# Value bytes: 4B for INT/FLOAT, [str_len 1B][str bytes] for STRING
def _decode_dict(payload: bytes) -> dict:
    if len(payload) < 1:
        raise ProtocolLengthError("Dict payload too short")

    count  = payload[0]
    pos    = 1
    result = {}

    for _ in range(count):
        # Key
        key_len = payload[pos]; pos += 1
        key     = payload[pos:pos + key_len].decode("utf-8"); pos += key_len

        # Value
        val_type = payload[pos]; pos += 1

        if val_type == PROTO_TYPE_INT:
            value = struct.unpack_from("<i", payload, pos)[0]; pos += 4
        elif val_type == PROTO_TYPE_FLOAT:
            value = struct.unpack_from("<f", payload, pos)[0]; pos += 4
        elif val_type == PROTO_TYPE_STRING:
            str_len = payload[pos]; pos += 1
            value   = payload[pos:pos + str_len].decode("utf-8"); pos += str_len
        else:
            raise ProtocolLengthError(f"Unknown dict value type: 0x{val_type:02X}")

        result[key] = value

    return result


# --- Protocol Class ---------------------------------------------------
class CustomProtocol:
    def __init__(self, port: str, baud_rate: int = 115200, timeout: float = 2.0):
        self.port      = port
        self.baud_rate = baud_rate
        self.timeout   = timeout
        self._serial: Optional[serial.Serial] = None
        self._seq = 0

    def connect(self):
        self._serial = serial.Serial(
            port=self.port, baudrate=self.baud_rate, timeout=self.timeout
        )
        time.sleep(0.1)

    def disconnect(self):
        if self._serial and self._serial.is_open:
            self._serial.close()

    def cleanup(self):
        self.disconnect()

    # -- Checksum -----------------------------------------------------
    @staticmethod
    def _checksum(type_: int, seq: int, payload: bytes) -> int:
        csum = PROTO_START ^ type_ ^ seq ^ len(payload)
        for b in payload:
            csum ^= b
        return csum & 0xFF

    # -- Send ---------------------------------------------------------
    def _build_packet(self, type_: int, payload: bytes) -> bytes:
        seq  = self._seq & 0xFF
        self._seq += 1
        csum = self._checksum(type_, seq, payload)
        return bytes([PROTO_START, type_, seq, len(payload)]) + payload + bytes([csum, PROTO_END])

    def send(self, data: Any):
        """
        Send data. Accepts:
          str        -> STRING packet
          int        -> INT packet
          float      -> FLOAT packet
          list[int]  -> ARRAY packet
          list[float]-> ARRAY packet
          dict       -> DICT packet (values must be str, int, or float)
        """
        if isinstance(data, str):
            payload = data.encode("utf-8")
            type_   = PROTO_TYPE_STRING

        elif isinstance(data, bool):
            # bool is a subclass of int -- handle explicitly
            payload = struct.pack("<i", int(data))
            type_   = PROTO_TYPE_INT

        elif isinstance(data, int):
            payload = struct.pack("<i", data)
            type_   = PROTO_TYPE_INT

        elif isinstance(data, float):
            payload = struct.pack("<f", data)
            type_   = PROTO_TYPE_FLOAT

        elif isinstance(data, list):
            payload = self._encode_array(data)
            type_   = PROTO_TYPE_ARRAY

        elif isinstance(data, dict):
            payload = self._encode_dict(data)
            type_   = PROTO_TYPE_DICT

        else:
            raise TypeError(f"Unsupported type: {type(data)}")

        self._serial.write(self._build_packet(type_, payload))

    def _encode_array(self, lst: list) -> bytes:
        if not lst:
            raise ValueError("Cannot send empty array")
        # Infer type from first element
        if isinstance(lst[0], float):
            elem_type = PROTO_TYPE_FLOAT
            packed    = b"".join(struct.pack("<f", v) for v in lst)
        elif isinstance(lst[0], int):
            elem_type = PROTO_TYPE_INT
            packed    = b"".join(struct.pack("<i", v) for v in lst)
        else:
            raise TypeError("Array elements must be int or float")
        return bytes([elem_type, len(lst)]) + packed

    def _encode_dict(self, d: dict) -> bytes:
        buf = bytes([len(d)])
        for key, val in d.items():
            key_bytes = key.encode("utf-8")[:15]
            buf += bytes([len(key_bytes)]) + key_bytes
            if isinstance(val, float):
                buf += bytes([PROTO_TYPE_FLOAT]) + struct.pack("<f", val)
            elif isinstance(val, int):
                buf += bytes([PROTO_TYPE_INT]) + struct.pack("<i", val)
            elif isinstance(val, str):
                val_bytes = val.encode("utf-8")[:31]
                buf += bytes([PROTO_TYPE_STRING, len(val_bytes)]) + val_bytes
            else:
                raise TypeError(f"Dict value type not supported: {type(val)}")
        return buf

    # -- Receive ------------------------------------------------------
    def receive(self) -> Packet:
        # Sync to START byte
        while True:
            b = self._serial.read(1)
            if not b:
                raise ProtocolFramingError("Timeout waiting for START byte")
            if b[0] == PROTO_START:
                break

        header = self._serial.read(3)
        if len(header) < 3:
            raise ProtocolLengthError("Incomplete header")

        type_, seq, length = header[0], header[1], header[2]

        tail = self._serial.read(length + 2)
        if len(tail) < length + 2:
            raise ProtocolLengthError("Incomplete packet body")

        payload  = tail[:length]
        checksum = tail[length]
        end_byte = tail[length + 1]

        if end_byte != PROTO_END:
            raise ProtocolFramingError(f"Bad END byte: 0x{end_byte:02X}")

        if checksum != self._checksum(type_, seq, payload):
            raise ProtocolChecksumError("Checksum mismatch")

        return Packet(type_=type_, seq=seq, payload=payload)

    # -- Context manager -----------------------------------------------
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.cleanup()
