cmake_minimum_required(VERSION 3.13)

set(PICO_BOARD pico2 CACHE STRING "Target board")
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(scb_pico2_firmware C ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
pico_sdk_init()

add_executable(scb_pico2
    main.c
    ../src/mcu_controller.c
)
target_include_directories(scb_pico2 PRIVATE ../include)
target_link_libraries(scb_pico2 PRIVATE pico_stdlib hardware_uart)
pico_enable_stdio_usb(scb_pico2 0)
pico_enable_stdio_uart(scb_pico2 0)
pico_add_extra_outputs(scb_pico2)
