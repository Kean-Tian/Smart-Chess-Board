# TA preparation report — 2026-11-26

## Deliverables

- `TA_CHECKOFF_GUIDE.md`: final-hardware readiness, exact commands, combined run
  cards for all ten implemented TIDRs, physical actions, evidence, measurements,
  cleanup, isolated failure test, restart/power cycle and existing-launcher fallback.
- `TA_CHECKOFF_RESULTS_TEMPLATE.md`: unassessed results/signature table and detailed
  trial/blocker/safe-state fields. Every execution status starts NOT RUN.
- `TA_COMMAND_AUDIT.md`: static command/ownership/dependency/observer compatibility
  review, mitigations and limits.
- `run_ta_service.py`: optional operator-only launcher using original shared launch
  and existing observers, additionally retaining legacy #19 completion records.
- `checkoff_index.py`: read-only test-run IDs, metadata, evidence hashes and relevant
  annotation tokens; no control client or writable GameStore.

## Recommended order

1. Final Pi readiness and all-64 occupancy/LED mapping with all controllers closed.
2. One main session: #23/#37/#38; #22/#39/#27 error; #20 cases; #27 overview/#28;
   #27 check and actual mate/#19 completion; #33 paused-game replay.
3. Close main safely; perform real #19 failure injection in its separate DB;
   close failure safely and disarm only its named fixture trigger.
4. Relaunch main for record verification, then normal operator shutdown/power cycle
   and another main relaunch. These are required #19 restarts, not gratuitous ones.
5. Close all sessions; attach/import actual measurements; evaluate each TIDR
   independently and obtain TA disposition/signature.

## What was verified in this phase

**Static inspection only. No tests, demos, preflight, services, UI, hardware,
generator, mapping capture, or checkoff index were executed.**

- Parsed **34 Python source files** as AST without importing/executing them.
- Reviewed **5 documentation files** (all existing READMEs and the unified guide).
- Parsed **102 shell blocks** with `/bin/sh -n`, which performs syntax inspection
  only and does not execute commands inside them.
- Statically matched **135 documented script commands** to existing script paths
  and declared/delegated option names. No missing script or unknown option found.
  Case/setup/ownership requirements were reviewed manually against the source.
- Compared SHA-256 values for all **44 pre-existing demo files**: none modified
  or missing.
- `git diff --exit-code`, `git diff --cached --exit-code`, and `git diff --check`
  returned exit 0. Git status showed only untracked paths under `tests/tidr_demos/`.

The previous 31 passing software tests remain historical results. No new passing
unit-test count or runtime validation of the new launcher/index is claimed. The
new launcher preserves both record formats by invoking existing observation code;
the guide also provides an existing-launcher fallback if new runtime integration
is not accepted for checkoff.

## Audit findings and remaining blockers

- Existing extended group launchers omit #19's legacy commit/end records. The
  optional new observer preserves these without altering earlier files; fallback
  needs another actual Fool's Mate under the base launcher.
- Final hardware readiness remains unverified. Required software must already be
  installed on the Pi; unsupported firmware/interfaces or wrong-architecture/
  headless builds remain BLOCKED, not silently rebuilt/flashed.
- Optical one-second/500 ms deadlines require calibrated actual visible endpoints;
  missing equipment or ambiguous uncertainty remains BLOCKED. ACK/socket/RMT data
  and generated games cannot substitute.
- #23 needs full-path proof beyond Pi receipt; its documented pre-action bound is
  conservative and must precede the physical lift.
- #33 replay must not overlap clock disconnect/reset, End, Quit or write-failure
  windows. Failure injection must remain in its own DB and service ownership phase.
- Map and LED windows must share their capture boot. Current mapping records lack
  boot-domain binding; do not mix post-reboot mappings into earlier windows.
- Absolute/UID-bound manifests must be created on the Pi and kept at stable paths.
  Device enumeration can change after disconnect/reboot. Fake UI mode must be unset,
  not set to zero. File existence preflight does not prove native architecture or
  physical touchscreen rendering.
- Native Game shows the latest move; full history uses existing View position.
  A full live move-list widget is not implemented. Rules-terminal feedback selects
  LED_CLEAR immediately, so a separate final-mating-move indication is not established.

No production file, earlier demo, configuration or production DB changed. No
normal application service was stopped/restarted. All ten actual hardware results
remain **NOT RUN / unassessed** in the supplied template.
