#include "protocol.h"
#include "pico/stdlib.h"

int main(void) {
    protocol_init(0);

    int count = 0;

    while (true) {
        // ── Primitives (unchanged) ────────────────────────────────────
        protocol_send_string("Hello from Pico!");
        protocol_send_int((int32_t)count);
        protocol_send_float(20.0f + (count % 10) * 0.5f);

        // ── Array: send 5 sensor readings as floats ───────────────────
        float readings[5];
        for (int i = 0; i < 5; i++) {
            readings[i] = 18.0f + i * 1.2f + (count % 5) * 0.1f;
        }
        protocol_send_float_array(readings, 5);

        // ── Array: send 4 integers ────────────────────────────────────
        int32_t counters[4] = { count, count * 2, count * 3, count * 4 };
        protocol_send_int_array(counters, 4);

        // ── Dict: send a sensor snapshot ─────────────────────────────
        proto_entry_t snapshot[4];
        snapshot[0] = proto_entry_float("temp",     22.5f + count * 0.1f);
        snapshot[1] = proto_entry_float("humidity", 55.0f);
        snapshot[2] = proto_entry_int  ("uptime",   count);
        snapshot[3] = proto_entry_string("status",  count % 2 == 0 ? "OK" : "WARN");
        protocol_send_dict(snapshot, 4);

        count++;
        sleep_ms(1000);
    }

    return 0;
}
