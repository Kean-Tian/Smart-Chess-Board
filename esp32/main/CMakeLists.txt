idf_component_register(
    SRCS "app_main.c" "scb_core.c"
    INCLUDE_DIRS "."
    REQUIRES board_logic esp_driver_gpio esp_driver_rmt esp_driver_uart esp_timer
)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
