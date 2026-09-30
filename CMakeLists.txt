cmake_minimum_required(VERSION 3.16)
project(smart_chessboard LANGUAGES C CXX)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)

FetchContent_Declare(
	libchess_source
	GIT_REPOSITORY https://github.com/kz04px/libchess.git
	GIT_TAG 71c3543da7ad64387b618e889feef5406f1ee851
)

FetchContent_GetProperties(libchess_source)
if(NOT libchess_source_POPULATED)
	FetchContent_Populate(libchess_source)
endif()

add_library(
	libchess_vendor
	${libchess_source_SOURCE_DIR}/src/attackers.cpp
	${libchess_source_SOURCE_DIR}/src/check_evasions.cpp
	${libchess_source_SOURCE_DIR}/src/checkers.cpp
	${libchess_source_SOURCE_DIR}/src/count_moves.cpp
	${libchess_source_SOURCE_DIR}/src/get_fen.cpp
	${libchess_source_SOURCE_DIR}/src/is_legal.cpp
	${libchess_source_SOURCE_DIR}/src/king_allowed.cpp
	${libchess_source_SOURCE_DIR}/src/legal_captures.cpp
	${libchess_source_SOURCE_DIR}/src/legal_moves.cpp
	${libchess_source_SOURCE_DIR}/src/legal_noncaptures.cpp
	${libchess_source_SOURCE_DIR}/src/makemove.cpp
	${libchess_source_SOURCE_DIR}/src/movegen.cpp
	${libchess_source_SOURCE_DIR}/src/perft.cpp
	${libchess_source_SOURCE_DIR}/src/pinned.cpp
	${libchess_source_SOURCE_DIR}/src/predict_hash.cpp
	${libchess_source_SOURCE_DIR}/src/set_fen.cpp
	${libchess_source_SOURCE_DIR}/src/square_attacked.cpp
	${libchess_source_SOURCE_DIR}/src/squares_attacked.cpp
	${libchess_source_SOURCE_DIR}/src/undomove.cpp
	${libchess_source_SOURCE_DIR}/src/valid.cpp
	${libchess_source_SOURCE_DIR}/src/zobrist.cpp
)
target_include_directories(libchess_vendor SYSTEM PUBLIC ${libchess_source_SOURCE_DIR}/src)
target_compile_features(libchess_vendor PUBLIC cxx_std_20)

add_library(scb_rules src/libchess_adapter.cpp)
target_include_directories(scb_rules PUBLIC include)
target_link_libraries(scb_rules PUBLIC libchess_vendor)
target_compile_options(scb_rules PRIVATE -Wall -Wextra -Wpedantic)

# Keep the original C rules core while the libchess adapter is being verified.
add_library(chess_core src/chess.c)
target_include_directories(chess_core PUBLIC include)
target_compile_options(chess_core PRIVATE -Wall -Wextra -Wpedantic)

add_executable(scb_console src/main.c)
target_link_libraries(scb_console PRIVATE scb_rules)
set_target_properties(scb_console PROPERTIES LINKER_LANGUAGE CXX)

if(UNIX)
	add_executable(scb_pi_uart_bridge pi/src/uart_bridge.c)
	target_link_libraries(scb_pi_uart_bridge PRIVATE scb_rules)
	target_compile_options(scb_pi_uart_bridge PRIVATE -Wall -Wextra -Wpedantic)
	set_target_properties(scb_pi_uart_bridge PROPERTIES LINKER_LANGUAGE CXX)
endif()

enable_testing()
add_executable(chess_tests tests/chess_tests.c)
target_link_libraries(chess_tests PRIVATE chess_core)
add_test(NAME chess_tests COMMAND chess_tests)

add_executable(libchess_adapter_tests tests/libchess_adapter_tests.c)
target_link_libraries(libchess_adapter_tests PRIVATE scb_rules)
set_target_properties(libchess_adapter_tests PROPERTIES LINKER_LANGUAGE CXX)
add_test(NAME libchess_adapter_tests COMMAND libchess_adapter_tests)

add_library(mcu_firmware firmware/src/mcu_controller.c)
target_include_directories(mcu_firmware PUBLIC firmware/include)
target_compile_options(mcu_firmware PRIVATE -Wall -Wextra -Wpedantic)

add_executable(mcu_controller_tests firmware/tests/mcu_controller_tests.c)
target_link_libraries(mcu_controller_tests PRIVATE mcu_firmware)
add_test(NAME mcu_controller_tests COMMAND mcu_controller_tests)
