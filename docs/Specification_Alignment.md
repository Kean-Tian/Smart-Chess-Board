# Software Specification Alignment

This change applies the Team 24 requirements supplied on 2026-10-29 to software configuration, scheduling, diagnostics, and tests. A configured target or simulated result is not a hardware measurement.

## Requirements and Verification Scope

| Requirement | Implementation or dependency | Current verification |
|---|---|---|
| Engine response target 2–5 s per move | Game entry points accept 2000–5000 ms, default 3000 ms. The engine rejects results outside a 5 s turn-response deadline. | Host engine tests; Pi runtime still required. Forced moves can finish earlier; there is no artificial minimum delay. Startup and fault cleanup are separate. |
| Full-board scan >50 Hz | Explicit 10 ms full-board schedule (100 Hz nominal), 1 ms row settling, absolute 1 ms control-task schedule. LED transmission runs in another task. | Host timing simulation and target compilation. An earlier S2 session reported 10 ms latest / 12 ms maximum frame periods with zero misses; sustained current-firmware rate still requires TIMING measurements. |
| Debounce within milliseconds | Two consecutive identical complete frames. Acceptance is 10 ms after the first matching candidate observation at the nominal schedule; physical detection typically needs up to about 20–30 ms depending on row phase. | Simulated stable inputs. Noise, sensor startup, polarity, and orientation require hardware tests. |
| LED/visual feedback <100 ms | Queue-based LED updates, separate RMT worker, 5 ms Pi event polling, background engine search, and 80 ms LED-command ACK timeout. | LED queue-to-RMT-completion timing is reported by PLATFORM. This does not measure the complete physical-event-to-light path or a TFT GUI. |
| SRAM about 264–520 KB for search | Stockfish runs in Pi DRAM, not MCU SRAM. Its default Hash is 16 MiB; its total process memory is larger. The firmware has no search/transposition table. A separate conservative 264 KiB ceiling checks static MCU DRAM/IRAM/RTC allocation at ESP-IDF link time. | Build-time static accounting and runtime free/minimum internal heap reporting. The original search-SRAM wording conflicts with this architecture and needs clarification in the report. |
| GPIO capacity 22–25 minimum | The S2 test-harness map uses 18 external signals plus UART0 TX/RX through the onboard USB bridge (20 MCU signals). No extra pins are assigned merely to raise the count. | Pin uniqueness, S2 header availability, and module restrictions are checked; jumper wiring is required. Additional switches require confirmed PCB connections. |
| Maximum 25 W, typical 10 W | Default engine threads reduced to 1, Hash reduced to 16 MiB, Ponder remains off, and LED channels are capped at 32/255. Motor/magnet stop behavior is retained. | Resource controls only; whole-system power has not been measured or guaranteed. |
| Ambient operation 10–35 C | Component, enclosure, and environmental qualification. | Not established by software tests. |
| Enclosure surface <45 C | Requires enclosure temperature measurements and thermal design; chip temperature would not substitute for enclosure temperature. | No connected enclosure sensor; no fabricated software temperature protection. |
| Squares 50–55 mm, area 400–440 mm | Physical construction; SET_STEPS must be calibrated using actual square size and transmission. | No arbitrary steps/mm or measured dimensions are assumed. |
| Footprint <=600 x 550 mm, height <=50 mm | Mechanical design and measurement. | Not changed or verified by software. |
| Weight <5 kg | Physical bill of materials and weighing. | Not changed or verified by software. |
| Future battery >=6 h, charge <=3 h | Battery capacity, charger, load profile, and runtime testing. | No battery/charger interface is present in the supplied MCU wiring. |
| Prototype <=$525, consumer price $300–350 | BOM, procurement, and product cost analysis. | Not changed or verified by software. |

## Runtime Diagnostics

After connecting the flashed MCU to a Pi, run from `pi5/`:

```sh
.venv/bin/python app/board_diagnostics.py --port /dev/ttyUSB0 --seconds 10 --exercise-leds --output runtime/Timing_Validation.json
```

This command does not ARM, GOTO, MOVE, or JOG. The optional LED exercise changes a dim a1 LED and clears the LEDs afterward. It should be used outside an active game. Closing the USB client sends STOP as in the existing protocol.

- `TIMING`: full frames completed, latest and maximum frame interval in microseconds, intervals at or above 20 ms, and debounce acceptance time from the first complete candidate frame.
- `PLATFORM`: last/maximum LED queue-to-RMT-completion time, LED intervals at or above 100 ms, RMT failures, and current/minimum free internal byte-addressable heap.
- Scan-only diagnostics omit LED acceptance and report led_software_pass as null unless --exercise-leds is requested. When LED exercise is requested, diagnostic acceptance requires observed complete-board rate strictly above 50 Hz, maximum recorded interval below 20 ms, zero scan misses, LED software completion below 100 ms, and no LED failures. Maximums/counters are cumulative since boot (or since POLARITY resets scan state), so a previous failure is not hidden by a later good sample.
- LED updates use a one-entry queue: a newer state replaces an older state that has not started transmission. ACK confirms acceptance into that queue, not physical display completion. PLATFORM measures completed frames, not every intermediate request.
- The current two-frame debounce is based on complete snapshots; one continuously noisy square can delay stable-board acceptance. No finite bound is claimed for an input that never stabilizes.

The report intentionally separates MCU software timings from optical feedback, real motor motion, Pi scheduling, USB transport delays, power, and thermal measurements.

## Firmware and Safety Boundaries

The current MCU target is ESP32-S2-Saola-1, with a new test-harness GPIO map documented in PCB_Connection_Map.md. Row-settling time, polarity defaults, calibration requirements, and protection timeouts are retained. No undocumented homing or temperature inputs are assigned. Automatic homing, collision avoidance, automatic captures, and a full touchscreen GUI remain outside this change.

The ESP-IDF post-link RAM check includes static internal data, instruction RAM, and RTC allocations, excluding flash sections and linker padding. It does not include later dynamic task/driver allocations. Inspect PLATFORM heap/min_heap on hardware under sustained load. The native ESP-IDF CMake target runs the RAM check after linking. The release manifest records current measured static allocation.

The ESP32-S2 has one CPU core. Control (priority 10), LED (priority 3) and serial output (priority 4) are scheduled on that single core; no second-core pinning is used. RMT uses interrupt refilling without DMA. Both processors and their operating systems remain subject to scheduling delays. TIMING detects observed failures; source configuration alone is not proof that timing requirements have been met on the PCB.

An asynchronous RMT output failure is counted and reported as `FAULT LED_OUTPUT` by the control task, which also disables motion and releases the electromagnet.

## Current S2 Sensor Mapping and Verification

MUX A0/A1/A2 use GPIO36/37/38; DIG_OUT1..8 use GPIO1..8; UART0 TX/RX use GPIO43/44. The external RGB data pin is GPIO17; the board RGB on GPIO18 is unused. GPIO46 is input-only and is not used as a select output.

Default occupancy is HIGH, corrected after the user observed magnet placement being reported as LIFT with the old LOW setting. The raw captured input, MUX address and stable occupancy are reported together. Human-readable square names replace hexadecimal masks in the Python terminal only; the wire representation is unchanged. Automatic sensor diagnostics are limited to five snapshots/second without changing the nominal 100 Hz scan schedule.

Physical orientation is still pending: address000 / DIG_OUT8 displays logical h1, but the user triggered the physical lower-left corner. Do not infer a top/bottom or left/right convention from logical labels. Four-corner and all-square tests are required before gameplay. See [S2 test guide](ESP32_S2_Test_Guide.md).
