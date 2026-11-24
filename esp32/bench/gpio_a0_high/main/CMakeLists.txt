idf_component_register(SRCS "main.c" INCLUDE_DIRS "." "../../../main"
                       REQUIRES esp_driver_gpio scb_transport freertos)
