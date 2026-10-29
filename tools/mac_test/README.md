# Software Validation on the Current Mac

Run `sh SCB_Computer_Test.command` from the project root to choose Local Mode or AI Mode. AI Mode remembers the key locally after its first hidden input; `--set-api-key` replaces it. Add `--check-only` to run the automated checks separately; these require the local Stockfish binary.

- `check_software.py`: nine regression test suites and integration checks using real Stockfish and libchess. OpenRouter opponent and coaching responses are simulated; no API key or network is needed for tests.
- `binaries/`: runtime files and compiled test programs for the Apple Silicon Mac.
- `BUILD_INFO.json`: runtime-file checksums and platform information.
- `latest_result.json`: the most recent host test result, generated automatically when the tests run.

This directory does not contain the engine deployed to the Pi. The Pi's ARM64 Linux files are in `pi5/engines/stockfish/`.
The corresponding Stockfish source code and GPL license are also retained there. Third-party source code for the rules library is in `pi5/vendor/libchess/`.

These tests validate software and simulated interfaces. GPIO, voltage levels, scanning rate, motors, and sensors still require hardware validation.
