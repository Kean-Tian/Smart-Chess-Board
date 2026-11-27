"""TIDR #19: analyze real UI sessions; explicitly arm an isolated SQLite failure fixture."""
import argparse
import fcntl
import json
import sqlite3
import sys
import time

sys.dont_write_bytecode = True
from common.runtime import (Blocked, Report, append, attachments, bootstrap, cli,
                            database_snapshot, events, game_record, load_run,
                            no_symlinks, read_jsonl, run_argument, stopped_observer_check)

TRIGGER = "tidr19_abort_position_update"


def failure_fixture(run, manifest, arm):
    if manifest["purpose"] != "failure":
        raise Blocked("Failure injection requires a separately initialized --purpose failure run")
    db_path = no_symlinks(manifest["database"])
    if not db_path.is_file():
        raise Blocked("First start the real application and prepare a test game in this failure run")
    if arm:
        trace = events(run)
        latest = next((e for e in reversed(trace) if e["kind"] == "state"), None)
        if (not latest or time.time_ns() - latest["wall_ns"] > 2_000_000_000
                or not latest["state"]["active"] or not latest["state"]["paused"]):
            raise Blocked("Pause the active failure-test game in the native UI before arming")
    elif (run / "service.lock").exists():
        with no_symlinks(run / "service.lock").open("r") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise Blocked("Quit the demo UI and stop its own service gracefully before disarming") from exc
    baseline = database_snapshot(db_path)
    with sqlite3.connect(db_path, timeout=0.5) as db:
        if arm:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (TRIGGER,)).fetchone():
                raise Blocked("Failure trigger is already armed")
            db.execute(f"""CREATE TRIGGER {TRIGGER} BEFORE UPDATE OF current_fen ON games
                WHEN NEW.current_fen != OLD.current_fen
                BEGIN SELECT RAISE(ABORT, 'TIDR19 isolated position update failure'); END""")
        else:
            db.execute(f"DROP TRIGGER IF EXISTS {TRIGGER}")
    append(run / "failure.jsonl", {"kind": "armed" if arm else "disarmed", "baseline": baseline})
    print("Armed real SQLite ABORT trigger in failure-test DB only. Resume, then make a physical move."
          if arm else "Removed only the named failure fixture trigger; records retained.")
    return 0


def verify_failure(run, report):
    trace = events(run)
    stopped_observer_check(report, trace, "failure service")
    armed = [e for e in read_jsonl(run / "failure.jsonl") if e["kind"] == "armed"]
    attempts = []
    for arm in armed:
        calls = {e["token"]: e for e in trace if e["kind"] == "call" and
                 e.get("operation") == "GameSession.commit" and e["monotonic_ns"] > arm["monotonic_ns"]}
        # Only attempts during an armed interval count.
        stop = min([e["monotonic_ns"] for e in read_jsonl(run / "failure.jsonl")
                    if e["kind"] == "disarmed" and e["monotonic_ns"] > arm["monotonic_ns"]] or [2**63])
        for ret in trace:
            call = calls.get(ret.get("token"))
            if (ret["kind"] != "return" or not call or ret["monotonic_ns"] >= stop
                    or ret["data"].get("return") is not None):
                continue
            before = call["data"]["state"]
            after = ret["data"]["state"]
            # Prove a real production store.move attempt happened, rather than an unrelated rejected input.
            stores = [s for s in trace if s["kind"] == "call" and s.get("operation") == "GameStore.move"
                      and call["monotonic_ns"] <= s["monotonic_ns"] <= ret["monotonic_ns"]
                      and s["data"].get("game_id") == before["game_id"]
                      and s["session"] == call["session"]]
            if stores and after["paused"] and "not saved" in after["message"]:
                old = game_record(arm["baseline"], before["game_id"])
                new = game_record(ret["data"]["snapshot"], before["game_id"])
                unchanged = (old["moves"] == new["moves"] and old["game"] is not None
                             and new["game"] is not None
                             and old["game"]["current_fen"] == new["game"]["current_fen"]
                             and before["fen"] == after["fen"] and before["moves"] == after["moves"])
                attempts.append(unchanged and after["restore"])
    report.check("real aborted write: move and position roll back; accepted game does not advance",
                 bool(attempts) and all(attempts), f"observed failure attempts={len(attempts)}",
                 missing=not attempts)
    report.check("failure observer complete", not any(e["kind"] == "observer_error" for e in trace),
                 "no observation errors allowed", missing=True)
    report.check("failure test used final hardware", bool(attachments(run, "hardware")),
                 "operator-supplied physical evidence plus real board/event trace required", missing=True)
    report.check("failure test received actual board events", any(e["kind"] == "serial_reply" and
                 e.get("frame_kind") == "EVENT" and e.get("payload", "").startswith("MOVE ") for e in trace),
                 "production serial observations", missing=True)


