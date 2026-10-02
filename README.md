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

## Play against AI

This mode also needs Python 3. Build the project as above, then set your OpenAI
API key in the terminal and run:

```sh
export OPENAI_API_KEY="your-api-key"
python3 scripts/play_ai.py
```

You play White. Enter moves such as `e2e4`; the AI plays Black after each legal move.
Enter `quit` to stop. The API is called once per AI turn, so an API key with
available usage is required. `OPENAI_MODEL` can override the default
`gpt-4.1-mini` model. The API key is read from the environment and is never
stored in the repository.

## What works so far

The `libchess` rules adapter checks normal legal moves as well as check,
checkmate, stalemate, castling, en passant, promotion, threefold repetition,
and the 50-move draw rule. Insufficient-material draws are not handled yet.

Work on the MCU input controller has started. The current prototype contains
the basic structure for scanning 64 Hall sensors, debouncing their readings,
detecting a lift-and-place move, sending text events to UART, and simulating a
move with test buttons. The real Pico 2 GPIO and UART drivers still need to be
connected.

## Next steps

- Flash the input-controller firmware onto the Pico 2.
- Deploy the chess rules and AI program to the Raspberry Pi 4B.
- Connect the Raspberry Pi 4B and Pico 2 through UART, then test that physical
  moves can reach the main chess program correctly.
