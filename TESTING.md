# Testing Documentation

**Project:** Custom Communication Protocol -- Raspberry Pi Pico <-> PC  
**Scope:** Unit tests, hardware-in-the-loop tests, and error-injection tests  
**Test files:** `pc/test_protocol.py` (unit), `pc/test_protocol_hardware.py` (hardware)

---

## Overview

Testing is structured in three layers:

1. **Unit tests** (`test_protocol.py`) -- validate encode/decode logic in isolation, no hardware required
2. **Hardware-in-the-loop tests** (`test_protocol_hardware.py`) -- verify end-to-end packet transmission over a live USB serial connection using dedicated test firmware
3. **Error-injection tests** -- confirm correct error handling under corrupted or malformed input

---

## Running the Unit Tests

No Pico or serial port required.

```bash
cd pc
pip install pyserial    # only required once
python test_protocol.py
```

---

## Running the Hardware Tests

### Step 1 -- Build the test firmware

```bash
cd pico
mkdir -p build && cd build
cmake ..
make custom_protocol_test
```

This produces `custom_protocol_test.uf2` alongside the normal `custom_protocol.uf2`.

### Step 2 -- Flash the Pico

Hold **BOOTSEL**, plug in the Pico, then drag `custom_protocol_test.uf2` onto the drive.

### Step 3 -- Run the test runner

```bash
cd pc
python test_protocol_hardware.py --port /dev/tty.usbmodem101   # Mac
python test_protocol_hardware.py --port /dev/ttyACM0           # Linux
python test_protocol_hardware.py --port COM3                   # Windows
```

After opening the port, the runner immediately sends a single ACK byte (`0x06`). The Pico waits for this byte before transmitting anything, guaranteeing the PC is reading before the first packet arrives regardless of how long USB enumeration takes. The Pico then transmits its 29-packet sequence and halts, with the onboard LED blinking rapidly to confirm completion. The runner checks each packet's type, SEQ number, and value, then prints a per-packet result table and a final summary. Exit code is `0` on full pass, `1` on any failure.

### Expected output

```
Connecting to /dev/ttyACM0 at 115200 baud ...
Connected. Waiting for 29 packets ...

  SEQ  TYPE      RESULT  DESCRIPTION
  ---  ----      ------  ---------------------------------------
  000  STRING    PASS  STRING "Hello from Pico!"
  001  STRING    PASS  STRING "" (empty)
  002  INT       PASS  INT 0
  003  INT       PASS  INT 1
  004  INT       PASS  INT -1
  005  INT       PASS  INT INT32_MAX (2147483647)
  006  INT       PASS  INT INT32_MIN (-2147483648)
  007  FLOAT     PASS  FLOAT 0.0
  008  FLOAT     PASS  FLOAT 3.14
  009  FLOAT     PASS  FLOAT -273.15
  010  FLOAT     PASS  FLOAT 1.0e20
  011  ARRAY     PASS  ARRAY INT [1, -2, 300, -400, 0]
  012  ARRAY     PASS  ARRAY INT [2147483647] (single element)
  013  ARRAY     PASS  ARRAY FLOAT [18.0, 19.2, 20.4, 21.6, 22.8]
  014  ARRAY     PASS  ARRAY FLOAT [0.0] (single element)
  015  DICT      PASS  DICT {temp:22.5, uptime:42, status:"OK"}
  016  DICT      PASS  DICT {a:1 ... p:16} (16 entries, maximum size)
  017  STRING    PASS  STRING special ASCII "!"#$%&'()*+,-./"
  018  INT       PASS  INT 42 (seq continuity check)
  019  FLOAT     PASS  FLOAT 42.0 (seq continuity check)
  020  STRING    PASS  STRING "PACKET_20" (rapid-fire burst)
  ...
  028  STRING    PASS  STRING "__DONE__" (sentinel)

  =======================================================
  Results: 29/29 passed  -- all tests passed PASS
  =======================================================
```

---

## Hardware Test -- Packet Sequence

The test firmware (`main_test.c`) sends the following fixed sequence. The SEQ numbers are assigned by the static counter in `protocol.c` in call order and must not be reordered.

