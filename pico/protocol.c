#include "protocol.h"
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include <string.h>
#include <stdio.h>

static uint8_t _seq = 0;

// ─── Init ────────────────────────────────────────────────────────────
void protocol_init(uint32_t baud_rate) {
    stdio_usb_init();
    sleep_ms(2000);
    (void)baud_rate;
}

// ─── Checksum ────────────────────────────────────────────────────────
uint8_t protocol_checksum(const proto_packet_t *packet) {
    uint8_t csum = 0;
    csum ^= packet->start;
    csum ^= packet->type;
    csum ^= packet->seq;
    csum ^= packet->length;
    for (int i = 0; i < packet->length; i++) csum ^= packet->payload[i];
    return csum;
}

// ─── Encode ──────────────────────────────────────────────────────────
int protocol_encode(const proto_packet_t *packet, uint8_t *buf, size_t buf_size) {
    size_t total = 6 + packet->length;
    if (buf_size < total) return PROTO_ERR_LENGTH;
    int i = 0;
    buf[i++] = packet->start;
    buf[i++] = packet->type;
    buf[i++] = packet->seq;
    buf[i++] = packet->length;
    memcpy(&buf[i], packet->payload, packet->length);
    i += packet->length;
    buf[i++] = packet->checksum;
    buf[i++] = packet->end;
    return (int)total;
}

// ─── Decode ──────────────────────────────────────────────────────────
int protocol_decode(const uint8_t *buf, size_t buf_size, proto_packet_t *packet) {
    if (buf_size < 6)           return PROTO_ERR_LENGTH;
    if (buf[0] != PROTO_START)  return PROTO_ERR_FRAMING;
    packet->start  = buf[0];
    packet->type   = buf[1];
    packet->seq    = buf[2];
    packet->length = buf[3];
    size_t total = 6 + packet->length;
    if (buf_size < total)            return PROTO_ERR_LENGTH;
    if (buf[total-1] != PROTO_END)   return PROTO_ERR_FRAMING;
    memcpy(packet->payload, &buf[4], packet->length);
    packet->checksum = buf[4 + packet->length];
    packet->end      = buf[total - 1];
    if (protocol_checksum(packet) != packet->checksum) return PROTO_ERR_CHECKSUM;
    return PROTO_OK;
}

// ─── Send / Receive ──────────────────────────────────────────────────
int protocol_send(const proto_packet_t *packet) {
    uint8_t buf[6 + PROTO_MAX_PAYLOAD];
    int len = protocol_encode(packet, buf, sizeof(buf));
    if (len < 0) return len;
    for (int i = 0; i < len; i++) putchar_raw(buf[i]);
    return len;
}

int protocol_receive(proto_packet_t *packet) {
    uint8_t buf[6 + PROTO_MAX_PAYLOAD];
    int idx = 0;
    while (true) {
        int c = getchar_timeout_us(1000000);
        if (c == PICO_ERROR_TIMEOUT) continue;
        if ((uint8_t)c == PROTO_START) { buf[idx++] = (uint8_t)c; break; }
    }
    for (int i = 0; i < 3; i++) {
        int c = getchar_timeout_us(1000000);
        if (c == PICO_ERROR_TIMEOUT) return PROTO_ERR_FRAMING;
        buf[idx++] = (uint8_t)c;
    }
    uint8_t length = buf[3];
    for (int i = 0; i < length + 2; i++) {
        int c = getchar_timeout_us(1000000);
        if (c == PICO_ERROR_TIMEOUT) return PROTO_ERR_FRAMING;
        buf[idx++] = (uint8_t)c;
    }
    return protocol_decode(buf, idx, packet);
}

// ─── Primitive Helpers ───────────────────────────────────────────────
int protocol_send_string(const char *str) {
    proto_packet_t pkt;
    pkt.start  = PROTO_START;
    pkt.type   = PROTO_TYPE_STRING;
    pkt.seq    = _seq++;
    pkt.length = (uint8_t)strnlen(str, PROTO_MAX_PAYLOAD);
    memcpy(pkt.payload, str, pkt.length);
    pkt.checksum = protocol_checksum(&pkt);
    pkt.end      = PROTO_END;
    return protocol_send(&pkt);
}

int protocol_send_int(int32_t value) {
    proto_packet_t pkt;
    pkt.start  = PROTO_START;
    pkt.type   = PROTO_TYPE_INT;
    pkt.seq    = _seq++;
    pkt.length = sizeof(int32_t);
    memcpy(pkt.payload, &value, sizeof(int32_t));
    pkt.checksum = protocol_checksum(&pkt);
    pkt.end      = PROTO_END;
    return protocol_send(&pkt);
}

int protocol_send_float(float value) {
    proto_packet_t pkt;
    pkt.start  = PROTO_START;
    pkt.type   = PROTO_TYPE_FLOAT;
    pkt.seq    = _seq++;
    pkt.length = sizeof(float);
    memcpy(pkt.payload, &value, sizeof(float));
    pkt.checksum = protocol_checksum(&pkt);
    pkt.end      = PROTO_END;
    return protocol_send(&pkt);
}

