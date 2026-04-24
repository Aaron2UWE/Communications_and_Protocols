/*
 * main_test.c -- Hardware-in-the-loop test firmware for the Raspberry Pi Pico.
 *
 * Flash custom_protocol_test.uf2 instead of the normal firmware, then run:
 *
 *   python pc/test_protocol_hardware.py --port <port>
 *
 * Handshake
 * ---------
 * After USB enumeration the Pico spins waiting for a single ACK byte (0x06)
 * from the PC. The test runner sends it immediately after opening the port.
 * This guarantees the PC is reading before the first packet is transmitted,
 * regardless of how long USB enumeration takes.
 *
 * The Pico transmits a fixed, deterministic sequence of 29 packets and then
 * sends a "__DONE__" sentinel string. The PC asserts the type, SEQ number,
 * and value of every packet exactly. SEQ numbers are assigned by the static
 * counter inside protocol.c in the order the send helpers are called, so the
 * sequence below is the ground truth -- do not reorder.
 *
 * Packet sequence
 * ---------------
 *  SEQ 00  STRING  "Hello from Pico!"
 *  SEQ 01  STRING  ""                          (empty string)
 *  SEQ 02  INT     0
 *  SEQ 03  INT     1
 *  SEQ 04  INT     -1
 *  SEQ 05  INT     2147483647                  (INT32_MAX)
 *  SEQ 06  INT     -2147483648                 (INT32_MIN)
 *  SEQ 07  FLOAT   0.0
 *  SEQ 08  FLOAT   3.14
 *  SEQ 09  FLOAT   -273.15
 *  SEQ 10  FLOAT   1.0e20
 *  SEQ 11  ARRAY   INT   [1, -2, 300, -400, 0]
 *  SEQ 12  ARRAY   INT   [2147483647]           (single element)
 *  SEQ 13  ARRAY   FLOAT [18.0, 19.2, 20.4, 21.6, 22.8]
 *  SEQ 14  ARRAY   FLOAT [0.0]                  (single element)
 *  SEQ 15  DICT    {temp:22.5, uptime:42, status:"OK"}
 *  SEQ 16  DICT    {a:1 ... p:16}               (16 entries, maximum size)
 *  SEQ 17  STRING  "!\"#$%&'()*+,-./"           (special ASCII characters)
 *  SEQ 18  INT     42                            (seq continuity check)
 *  SEQ 19  FLOAT   42.0                          (seq continuity check)
 *  SEQ 20  STRING  "PACKET_20"  \
 *  SEQ 21  STRING  "PACKET_21"   |
 *  SEQ 22  STRING  "PACKET_22"   |
 *  SEQ 23  STRING  "PACKET_23"   | rapid-fire burst
 *  SEQ 24  STRING  "PACKET_24"   |
 *  SEQ 25  STRING  "PACKET_25"   |
 *  SEQ 26  STRING  "PACKET_26"   |
 *  SEQ 27  STRING  "PACKET_27"  /
 *  SEQ 28  STRING  "__DONE__"    sentinel -- PC stops reading
 */

#include "protocol.h"
#include "pico/stdlib.h"

/* ASCII ACK -- used as the handshake byte. */
#define HANDSHAKE_BYTE 0x06

