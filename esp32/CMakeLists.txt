cmake_minimum_required(VERSION 3.16)
set(IDF_TARGET "esp32c5" CACHE STRING "FireBeetle 2 ESP32-C5")
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/main")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
set(COMPONENTS main)
project(scb_esp32c5)
if(NOT IDF_TARGET STREQUAL "esp32c5")
    message(FATAL_ERROR "Use idf.py set-target esp32c5 for the DFR1222 board")
endif()
if("${IDF_VERSION_MAJOR}.${IDF_VERSION_MINOR}.${IDF_VERSION_PATCH}" VERSION_LESS "5.5.3")
    message(FATAL_ERROR "Use ESP-IDF 5.5.3 or newer; this project is validated with 5.5.3")
endif()
idf_build_get_property(scb_elf EXECUTABLE)
find_program(scb_size_tool NAMES riscv32-esp-elf-size REQUIRED)
add_custom_command(TARGET ${scb_elf} POST_BUILD
    COMMAND ${PYTHON} "${CMAKE_CURRENT_LIST_DIR}/scripts/ram_budget.py"
        --elf "$<TARGET_FILE:${scb_elf}>" --size-tool "${scb_size_tool}"
    VERBATIM)
