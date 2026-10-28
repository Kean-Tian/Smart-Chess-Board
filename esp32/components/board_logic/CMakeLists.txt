idf_component_register(SRCS "src/sensor_matrix.c" "src/led_grid.c" INCLUDE_DIRS "include")
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
