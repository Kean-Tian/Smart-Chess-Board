idf_component_register(SRCS "scb_transport.c"
    INCLUDE_DIRS "include" PRIV_INCLUDE_DIRS "../../main"
    REQUIRES esp_driver_uart esp_driver_usb_serial_jtag board_logic)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
