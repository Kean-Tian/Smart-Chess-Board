# Team 24 — final-hardware checkoff results (blank template)

**No results are pre-approved.** Copy this template into the isolated run, then
fill it from actual reports and reviewed final-hardware evidence. NOT RUN and
unassessed are preparation states; do not change them to PASS because software
tests, builds, seeded records, ACKs or screenshots of mock data passed.

## Session and hardware

- Operator / TA: ______________________________
- Checkoff date / timezone: ______________________________
- Repository path / revision / local artifact identity: ______________________________
- Main run / DB / observer sessions: ______________________________
- Failure run / DB / observer sessions: ______________________________
- Actual completed physical Fool's Mate game ID: ______________________________
- Pi 5 identity / OS / Python / native UI and rules build: ______________________________
- ESP32-S3 master and sensor PCB identities / actual transport and port: ______________________________
- Deployed firmware identification or observed capabilities (UNKNOWN if unavailable): ______________________________
- Touchscreen and LED array identities: ______________________________
- 64-square mapping ID / mapping video and cleanup result: ______________________________
- Physical piece set / coordinate labels / polarity verification: ______________________________
- Instruments / serial numbers / acquisition settings: ______________________________
- Synchronization method / before-and-after calibration / uncertainty / drift: ______________________________
- Normal restart evidence / old and new Linux boot IDs / normal power-cycle evidence: ______________________________

## Consolidated results

Execution status: NOT RUN / IN PROGRESS / EXECUTED / INTERRUPTED.
Outcome after execution: PASS / FAIL / BLOCKED. Leave unassessed until evaluated.
For interval measurements record lower and upper bounds, units, uncertainty and
sample count; retain the worst valid sample and all failed/repeated attempts.

| TIDR | Requirement summary | Execution status | Actual measured result | Acceptance threshold / functional condition | PASS / FAIL / BLOCKED | Evidence file / result JSON location | TA signature / date |
|---|---|---|---|---|---|---|---|
| #19 | Record completion, atomicity, restart/power-cycle persistence | NOT RUN | — | ≤2000 ms; correct moves/positions; failed writes do not advance; exact records survive both restart and normal power cycle | Unassessed | — | — |
| #20 | Ambiguous confirmation before candidate validation | NOT RUN | — | Actual AMBIGUOUS, native confirmation; valid/invalid/mismatched cases; no numeric deadline | Unassessed | — | — |
| #22 | Illegal rejection and restoration gate | NOT RUN | — | Accepted FEN/turn/history/records unchanged; further move blocked; legal play after full restoration; no numeric deadline | Unassessed | — | — |
| #23 | Legal destination availability | NOT RUN | — | Correct e2/g1/a1 sets, including empty; ≤500 ms from identified lift with full-path evidence | Unassessed | — | — |
| #27 | Physical display data and persistent errors | NOT RUN | — | Actual visible updates ≤1000 ms; names/turn/clocks/moves/check/checkmate/error; warning persists until resolved | Unassessed | — | — |
| #28 | Active-side clocks and transition behavior | NOT RUN | — | Switch/pause/stop ≤500 ms after accepted events; only active side decreases; disconnect freezes both; exact raw times preserved on resume | Unassessed | — | — |
| #33 | Native saved-game replay preserves current game | NOT RUN | — | Saved details and every forward/back step correct; current paused game unchanged; no movement commands; no numeric deadline | Unassessed | — | — |
| #37 | Actual legal-destination LED pattern | NOT RUN | — | Only legal destinations physically lit ≤500 ms after receipt; clears/replaces on return/completion | Unassessed | — | — |
| #38 | Actual accepted-move LED pattern | NOT RUN | — | Distinct blue source/green destination ≤500 ms after persisted acceptance; replaces old pattern, contrasts with red, clears on End/preparation | Unassessed | — | — |
| #39 | Rejected warning until complete restoration | NOT RUN | — | Red source/destination held continuously through unrelated action and partial restoration, clears after confirmed full restoration; no numeric deadline | Unassessed | — | — |

## Trial detail — duplicate rows as necessary

| TIDR / case / window | Game ID / observer session / event token | Start boundary and clock domain | End boundary / physical frame or sample | Measured interval / uncertainty / raw clock values | Assertion and result | Evidence / annotation / result JSON | TA initials |
|---|---|---|---|---|---|---|---|
| #19 completion | — | Actual completion-call bound | Separate reader availability | — | Unassessed | — | — |
| #19 write failure | — | Trigger armed in failure DB | Rejected original store write | — | Unassessed | — | — |
| #19 restart / power cycle | — | Completed record baseline | Later startup + changed boot ID | — | Unassessed | — | — |
| #20 valid / invalid / mismatch | — | Actual MCU ambiguity | Native confirmation/outcome | — | Unassessed | — | — |
| #22 illegal / blocked / restored / legal | — | Illegal physical event | Restored board / one legal commit | — | Unassessed | — | — |
| #23 e2 / g1 / a1 | — | Identified lift; pre-action bound separately | Legal-set availability | — | Unassessed | — | — |
| #27 overview / error / check / mate | — | Backend update bracket | Actual visible frame bracket | — | Unassessed | — | — |
| #28 White / Black / pause / resume / unplug / reconnect / End | — | Accepted event / actual detection | Original clock effect and hold samples | — | Unassessed | — | — |
| #33 replay | — | Already-paused current game | Review complete, before End/Resume | — | Unassessed | — | — |
| #37 each lift / return / completion | — | Destination-receipt bracket | Actual LED pattern/onset | — | Unassessed | — | — |
| #38 each accepted move / red contrast / End / prepare | — | Post-persistence acceptance bracket | Actual LED pattern/onset | — | Unassessed | — | — |
| #39 warning / unrelated / partial / full | — | Rejection and restoration tokens | Continuous optical review | — | Unassessed | — | — |

## Blockers, failures, retries and scope

Record every genuine failed observation and why a retry was needed. Missing
equipment or ambiguous timing is BLOCKED, not PASS. A conservative upper bound
above a deadline alone does not establish a precise violation; retain its report.

| TIDR | Issue / missing evidence / failed observation | Disposition and retained prior attempt | Remaining action | TA/date |
|---|---|---|---|---|
| — | — | — | — | — |

Special scope notes, if applicable:

- Full live move-list widget unavailable; native last-move/View position behavior reviewed: __________________
- Final checkmating-move LED indication not established by the two-nonterminal-move fixture: __________________
- New unified observer runtime acceptance / fallback selected: __________________
- Prior software test results referenced as historical engineering checks only: __________________

## Final safe-state and evidence retention

- All windows closed before cleanup: __________________
- Demo UI/service gracefully closed; no normal service killed/restarted: __________________
- Actual LEDs dark, motor/magnet outputs safe; unresolved fault noted: __________________
- Board restored manually; origin invalidation from STOP acknowledged: __________________
- Failure trigger disarmed only after failure service released its lock: __________________
- Main/failure DBs, sidecars, traces, mapping, optical annotations and versioned reports retained: __________________
- Operator signature/date: __________________
- TA signature/date and per-requirement disposition: __________________
