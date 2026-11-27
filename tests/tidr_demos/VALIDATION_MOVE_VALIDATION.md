# TIDR #20/#22/#23 implementation validation — 2026-11-26

This phase **only added files** under `tests/tidr_demos/`. The earlier README,
plan, launcher, observer, #19/#33 scripts and all other earlier files were retained
unchanged. `README_MOVE_VALIDATION.md` supplies the new commands and TA procedures
without changing the existing README.

## Executed software checks

On the development Mac:

```text
python3 -B -m unittest discover -s tests/tidr_demos/selftests -v
Ran 18 tests in 1.921s
OK
```

All 10 earlier tests and 8 added tests passed. The added tests cover:

1. Detection of a candidate rule query before required confirmation in a synthetic
   negative trace.
2. Real production confirmation/validation ordering with synthetic board input.
3. Illegal confirmation preserving accepted state and records.
4. Legal confirmation with mismatched occupancy preserving accepted state.
5. Illegal rejection, blocked subsequent candidate, restoration, one accepted move,
   and detection of an incorrectly changed accepted FEN in a negative trace.
6. Native pawn/knight legal sets and the blocked rook's empty set, with no false
   physical timing pass from synthetic input.
7. Timing-bound math at 500 ms, an inconclusive longer upper bound, a provably late
   query, and incorrect-guidance detection.
8. Refusal of window marking without the required extended observer state.

The tests executed original native rules, GameSession, GameStore and native player
APIs using fresh, temporary isolated databases. Board inputs and numeric timing
fixtures were explicitly synthetic and every new selftest observation was tagged
synthetic. No serial device, UI socket, native display or service was launched.
Selftest runs were cleaned up by their fixtures; no actual demo records were
deleted.

AST parsing of all demo Python sources succeeded. `--help` succeeded for each new
demo script and `run_move_validation_service.py` without launching anything.

## File integrity / Git confirmation

SHA-256 values for all **15 pre-existing demo files** were captured before this
phase and compared afterward. Result: **0 modified or missing**. Tracked Git checks
also remained clean:

```text
git diff --exit-code          # exit 0, no tracked working-tree changes
git diff --cached --exit-code # exit 0, no staged changes
git status --short --untracked-files=all
```

All status entries were untracked files within `tests/tidr_demos/`. No production
source, firmware, configuration, entry point, UI or database was modified.

## Hardware status and blockers

| TIDR | Implementation | Actual final-hardware verification |
|---|---|---|
| #20 | Ready for manual ambiguous/valid/invalid/mismatched cases | NOT RUN; requires actual MCU AMBIGUOUS, native touchscreen confirmation and physical evidence |
| #22 | Ready for manual illegal/block/restore/legal sequence | NOT RUN; requires actual candidate reports, restoration and accepted persistence |
| #23 | Ready for legal-set checks and conservative timing capture | NOT RUN; requires actual lifts and timing evidence establishing ≤500 ms |

No hardware TIDR PASS is claimed. Missing prerequisites, absent/incomplete extended
traces, uncorrelated sensor dispatch or missing physical evidence cause BLOCKED.
The existing firmware does not timestamp its internal lift identification. #23
therefore distinguishes Pi receipt timing from a pre-action-to-result upper bound.
A TA-reviewed recording must show that the marker preceded the physical lift;
an upper bound ≤500 ms proves the full deadline. If this proof cannot be obtained,
timing remains BLOCKED without a production change. A rule query starting more
than 500 ms after Pi reception establishes a definite violation and causes FAIL.
