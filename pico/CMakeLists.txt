cmake_minimum_required(VERSION 3.13)

# Pull in the Pico SDK (set PICO_SDK_PATH in your environment)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(custom_protocol C CXX ASM)
set(CMAKE_C_STANDARD 11)

pico_sdk_init()

# -- Normal firmware -----------------------------------------------------------
add_executable(custom_protocol
    main.c
    protocol.c
)

pico_enable_stdio_usb(custom_protocol 1)
pico_enable_stdio_uart(custom_protocol 0)

target_link_libraries(custom_protocol
    pico_stdlib
)

pico_add_extra_outputs(custom_protocol)

# -- Hardware-in-the-loop test firmware ---------------------------------------
# Produces custom_protocol_test.uf2
# Flash this instead of custom_protocol.uf2, then run:
#   python pc/test_protocol_hardware.py --port <port>

add_executable(custom_protocol_test
    main_test.c
    protocol.c
)

pico_enable_stdio_usb(custom_protocol_test 1)
pico_enable_stdio_uart(custom_protocol_test 0)

target_link_libraries(custom_protocol_test
    pico_stdlib
)

pico_add_extra_outputs(custom_protocol_test)
