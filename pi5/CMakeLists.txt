cmake_minimum_required(VERSION 3.16)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    project(SCB_Pi5 LANGUAGES C CXX)
    enable_testing()
endif()
set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(SCB_PI5_ROOT "${CMAKE_CURRENT_SOURCE_DIR}")
set(SCB_CHESS_SRC "${SCB_PI5_ROOT}/vendor/libchess/src")
add_library(libchess_vendor STATIC
    ${SCB_CHESS_SRC}/attackers.cpp
    ${SCB_CHESS_SRC}/check_evasions.cpp
    ${SCB_CHESS_SRC}/checkers.cpp
    ${SCB_CHESS_SRC}/count_moves.cpp
    ${SCB_CHESS_SRC}/get_fen.cpp
    ${SCB_CHESS_SRC}/is_legal.cpp
    ${SCB_CHESS_SRC}/king_allowed.cpp
    ${SCB_CHESS_SRC}/legal_captures.cpp
    ${SCB_CHESS_SRC}/legal_moves.cpp
    ${SCB_CHESS_SRC}/legal_noncaptures.cpp
    ${SCB_CHESS_SRC}/makemove.cpp
    ${SCB_CHESS_SRC}/movegen.cpp
    ${SCB_CHESS_SRC}/perft.cpp
    ${SCB_CHESS_SRC}/pinned.cpp
    ${SCB_CHESS_SRC}/predict_hash.cpp
    ${SCB_CHESS_SRC}/set_fen.cpp
    ${SCB_CHESS_SRC}/square_attacked.cpp
    ${SCB_CHESS_SRC}/squares_attacked.cpp
    ${SCB_CHESS_SRC}/undomove.cpp
    ${SCB_CHESS_SRC}/valid.cpp
    ${SCB_CHESS_SRC}/zobrist.cpp
)
target_include_directories(libchess_vendor SYSTEM PUBLIC "${SCB_CHESS_SRC}")
set_target_properties(libchess_vendor PROPERTIES POSITION_INDEPENDENT_CODE ON)
add_library(scb_rules SHARED rules/src/libchess_adapter.cpp)
target_include_directories(scb_rules PUBLIC rules/include)
target_link_libraries(scb_rules PUBLIC libchess_vendor)
target_compile_options(scb_rules PRIVATE -Wall -Wextra -Wpedantic)
set_target_properties(scb_rules PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")
add_executable(scb_console rules/src/console.c)
target_link_libraries(scb_console PRIVATE scb_rules)
set_target_properties(scb_console PROPERTIES LINKER_LANGUAGE CXX RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
add_executable(libchess_adapter_tests tests/libchess_adapter_tests.c)
target_link_libraries(libchess_adapter_tests PRIVATE scb_rules)
set_target_properties(libchess_adapter_tests PROPERTIES LINKER_LANGUAGE CXX RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
add_test(NAME libchess_adapter_tests COMMAND libchess_adapter_tests)
find_package(Python3 COMPONENTS Interpreter QUIET)
if(Python3_Interpreter_FOUND)
    foreach(test scb_link_tests board_game_tests stockfish_engine_tests stockfish_board_tests openrouter_engine_tests play_mode_tests coaching_tests)
        add_test(NAME ${test} COMMAND ${Python3_EXECUTABLE} "${SCB_PI5_ROOT}/tests/${test}.py")
    endforeach()
    set_tests_properties(stockfish_board_tests play_mode_tests coaching_tests PROPERTIES ENVIRONMENT "SCB_RULES_LIBRARY=$<TARGET_FILE:scb_rules>")
endif()
