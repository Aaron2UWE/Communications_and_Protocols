cmake_minimum_required(VERSION 3.13)

# Pull in the Pico SDK (set PICO_SDK_PATH in your environment)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(custom_protocol C CXX ASM)
set(CMAKE_C_STANDARD 11)

pico_sdk_init()

add_executable(custom_protocol
    main.c
    protocol.c
)

# Enable USB serial, disable UART stdio
pico_enable_stdio_usb(custom_protocol 1)
pico_enable_stdio_uart(custom_protocol 0)

target_link_libraries(custom_protocol
    pico_stdlib
)

pico_add_extra_outputs(custom_protocol)
