cmake_minimum_required(VERSION 3.16)
project(smart_chessboard LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(chess_core src/chess.cpp)
target_include_directories(chess_core PUBLIC include)
target_compile_options(chess_core PRIVATE -Wall -Wextra -Wpedantic)

add_executable(scb_console src/main.cpp)
target_link_libraries(scb_console PRIVATE chess_core)

enable_testing()
add_executable(chess_tests tests/chess_tests.cpp)
target_link_libraries(chess_tests PRIVATE chess_core)
add_test(NAME chess_tests COMMAND chess_tests)
