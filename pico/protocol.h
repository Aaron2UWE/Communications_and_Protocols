#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

// ─── Packet Constants ────────────────────────────────────────────────
#define PROTO_START       0xAA
#define PROTO_END         0xFF
#define PROTO_MAX_PAYLOAD 255

// ─── Data Types ──────────────────────────────────────────────────────
#define PROTO_TYPE_STRING 0x01
#define PROTO_TYPE_INT    0x02
#define PROTO_TYPE_FLOAT  0x03
#define PROTO_TYPE_ARRAY  0x04
#define PROTO_TYPE_DICT   0x05

// ─── Status Codes ────────────────────────────────────────────────────
#define PROTO_OK           0
#define PROTO_ERR_CHECKSUM -1
#define PROTO_ERR_FRAMING  -2
#define PROTO_ERR_LENGTH   -3
#define PROTO_ERR_TYPE     -4

// ─── Limits ──────────────────────────────────────────────────────────
#define PROTO_MAX_ARRAY_ELEMENTS 32
#define PROTO_MAX_DICT_ENTRIES   16
#define PROTO_MAX_KEY_LEN        15

// ─── Packet Structure ────────────────────────────────────────────────
typedef struct {
    uint8_t  start;
    uint8_t  type;
    uint8_t  seq;
    uint8_t  length;
    uint8_t  payload[PROTO_MAX_PAYLOAD];
    uint8_t  checksum;
    uint8_t  end;
} proto_packet_t;

// ─── Array Element ───────────────────────────────────────────────────
typedef struct {
    uint8_t type;
    union {
        int32_t  i;
        float    f;
        char     s[32];
    } value;
} proto_element_t;

// ─── Dict Entry ──────────────────────────────────────────────────────
typedef struct {
    char            key[PROTO_MAX_KEY_LEN + 1];
    proto_element_t value;
} proto_entry_t;

// ─── API ─────────────────────────────────────────────────────────────
void    protocol_init(uint32_t baud_rate);
int     protocol_encode(const proto_packet_t *packet, uint8_t *buf, size_t buf_size);
int     protocol_decode(const uint8_t *buf, size_t buf_size, proto_packet_t *packet);
int     protocol_send(const proto_packet_t *packet);
int     protocol_receive(proto_packet_t *packet);
uint8_t protocol_checksum(const proto_packet_t *packet);

// Primitives
int protocol_send_string(const char *str);
int protocol_send_int(int32_t value);
int protocol_send_float(float value);

// Arrays
int protocol_send_int_array(const int32_t *values, uint8_t count);
int protocol_send_float_array(const float *values, uint8_t count);

// Dicts
int           protocol_send_dict(const proto_entry_t *entries, uint8_t count);
proto_entry_t proto_entry_int(const char *key, int32_t value);
proto_entry_t proto_entry_float(const char *key, float value);
proto_entry_t proto_entry_string(const char *key, const char *str);

#endif // PROTOCOL_H
