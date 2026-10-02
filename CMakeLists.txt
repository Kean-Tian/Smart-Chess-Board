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
set_target_properties(libchess_vendor PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_library(scb_rules SHARED src/libchess_adapter.cpp)
target_include_directories(scb_rules PUBLIC include)
target_link_libraries(scb_rules PUBLIC libchess_vendor)
target_compile_options(scb_rules PRIVATE -Wall -Wextra -Wpedantic)

# 这部分还是 MCU 原型，目前先在电脑上检查基础逻辑能不能编译。
add_library(mcu_input_prototype STATIC firmware/pico2/input_controller.c)
target_include_directories(mcu_input_prototype PUBLIC firmware/pico2)
target_compile_options(mcu_input_prototype PRIVATE -Wall -Wextra -Wpedantic)

add_executable(scb_console src/main.c)
target_link_libraries(scb_console PRIVATE scb_rules)
set_target_properties(scb_console PROPERTIES LINKER_LANGUAGE CXX)

enable_testing()
add_executable(libchess_adapter_tests tests/libchess_adapter_tests.c)
target_link_libraries(libchess_adapter_tests PRIVATE scb_rules)
set_target_properties(libchess_adapter_tests PROPERTIES LINKER_LANGUAGE CXX)
add_test(NAME libchess_adapter_tests COMMAND libchess_adapter_tests)

find_package(Python3 COMPONENTS Interpreter QUIET)
if(Python3_Interpreter_FOUND)
	add_test(NAME play_ai_tests COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/play_ai_tests.py)
endif()
