idf_component_register(SRCS "app_main.c" "motor_bench.c" INCLUDE_DIRS "." "../../../main"
                       REQUIRES motor_control esp_driver_gpio scb_transport esp_timer)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
