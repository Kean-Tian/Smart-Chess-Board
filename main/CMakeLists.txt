idf_component_register(SRCS "main.c" "stepper.c"
                       INCLUDE_DIRS "."
                       REQUIRES esp_driver_gpio esp_driver_gptimer)