int main(void) {
    protocol_init(0);

    /* -- Handshake -------------------------------------------------- */
    /* Spin until the PC sends 0x06 (ACK). This ensures the runner is
     * connected and reading before the first packet is transmitted.   */
    while (true) {
        int c = getchar_timeout_us(100000);
        if (c == HANDSHAKE_BYTE) break;
    }

    /* -- Strings ---------------------------------------------------- */
    protocol_send_string("Hello from Pico!");   /* SEQ 00 */
    protocol_send_string("");                    /* SEQ 01 */

    /* -- Integers --------------------------------------------------- */
    protocol_send_int(0);                        /* SEQ 02 */
    protocol_send_int(1);                        /* SEQ 03 */
    protocol_send_int(-1);                       /* SEQ 04 */
    protocol_send_int(2147483647);               /* SEQ 05  INT32_MAX */
    protocol_send_int(-2147483648);              /* SEQ 06  INT32_MIN */

    /* -- Floats ----------------------------------------------------- */
    protocol_send_float(0.0f);                   /* SEQ 07 */
    protocol_send_float(3.14f);                  /* SEQ 08 */
    protocol_send_float(-273.15f);               /* SEQ 09 */
    protocol_send_float(1.0e20f);                /* SEQ 10 */

    /* -- Arrays ----------------------------------------------------- */
    {
        int32_t arr[] = {1, -2, 300, -400, 0};
        protocol_send_int_array(arr, 5);         /* SEQ 11 */
    }
    {
        int32_t arr[] = {2147483647};
        protocol_send_int_array(arr, 1);         /* SEQ 12 */
    }
    {
        float arr[] = {18.0f, 19.2f, 20.4f, 21.6f, 22.8f};
        protocol_send_float_array(arr, 5);       /* SEQ 13 */
    }
    {
        float arr[] = {0.0f};
        protocol_send_float_array(arr, 1);       /* SEQ 14 */
    }

    /* -- Dicts ------------------------------------------------------ */
    {
        proto_entry_t d[3];
        d[0] = proto_entry_float ("temp",   22.5f);
        d[1] = proto_entry_int   ("uptime", 42);
        d[2] = proto_entry_string("status", "OK");
        protocol_send_dict(d, 3);               /* SEQ 15 */
    }
    {
        proto_entry_t d[16];                    /* Maximum dict size */
        d[0]  = proto_entry_int("a",  1);
        d[1]  = proto_entry_int("b",  2);
        d[2]  = proto_entry_int("c",  3);
        d[3]  = proto_entry_int("d",  4);
        d[4]  = proto_entry_int("e",  5);
        d[5]  = proto_entry_int("f",  6);
        d[6]  = proto_entry_int("g",  7);
        d[7]  = proto_entry_int("h",  8);
        d[8]  = proto_entry_int("i",  9);
        d[9]  = proto_entry_int("j", 10);
        d[10] = proto_entry_int("k", 11);
        d[11] = proto_entry_int("l", 12);
        d[12] = proto_entry_int("m", 13);
        d[13] = proto_entry_int("n", 14);
        d[14] = proto_entry_int("o", 15);
        d[15] = proto_entry_int("p", 16);
        protocol_send_dict(d, 16);              /* SEQ 16 */
    }

    /* -- Special characters ----------------------------------------- */
    protocol_send_string("!\"#$%&'()*+,-./");   /* SEQ 17 */

    /* -- Duplicate values (sequence continuity check) -------------- */
    protocol_send_int(42);                       /* SEQ 18 */
    protocol_send_float(42.0f);                  /* SEQ 19 */

    /* -- Rapid-fire string burst ------------------------------------ */
    protocol_send_string("PACKET_20");           /* SEQ 20 */
    protocol_send_string("PACKET_21");           /* SEQ 21 */
    protocol_send_string("PACKET_22");           /* SEQ 22 */
    protocol_send_string("PACKET_23");           /* SEQ 23 */
    protocol_send_string("PACKET_24");           /* SEQ 24 */
    protocol_send_string("PACKET_25");           /* SEQ 25 */
    protocol_send_string("PACKET_26");           /* SEQ 26 */
    protocol_send_string("PACKET_27");           /* SEQ 27 */

    /* -- Sentinel --------------------------------------------------- */
    protocol_send_string("__DONE__");            /* SEQ 28 */

    /* Halt -- blink the onboard LED to confirm completion. */
    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);
    while (true) {
        gpio_put(PICO_DEFAULT_LED_PIN, 1); sleep_ms(200);
        gpio_put(PICO_DEFAULT_LED_PIN, 0); sleep_ms(200);
    }

    return 0;
}
