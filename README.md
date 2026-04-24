# Custom Communication Protocol

A binary serial protocol for sending typed data between a Raspberry Pi Pico and a PC over USB.

---

## Packet Structure

```
[0xAA] [TYPE] [SEQ] [LENGTH] [PAYLOAD...] [CHECKSUM] [0xFF]
```

| Field | Size | Purpose |
|-------|------|---------|
| START `0xAA` | 1B | Marks the start of a packet |
| TYPE | 1B | Data type: `0x01`=string `0x02`=int `0x03`=float `0x04`=array `0x05`=dict |
| SEQ | 1B | Sequence number (0–255, wraps) |
| LENGTH | 1B | Payload size in bytes |
| PAYLOAD | N bytes | The data |
| CHECKSUM | 1B | XOR of all preceding bytes |
| END `0xFF` | 1B | Marks the end of a packet |

---

## Project Structure

```
project/
├── README.md
├── TESTING.md
├── pico/
│   ├── protocol.h
│   ├── protocol.c
│   ├── main.c
│   └── CMakeLists.txt
└── pc/
    ├── protocol.py
    ├── demo_receive.py
    └── demo_send.py
```

---

## Setup

### Pico

Requires the [Pico SDK](https://github.com/raspberrypi/pico-sdk) and `cmake`.

```bash
cd pico
mkdir build && cd build
cmake ..
make
```

Hold **BOOTSEL**, plug in the Pico, then drag `custom_protocol.uf2` onto the drive.

### PC

```bash
pip install pyserial
```

Find your port:
- **Mac:** `ls /dev/tty.*` → usually `/dev/tty.usbmodem101`
- **Linux:** `ls /dev/ttyACM*` → usually `/dev/ttyACM0`
- **Windows:** Device Manager → Ports → usually `COM3`

---

## Running

```bash
python demo_receive.py --port /dev/tty.usbmodem101
```

Expected output:
```
[SEQ 000] Packet(type=STRING, seq=0,  value='Hello from Pico!')
[SEQ 001] Packet(type=INT,    seq=1,  value=0)
[SEQ 002] Packet(type=FLOAT,  seq=2,  value=20.0)
[SEQ 003] ARRAY  (5 elements): [18.0, 19.2, 20.4, 21.6, 22.8]
[SEQ 004] ARRAY  (4 elements): [0, 0, 0, 0]
[SEQ 005] DICT   (4 keys):
           temp: 22.5
           humidity: 55.0
           uptime: 0
           status: OK
```

---

## Error Handling

| Error | Cause | Action |
|-------|-------|--------|
| `FramingError` | Bad START/END byte | Logged, re-syncs to next `0xAA` |
| `ChecksumError` | Corrupted byte | Logged, packet discarded |
| `LengthError` | Timeout mid-packet | Logged, re-syncs |