def evaluate(run, manifest, args):
    report = Report(19)
    trace = events(run)
    stopped_observer_check(report, trace)
    if args.failure_run:
        fail_run, fail_manifest = load_run(args.failure_run)
        if fail_run == run or fail_manifest["purpose"] != "failure":
            raise Blocked("Use a different failure-purpose run for injection evidence")
        verify_failure(fail_run, report)
    else:
        report.check("atomicity/failure test supplied", False, "--failure-run is required", missing=True)
    report.check("record run purpose", manifest["purpose"] == "records", "completion/persistence DB separate from failure DB")
    snapshot = database_snapshot(manifest["database"])
    record = game_record(snapshot, args.game_id)
    if record["game"] is None:
        report.check("designated completed game exists", False, f"game ID {args.game_id} not found", missing=True)
        return report.finish(run)
    game, moves = record["game"], record["moves"]
    expected_moves = args.expected_moves.split()
    report.check("SQLite integrity", snapshot["integrity"] == "ok", snapshot["integrity"])
    stores = [e for e in trace if e["kind"] == "call" and
              e.get("operation") in {"GameStore.move", "GameStore.checkpoint"} and
              e["data"].get("game_id") == args.game_id]
    report.check("production writer uses durable SQLite settings", bool(stores) and all(
                 s["data"].get("storage", {}).get("synchronous", 0) >= 2 and
                 s["data"].get("storage", {}).get("journal_mode") not in {None, "off", "memory"}
                 for s in stores), "observed writer connection: synchronous >= FULL and persistent journal", missing=not stores)
    report.check("saved details", game["white_name"] == args.white and game["black_name"] == args.black
                 and game["result"] == args.result and game["status"] == "completed"
                 and game["mode"] == "pvp" and game["ended_at"] is not None,
                 json.dumps({k: game[k] for k in ("white_name", "black_name", "result", "status", "mode", "ended_at")}))
    report.check("saved move history", [m["uci"] for m in moves] == expected_moves
                 and [m["ply"] for m in moves] == list(range(1, len(moves) + 1)), str(expected_moves))
    bootstrap()
    from scb_rules import Game
    with Game() as rules:  # Existing native rules, not a duplicate replay/validation engine.
        positions = []
        initial = rules.fen()
        for move in expected_moves:
            if not rules.play(move):
                raise Blocked(f"Expected sequence is not legal according to production rules: {move}")
            positions.append(rules.fen())
        report.check("saved initial and every resulting position", game["initial_fen"] == initial
                     and [m["fen"] for m in moves] == positions
                     and game["current_fen"] == (positions[-1] if positions else initial),
                     "all FENs checked using original native Game")
    completions = [e for e in trace if e["kind"] == "return" and
                   e.get("operation") in {"GameSession.commit", "GameSession.end"}
                   and e["data"].get("snapshot") and
                   game_record(e["data"]["snapshot"], args.game_id)["game"] is not None and
                   game_record(e["data"]["snapshot"], args.game_id)["game"]["status"] == "completed"]
    # Match to its call: later no-op End requests must not masquerade as completion measurements.
    calls = {e["token"]: e for e in trace if e["kind"] == "call" and
             e.get("operation") in {"GameSession.commit", "GameSession.end"}}
    completions = [e for e in completions if e.get("token") in calls and
                   calls[e["token"]]["data"]["state"]["game_id"] == args.game_id and
                   calls[e["token"]]["data"]["state"]["active"] and
                   not e["data"]["state"]["active"]]
    if completions:
        completion = completions[0]
        # Entry precedes the actual completion decision: a conservative upper bound.
        duration_ms = (completion["data"]["availability_ns"] - completion["started_ns"]) / 1e6
        report.check("completion-to-committed availability <= 2000 ms", duration_ms <= 2000,
                     f"conservative completion-call-entry -> separate-reader availability: {duration_ms:.3f} ms; "
                     "includes observer overhead; writer settings and normal power cycle checked separately. "
                     "A bound above the deadline blocks proof rather than establishing a precise deadline violation.",
                     missing=True)
        baseline = game_record(completion["data"]["snapshot"], args.game_id)
        report.check("completed record remains exact", record == baseline, "all game/move columns compared")
        startups = [e for e in trace if e["kind"] == "service_ready" and
                    e["wall_ns"] > completion["wall_ns"] and e["session"] != completion["session"]]
        restart_ok = [e for e in startups if game_record(e["snapshot"], args.game_id) == baseline]
        report.check("manual application restart preserves exact records", bool(restart_ok),
                     f"matching later service startups={len(restart_ok)}", missing=not startups)
        power = [e for e in restart_ok if completion["boot_id"] and e["boot_id"] and
                 e["boot_id"] != completion["boot_id"]]
        report.check("normal final-Pi power cycle preserves records", bool(power) and
                     bool(attachments(run, "power-cycle", str(args.game_id))),
                     "requires changed Linux boot ID, exact record match and operator evidence of normal shutdown/power cycle",
                     missing=True)
    else:
        report.check("timed completion observation", False, "complete this game through observed real UI session", missing=True)
    report.check("final hardware evidence", bool(attachments(run, "hardware")),
                 "operator must document Pi 5, final PCB, physical play and final touchscreen", missing=True)
    report.check("real sensor input captured", any(e["kind"] == "serial_reply" and
                 e.get("frame_kind") == "EVENT" and e.get("payload", "").startswith("MOVE ") for e in trace),
                 "no synthetic events are generated by this fixture", missing=True)
    report.check("observer complete", bool(trace) and not any(e["kind"] == "observer_error" for e in trace),
                 "no observation errors allowed", missing=True)
    return report.finish(run)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("arm-failure", "disarm-failure", "evaluate"):
        item = sub.add_parser(action)
        run_argument(item)
        if action != "evaluate":
            item.add_argument("--confirm-isolated-test-db", action="store_true", required=True)
        else:
            item.add_argument("--game-id", type=int, required=True)
            item.add_argument("--expected-moves", required=True, help="Space-separated UCI sequence actually played")
            item.add_argument("--white", required=True)
            item.add_argument("--black", required=True)
            item.add_argument("--result", choices=["1-0", "0-1", "1/2-1/2", "*"], required=True)
            item.add_argument("--failure-run")
    args = parser.parse_args()
    run, manifest = load_run(args.run)
    if args.action == "evaluate":
        return evaluate(run, manifest, args)
    return failure_fixture(run, manifest, args.action == "arm-failure")


if __name__ == "__main__":
    raise SystemExit(cli(main))