// ─── Array Encoding ──────────────────────────────────────────────────
//
// Array payload format:
//   [element_type 1B] [count 1B] [element_0] [element_1] ...
//
// Each element for INT/FLOAT is 4 bytes (little-endian).
// String arrays are not supported in the helpers (add if needed).

int protocol_send_int_array(const int32_t *values, uint8_t count) {
    if (count > PROTO_MAX_ARRAY_ELEMENTS) return PROTO_ERR_LENGTH;
    proto_packet_t pkt;
    pkt.start = PROTO_START;
    pkt.type  = PROTO_TYPE_ARRAY;
    pkt.seq   = _seq++;
    uint8_t *p = pkt.payload;
    *p++ = PROTO_TYPE_INT;  // element type
    *p++ = count;
    for (int i = 0; i < count; i++) {
        memcpy(p, &values[i], sizeof(int32_t));
        p += sizeof(int32_t);
    }
    pkt.length   = (uint8_t)(p - pkt.payload);
    pkt.checksum = protocol_checksum(&pkt);
    pkt.end      = PROTO_END;
    return protocol_send(&pkt);
}

int protocol_send_float_array(const float *values, uint8_t count) {
    if (count > PROTO_MAX_ARRAY_ELEMENTS) return PROTO_ERR_LENGTH;
    proto_packet_t pkt;
    pkt.start = PROTO_START;
    pkt.type  = PROTO_TYPE_ARRAY;
    pkt.seq   = _seq++;
    uint8_t *p = pkt.payload;
    *p++ = PROTO_TYPE_FLOAT;
    *p++ = count;
    for (int i = 0; i < count; i++) {
        memcpy(p, &values[i], sizeof(float));
        p += sizeof(float);
    }
    pkt.length   = (uint8_t)(p - pkt.payload);
    pkt.checksum = protocol_checksum(&pkt);
    pkt.end      = PROTO_END;
    return protocol_send(&pkt);
}

// ─── Dict Encoding ───────────────────────────────────────────────────
//
// Dict payload format:
//   [count 1B]
//   For each entry:
//     [key_len 1B] [key bytes] [value_type 1B] [value bytes]
//
// Value bytes: 4B for INT/FLOAT, (1B len + N bytes) for STRING.

int protocol_send_dict(const proto_entry_t *entries, uint8_t count) {
    if (count > PROTO_MAX_DICT_ENTRIES) return PROTO_ERR_LENGTH;
    proto_packet_t pkt;
    pkt.start = PROTO_START;
    pkt.type  = PROTO_TYPE_DICT;
    pkt.seq   = _seq++;
    uint8_t *p = pkt.payload;
    *p++ = count;
    for (int i = 0; i < count; i++) {
        const proto_entry_t *e = &entries[i];
        uint8_t key_len = (uint8_t)strnlen(e->key, PROTO_MAX_KEY_LEN);
        *p++ = key_len;
        memcpy(p, e->key, key_len);
        p += key_len;
        *p++ = e->value.type;
        if (e->value.type == PROTO_TYPE_INT) {
            memcpy(p, &e->value.value.i, sizeof(int32_t));
            p += sizeof(int32_t);
        } else if (e->value.type == PROTO_TYPE_FLOAT) {
            memcpy(p, &e->value.value.f, sizeof(float));
            p += sizeof(float);
        } else if (e->value.type == PROTO_TYPE_STRING) {
            uint8_t slen = (uint8_t)strnlen(e->value.value.s, 31);
            *p++ = slen;
            memcpy(p, e->value.value.s, slen);
            p += slen;
        }
    }
    pkt.length   = (uint8_t)(p - pkt.payload);
    pkt.checksum = protocol_checksum(&pkt);
    pkt.end      = PROTO_END;
    return protocol_send(&pkt);
}

// ─── Dict Entry Builders ─────────────────────────────────────────────
proto_entry_t proto_entry_int(const char *key, int32_t value) {
    proto_entry_t e;
    strncpy(e.key, key, PROTO_MAX_KEY_LEN);
    e.key[PROTO_MAX_KEY_LEN] = '\0';
    e.value.type    = PROTO_TYPE_INT;
    e.value.value.i = value;
    return e;
}

proto_entry_t proto_entry_float(const char *key, float value) {
    proto_entry_t e;
    strncpy(e.key, key, PROTO_MAX_KEY_LEN);
    e.key[PROTO_MAX_KEY_LEN] = '\0';
    e.value.type    = PROTO_TYPE_FLOAT;
    e.value.value.f = value;
    return e;
}

proto_entry_t proto_entry_string(const char *key, const char *str) {
    proto_entry_t e;
    strncpy(e.key, key, PROTO_MAX_KEY_LEN);
    e.key[PROTO_MAX_KEY_LEN] = '\0';
    e.value.type = PROTO_TYPE_STRING;
    strncpy(e.value.value.s, str, 31);
    e.value.value.s[31] = '\0';
    return e;
}
