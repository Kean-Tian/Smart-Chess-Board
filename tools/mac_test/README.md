# Software Validation on the Current Mac

Run `sh SCB_Computer_Test.command` from the project root to choose Local Mode or AI Mode. AI Mode remembers the key locally after its first hidden input; `--set-api-key` replaces it. Normal startup runs checks silently and records `latest_check.log`; failures are displayed and prevent startup. Add `--check-only` for full test output; these require the local Stockfish binary.

- `check_software.py`: ten regression test suites and integration checks using real Stockfish and libchess. OpenRouter opponent and coaching responses are simulated; no API key or network is needed for tests.
- `binaries/`: runtime files and compiled test programs for the Apple Silicon Mac.
- `BUILD_INFO.json`: runtime-file checksums and platform information.
- `latest_check.log`: full output of the most recent normal-startup check (ignored by Git).
- `latest_result.json`: the most recent host test result, generated automatically when the tests run.

This directory does not contain the engine deployed to the Pi. The Pi's ARM64 Linux files are in `pi5/engines/stockfish/`.
The corresponding Stockfish source code and GPL license are also retained there. Third-party source code for the rules library is in `pi5/vendor/libchess/`.

The MCU test binary uses the current ESP32-S2-Saola-1 GPIO map with simulated inputs. It does not open a serial port, drive GPIO or measure electrical timing. Its current coverage includes 64-square mapping, polarity, synchronized SENSOR traces, protocol framing, outputs, motion guards and watchdogs. Python tests cover readable occupancy, live terminal events and S2 release-image checks.

Separate earlier S2 hardware sessions verified basic USB communication and scan-frame generation; they are not performed by this launcher. Full physical orientation, every sensor position, sustained scan/LED latency and actuator behavior remain to be verified. See the [S2 test guide](../../docs/ESP32_S2_Test_Guide.md).
