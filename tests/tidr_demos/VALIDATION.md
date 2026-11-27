# Implementation validation — 2026-11-26

Executed locally on the development Mac, with no UI/service/serial launch:

```text
python3 -B -m unittest discover -s tests/tidr_demos/selftests -v
Ran 8 tests
OK
```

The tests verified:

- Existing run directories cannot be reinitialized.
- Symlink/hard-link database aliases are refused without changing their targets.
- Partial evidence lines are excluded; corrupt complete lines are rejected.
- The actual production GameSession/GameStore and native rules, using synthetic
  board input in a new isolated fixture, roll back a real SQLite ABORT failure
  without advancing accepted history or position.
- Software-only completion remains BLOCKED for physical checkoff.
- Replay evaluation without physical display evidence remains BLOCKED.
- A synthetic movement-attempt test produces FAIL, even when other evidence is
  missing. This is a test of the evaluator, not a hardware movement test.

Also executed: AST parsing of all nine new Python files and `--help` for all five
CLI entry scripts. Every syntax/help check succeeded. Temporary selftest databases
were removed by their own test fixtures; no game/demo records were deleted.

Git checks executed:

```text
git diff --exit-code          # exit 0; no unstaged tracked changes
git diff --cached --exit-code # exit 0; no staged tracked changes
git diff --check              # exit 0
git status --short --untracked-files=all
```

Status contained only `?? tests/tidr_demos/...` paths: this README/validation,
the previously created plan, common modules, launch/preflight/evidence tools,
the two demonstration scripts and selftests. No tracked production file changed.
The approved `TIDR_DEMO_PLAN.md` was not edited in this implementation phase.

**Actual TIDR #19 hardware result: NOT RUN.**

**Actual TIDR #33 hardware result: NOT RUN.**

Still required: final Pi preflight, native touchscreen operation, real board play,
on-Pi timing and write-failure observation, manual application restart, normal
shutdown/power-cycle evidence, real replay navigation, command-stream observation
and TA review of physical evidence. The launcher itself was not exercised here,
because launching hardware demonstrations/services was explicitly excluded.

Known verification limits: physical content is operator/TA reviewed rather than
automatically authenticated; unavailable native UI navigation, unobservable device
ownership, missing prerequisites or trace gaps yield BLOCKED. Completion timing is
a conservative call-entry-to-separate-reader bound, including observer overhead.
If that bound exceeds 2 seconds, more precise instrumentation is needed to decide
the requirement rather than treating the upper bound as a measured violation.

## Generated-game fixture addition

Executed after adding `generate_test_game.py`, the native profile adapter and its
integration tests:

```text
python3 -B -m unittest discover -s tests/tidr_demos/selftests -v
Ran 10 tests
OK
```

The two new checks used fresh temporary test runs. They verified refusal of an
owned service lock before any DB was written, and actual Fool's Mate generation
twice through the original native rules, public native player APIs and Python
GameStore APIs. The first game's entire saved record remained unchanged after
the second generation. Both games returned the four expected moves and completed
`0-1` result through production history/review; profiles had real persisted IDs.
The generated game remained BLOCKED for complete TIDR #19 hardware verification.
The C adapter built successfully on this development Mac with its existing
compiler and SQLite library. The same build still requires verification on Pi.

`generate_test_game.py --help` also succeeded. All integration-test databases and
native build artifacts were confined to selftest runs and cleaned up by those
fixtures. No persistent demo game was pre-created, no physical game was claimed,
and no UI/service/hardware was launched. Git tracked/staged diffs remained empty;
all added or updated demo artifacts are under `tests/tidr_demos/`.
