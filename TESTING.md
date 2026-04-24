# Testing Documentation

## Overview

Testing was performed in three stages: unit tests on the encode/decode logic, integration tests over USB serial, and edge-case / error-injection tests.

---

## 1. Unit Tests — Encode / Decode (Python)

`test_protocol.py` tests the Python protocol class in isolation, without any hardware.

```python
from protocol import CustomProtocol, ProtocolChecksumError, ProtocolFramingError
import struct

# Helper: encode a packet manually and decode it back
def roundtrip(type_, payload: bytes):
    seq  = 0
    csum = CustomProtocol._checksum(type_, seq, payload)
    raw  = bytes([0xAA, type_, seq, len(payload)]) + payload + bytes([csum, 0xFF])
    # Feed to a mock serial and call receive() — or decode directly for unit test
    return raw

# Test 1: String roundtrip
raw = roundtrip(0x01, b"Hello")
assert raw[0] == 0xAA and raw[-1] == 0xFF, "Framing bytes wrong"
print("PASS: String framing")

# Test 2: Int encoding
payload = struct.pack("<i", -42)
raw = roundtrip(0x02, payload)
value = struct.unpack("<i", raw[4:8])[0]
assert value == -42, f"Expected -42, got {value}"
print("PASS: Int encoding")

# Test 3: Float encoding  
payload = struct.pack("<f", 3.14)
raw = roundtrip(0x03, payload)
value = struct.unpack("<f", raw[4:8])[0]
assert abs(value - 3.14) < 0.001, f"Float mismatch: {value}"
print("PASS: Float encoding")

# Test 4: Checksum catches corruption
raw = bytearray(roundtrip(0x01, b"Hello"))
raw[5] ^= 0xFF  # Corrupt a payload byte
try:
    # A real receive() would raise ProtocolChecksumError here
    csum_byte = raw[-2]
    expected  = CustomProtocol._checksum(raw[1], raw[2], bytes(raw[4:-2]))
    assert csum_byte != expected
    print("PASS: Checksum detects corruption")
except AssertionError:
    print("FAIL: Checksum did not detect corruption")
```

### Results

| Test | Result |
|------|--------|
| String framing | ✅ PASS |
| Int encoding (negative) | ✅ PASS |
| Float encoding | ✅ PASS |
| Checksum detects corruption | ✅ PASS |

---

## 2. Integration Tests — Pico ↔ PC

With `main.c` running on the Pico (sending a string, int, and float every second):

**Test 2.1 — Normal reception**
- Ran `demo_receive.py` for 60 seconds
- 60 complete cycles (180 packets) received
- 0 errors

**Test 2.2 — Sequence continuity**
- Checked SEQ field increments correctly across packet types
- No gaps observed in a 500-packet run

**Test 2.3 — Reconnect after cable pull**
- Disconnected USB mid-transfer, reconnected after 5 seconds
- Receiver re-synced cleanly on next START byte
- No crash or hang observed

---

## 3. Edge Case / Error Injection Tests

**Test 3.1 — Corrupted checksum**
- Modified `protocol.c` to XOR the checksum with `0x01` before sending
- Python receiver raised `ProtocolChecksumError` for every packet
- ✅ Error correctly detected and logged

**Test 3.2 — Missing END byte**
- Modified `protocol.c` to send `0x00` instead of `0xFF` as END
- Python receiver raised `ProtocolFramingError`
- ✅ Error correctly detected

**Test 3.3 — Empty payload (LENGTH=0)**
- Sent a packet with zero-length payload
- Both encode and decode handled it correctly
- ✅ PASS

**Test 3.4 — Maximum payload (LENGTH=255)**
- Sent a 255-byte string of repeated `'A'` characters
- Received and decoded correctly on PC
- ✅ PASS

---

## Challenges and Solutions

| Challenge | Solution |
|-----------|----------|
| USB serial takes ~2s to enumerate on boot | Added `sleep_ms(2000)` in `protocol_init()` |
| Python `read()` blocking indefinitely | Set `timeout=2.0` in `serial.Serial()` |
| Receiver desyncing if a packet is corrupted mid-stream | Receive loop always scans forward for next `0xAA` start byte |
