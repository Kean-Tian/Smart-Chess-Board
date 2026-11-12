idf_component_register(SRCS "app_main.c" "motor_bench.c" INCLUDE_DIRS "."
                       REQUIRES motor_control esp_driver_gpio esp_driver_uart esp_timer)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
