# LED demonstration implementation validation — 2026-11-26

Executed locally on the development Mac:

```text
python3 -B -m unittest discover -s tests/tidr_demos/selftests -v
Ran 31 tests in 4.027s
OK
```

All 25 earlier tests and 6 new LED tests passed. New tests exercised:

1. Full-array expected colors, absence of extra illuminated squares, wrong-color
   rejection and an empty expected set.
2. Optical timing PASS/FAIL/BLOCKED classification with uncertainty bounds;
   unsynchronized data cannot establish the 500 ms deadline.
3. ACK observation remains explicitly non-optical; missing physical mapping and
   missing physical frames remain BLOCKED.
4. Original pawn/knight/blocked-rook legal guidance and clearing selection on piece
   return, with no device connected and no actual LED commands sent.
5. Original accepted-state persistence before feedback, e2e4/e7e5 replacement,
   illegal contrast and End/new-preparation clear selection.
6. Original warning persistence through Guidance changes and partial restoration,
   full restoration clearing, unchanged DB records, and detection of a premature
   clear in a synthetic negative trace.

Tests used the original native chess rules, GameSession, GameStore and public
player APIs with real SQLite fixture databases. Board input and numeric optical
intervals were explicitly synthetic. All new selftest observations were tagged
synthetic. No serial device, UI socket, native touchscreen, service or mapping
capture was launched. Temporary selftest DB/build artifacts were cleaned up by
their own fixtures; no real demo/production records were deleted.

All Python files parsed successfully. The optical JSON example parsed, and
`--help` succeeded for the three LED scripts, `run_led_service.py` and
`verify_led_mapping.py`. Help commands never entered hardware execution.

## Integrity / Git confirmation

Before work, SHA-256 values were captured for all **33 pre-existing demo files**.
Comparison afterward found **zero modified or missing files**. This phase adds
only new files under `tests/tidr_demos/`, including its supplemental README.

```text
git diff --exit-code          # exit 0: no tracked working-tree changes
git diff --cached --exit-code # exit 0: no staged changes
git diff --check              # exit 0
git status --short --untracked-files=all
```

All status entries were untracked files under `tests/tidr_demos/`. No production
source, firmware, LED driver, game logic, UI, configuration, schema, entry point
or production database was changed. Earlier demos/documentation remain unchanged.

## Actual hardware status / remaining blockers

| Test | Software implementation | Actual final-hardware result |
|---|---|---|
| 64-square mapping | Manual exclusive-owner capture and evidence guard ready | NOT RUN; blocks game-demo windows until completed and reviewed |
| #37 | Guidance/return/completion patterns and ≤500 ms optical analysis ready | NOT RUN; requires real Hall events, full-array optical inspection and calibration |
| #38 | Verified post-persistence anchor, accepted colors/replacement/clearing ready | NOT RUN; requires actual illumination measurements and physical comparison |
| #39 | Warning continuity, partial/full restoration and early-clear detection ready | NOT RUN; requires continuous physical footage and actual restoration |

No hardware PASS/FAIL is claimed from local tests. The 500 ms assertions stay
BLOCKED without sufficient calibrated optical evidence; ACK/RMT diagnostics are
not substitutes. #39 has no numeric timing threshold. Mapping failures, missing
physical evidence, active actuators, missing interfaces or incomplete observers
cannot be worked around by modifying production code.

Known scope limitation: current production selects LED_CLEAR immediately on a
rules-terminal move. The requested #38 two-nonterminal-move/manual-End workflow
can be demonstrated; a separate final-checkmating-move indication is not established
by that workflow. No fabricated final flash or firmware change was introduced.

The combined manual workflow in `README_LED_FEEDBACK.md` shares one native
service session while preserving independent requirement results and evidence.
