# Smart Chessboard

This repo contains a local command-line prototype for my smart chessboard
project. It uses [`libchess`](https://github.com/kz04px/libchess) to keep track
of the position and check whether each move is legal.

## Build and run

The desktop build needs CMake, a C17 compiler, a C++20 compiler, and Git. CMake
downloads the pinned `libchess` version automatically the first time it runs:

```sh
cmake -S . -B build
cmake --build build
ctest --test-dir build --output-on-failure
./build/scb_console
```

Moves use UCI coordinates. For example, type `e2e4` to move a piece from e2 to
e4. For promotion, add the new piece at the end, such as `e7e8q`.

## What works so far

The `libchess` rules adapter checks normal legal moves as well as check,
checkmate, stalemate, castling, en passant, promotion, threefold repetition,
and the 50-move draw rule. Insufficient-material draws are not handled yet.
