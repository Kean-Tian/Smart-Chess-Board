idf_component_register(SRCS "main.c" INCLUDE_DIRS "." "../../../main"
                       REQUIRES esp_driver_gpio esp_driver_uart freertos)