| SEQ | Type | Value | Purpose |
|-----|------|-------|---------|
| 00 | STRING | `"Hello from Pico!"` | Nominal string |
| 01 | STRING | `""` | Empty string (zero-length payload) |
| 02 | INT | `0` | Integer zero |
| 03 | INT | `1` | Positive integer |
| 04 | INT | `-1` | Negative integer |
| 05 | INT | `2147483647` | INT32_MAX boundary |
| 06 | INT | `-2147483648` | INT32_MIN boundary |
| 07 | FLOAT | `0.0` | Float zero |
| 08 | FLOAT | `3.14` | Positive float |
| 09 | FLOAT | `-273.15` | Negative float |
| 10 | FLOAT | `1.0e20` | Large float |
| 11 | ARRAY INT | `[1, -2, 300, -400, 0]` | Mixed-sign integer array |
| 12 | ARRAY INT | `[2147483647]` | Single-element array |
| 13 | ARRAY FLOAT | `[18.0, 19.2, 20.4, 21.6, 22.8]` | Float array |
| 14 | ARRAY FLOAT | `[0.0]` | Single-element float array |
| 15 | DICT | `{temp:22.5, uptime:42, status:"OK"}` | Mixed-type dict |
| 16 | DICT | `{a:1 ... p:16}` | Maximum dict size (16 entries) |
| 17 | STRING | `"!\"#$%&'()*+,-./"` | Special ASCII characters |
| 18 | INT | `42` | SEQ continuity check |
| 19 | FLOAT | `42.0` | SEQ continuity check |
| 20-27 | STRING | `"PACKET_20"` ... `"PACKET_27"` | Rapid-fire burst (8 packets) |
| 28 | STRING | `"__DONE__"` | Sentinel -- runner stops |

---

## 1. Unit Tests -- `test_protocol.py`

### 1.1 Packet Framing

| # | Test | Result |
|---|------|--------|
| 1.1.1 | START byte is `0xAA` | PASS |
| 1.1.2 | END byte is `0xFF` | PASS |
| 1.1.3 | LENGTH field matches payload size | PASS |
| 1.1.4 | Total packet size equals `6 + len(payload)` | PASS |
| 1.1.5 | Empty payload (`LENGTH=0`) frames correctly | PASS |
| 1.1.6 | Maximum payload (`LENGTH=255`) frames correctly | PASS |
| 1.1.7 | SEQ field is stored in decoded packet | PASS |

### 1.2 Checksum

| # | Test | Result |
|---|------|--------|
| 1.2.1 | Valid packet passes checksum | PASS |
| 1.2.2 | Corrupted payload byte raises `ProtocolChecksumError` | PASS |
| 1.2.3 | Corrupted TYPE byte raises `ProtocolChecksumError` | PASS |
| 1.2.4 | Corrupted SEQ byte raises `ProtocolChecksumError` | PASS |
| 1.2.5 | Checksum equals XOR of all header and payload bytes | PASS |
| 1.2.6 | Wrong END byte raises `ProtocolFramingError` | PASS |

### 1.3 Primitive Encode / Decode

| # | Test | Result |
|---|------|--------|
| 1.3.1 | String roundtrip | PASS |
| 1.3.2 | UTF-8 string roundtrip | PASS |
| 1.3.3 | Positive integer roundtrip | PASS |
| 1.3.4 | Negative integer roundtrip | PASS |
| 1.3.5 | Zero integer roundtrip | PASS |
| 1.3.6 | `INT32_MAX` roundtrip | PASS |
| 1.3.7 | `INT32_MIN` roundtrip | PASS |
| 1.3.8 | Float roundtrip (pi ~ 3.14) | PASS |
| 1.3.9 | Negative float roundtrip | PASS |
| 1.3.10 | Zero float roundtrip | PASS |

### 1.4 Array Encode / Decode

| # | Test | Result |
|---|------|--------|
| 1.4.1 | Integer array roundtrip (5 elements) | PASS |
| 1.4.2 | Float array roundtrip (5 elements) | PASS |
| 1.4.3 | Single-element array roundtrip | PASS |
| 1.4.4 | COUNT field reflects element count | PASS |
| 1.4.5 | Truncated payload raises `ProtocolLengthError` | PASS |
| 1.4.6 | Unsupported element type raises `ProtocolLengthError` | PASS |
| 1.4.7 | Missing COUNT byte raises `ProtocolLengthError` | PASS |

### 1.5 Dict Encode / Decode

