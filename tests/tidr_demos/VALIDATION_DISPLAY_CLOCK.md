# #27/#28 implementation validation — 2026-11-26

Executed on the development Mac, with no service, native UI, hardware device or
UI socket launch:

```text
python3 -B -m unittest discover -s tests/tidr_demos/selftests -v
Ran 25 tests in 3.115s
OK
```

All 18 earlier tests and 7 new tests passed. The added checks verified:

- Original five-minute GameSession clocks with real `time.monotonic`, including
  active-side decrements, pause/resume preservation, synthetic connection loss,
  reconnection preservation and ending. No fake clock was supplied.
- A software-only connection-loss workflow remains BLOCKED for hardware checkoff.
- Inactive-clock changes and clock resets between samples are detected, including
  changes smaller than a displayed second; no arbitrary accuracy tolerance is used.
- Original rules produce the legal check sequence and Fool's Mate; the illegal
  warning survives an unrelated Guidance action/tick and clears on restoration.
- Socket/backend state alone cannot prove visible pixels or visibility timing.
- Bounded visibility timing distinguishes PASS, definite FAIL and uncertainty
  spanning the deadline (BLOCKED); unsynchronized evidence remains BLOCKED.
- Imported evidence must match an attached video hash; altered annotation files
  are rejected. Synthetic test files are not represented as actual recordings.
- A longer conservative transition upper bound alone is not falsely reported as
  an exact deadline violation.

Tests used explicitly synthetic board/connection input in fresh isolated fixture
DBs while executing actual production rules, GameSession, GameStore and player
APIs. New observer output in selftests was tagged synthetic. Numeric interval
fixtures only test offline analysis. Temporary test databases/build artifacts
were cleaned up by those fixtures; actual game/demo records were not deleted.

All Python files parsed successfully. `--help` succeeded for the two new demo
scripts and `run_display_clock_service.py`. The visibility JSON example parsed;
its synchronization/measurement defaults deliberately cannot establish a PASS.

## File integrity

SHA-256 values for all **24 files already present under `tests/tidr_demos/`** were
captured before work and compared afterward: **0 modified or missing**. This phase
only adds new files. Earlier launchers, observers, demos and documentation remain
unchanged. `README_DISPLAY_CLOCK.md` contains the new commands and TA procedures.

Git checks:

```text
git diff --exit-code          # exit 0: no tracked working-tree changes
git diff --cached --exit-code # exit 0: no staged changes
git diff --check              # exit 0
git status --short --untracked-files=all
```

Status showed only untracked paths under `tests/tidr_demos/`. No production code,
firmware, UI, configuration, application entry point or production DB changed.

## Actual hardware disposition

| Demonstration | Implementation | Physical verification |
|---|---|---|
| #27 | Native data capture, operator video annotation/import, bounded 1-second analysis and sticky-error checks ready | NOT RUN; actual visibility timing remains BLOCKED until calibrated final-touchscreen evidence is supplied |
| #28 | Raw-clock audit, accepted-event bounds, native workflow and real serial-failure correlation ready | NOT RUN; requires final-board play, physical cable loss/recovery and manual UI actions |

The native active-game UI has a latest-move display, with earlier positions
available through its existing View position controls. It has no full live
move-list widget. If that widget is required by an interpretation of #27, report
the unsupported capability BLOCKED rather than adding a replacement UI.

No hardware PASS/FAIL is claimed from these local tests. A socket send cannot pass
#27 visibility. Missing calibration/equipment, uncertainty crossing a deadline,
legacy/incomplete observations or absent physical evidence cause BLOCKED. No
hardware demonstrations or normal service shutdown/restart actions were executed.
