idf_component_register(SRCS "main.c" INCLUDE_DIRS "." "../../../main"
                       REQUIRES board_logic esp_driver_gpio freertos)