| # | Test | Result |
|---|------|--------|
| 1.5.1 | Dict with integer values roundtrip | PASS |
| 1.5.2 | Dict with float values roundtrip | PASS |
| 1.5.3 | Dict with string values roundtrip | PASS |
| 1.5.4 | Dict with mixed value types roundtrip | PASS |
| 1.5.5 | Empty dict (0 entries) decodes to `{}` | PASS |
| 1.5.6 | Key at maximum length (15 characters) decodes correctly | PASS |
| 1.5.7 | Completely empty payload raises `ProtocolLengthError` | PASS |

### 1.6 PC-Side Encoding (`CustomProtocol`)

| # | Test | Result |
|---|------|--------|
| 1.6.1 | `_build_packet` sets TYPE byte correctly | PASS |
| 1.6.2 | `_build_packet` encodes INT payload correctly | PASS |
| 1.6.3 | Sequence number increments with each packet | PASS |
| 1.6.4 | Sequence number wraps from 255 to 0 | PASS |
| 1.6.5 | `_encode_array` infers INT type from first element | PASS |
| 1.6.6 | `_encode_array` infers FLOAT type from first element | PASS |
| 1.6.7 | `_encode_array([])` raises `ValueError` | PASS |
| 1.6.8 | `_encode_dict` with mixed types roundtrips correctly | PASS |

### 1.7 Error and Edge Cases

| # | Test | Result |
|---|------|--------|
| 1.7.1 | `bool True` encodes as INT value `1` | PASS |
| 1.7.2 | Unknown packet type returns raw bytes | PASS |
| 1.7.3 | `Packet.__repr__` includes type name, SEQ, and value | PASS |
| 1.7.4 | `Packet.__repr__` shows hex notation for unknown type | PASS |
| 1.7.5 | Checksum with single-byte payload returns a valid byte | PASS |
| 1.7.6 | Checksum with empty payload equals XOR of header fields only | PASS |

**Unit test summary: 51 / 51 passed.**

---

## 2. Integration Tests -- Pico <-> PC over USB Serial

The following tests were conducted with `main.c` (normal firmware) flashed on the Pico,
transmitting a string, integer, float, two arrays, and a dict snapshot on a 1-second cycle.

### 2.1 Normal Reception

- Ran `demo_receive.py` for 60 seconds (60 complete cycles, 360 packets total)
- Zero checksum errors, zero framing errors, zero dropped packets

### 2.2 Sequence Continuity

- Monitored the SEQ field across a 500-packet run
- No gaps or out-of-order values observed
- Sequence wrapped correctly from 255 -> 0

### 2.3 Reconnect After Cable Pull

- USB cable disconnected mid-transfer; reconnected after 5 seconds
- Receiver re-synced cleanly on the next `0xAA` START byte
- No crash, hang, or assertion failure observed

---

## 3. Error-Injection Tests

### 3.1 Corrupted Checksum

**Method:** Modified `protocol.c` to XOR the checksum byte with `0x01` before sending.  
**Expected:** `ProtocolChecksumError` raised for every packet.  
**Actual:** PASS Error raised and logged correctly for all packets.

### 3.2 Missing END Byte

**Method:** Modified `protocol.c` to transmit `0x00` in place of the `0xFF` END byte.  
**Expected:** `ProtocolFramingError` raised.  
**Actual:** PASS Error raised and logged correctly.

### 3.3 Empty Payload (`LENGTH=0`)

**Method:** Sent a packet with a zero-length payload from the Pico.  
**Expected:** Both encode and decode handle the packet without error.  
**Actual:** PASS Handled correctly on both sides.

### 3.4 Maximum Payload (`LENGTH=255`)

**Method:** Sent a 255-byte string of repeated `'A'` characters.  
**Expected:** Packet received and decoded correctly on the PC.  
**Actual:** PASS Received and decoded without error.

---

## 4. Challenges and Resolutions

| Challenge | Resolution |
|-----------|------------|
| USB serial takes ~2 s to enumerate on Pico boot | Added `sleep_ms(2000)` in `protocol_init()` |
| Pico transmits before PC is reading, dropping early packets | Pico waits for ACK byte (`0x06`) from PC before sending; runner writes it immediately after opening the port |
| Python `read()` blocking indefinitely on timeout | Set `timeout=2.0` in `serial.Serial()` (10 s for hardware tests) |
| Receiver desyncing on mid-stream corruption | Receive loop always scans forward to the next `0xAA` START byte |
| Test firmware SEQ counter must match PC expectations exactly | Packet sequence in `main_test.c` is the sole source of truth; helpers are called in a fixed order and never reordered |
