"""TIDR #33: mark and analyze native-UI replay; never connects to UI or serial."""
import argparse
import json
import sys
import time

sys.dont_write_bytecode = True
from common.runtime import (Blocked, Report, append, attachments, cli, database_snapshot,
                            events, game_record, load_run, read_jsonl, run_argument, stopped_observer_check)

# All commands capable of enabling or changing actuator motion/magnet state.
MOVEMENT = {"ARM", "GOTO", "MOVE", "JOG", "MAGNET", "HOME", "ORIGIN", "SET_STEPS",
            "STOP", "DISARM", "IDLE", "CLEAR_FAULT"}


def marker(run, manifest, args):
    marks = read_jsonl(run / "replay.jsonl")
    matching = [m for m in marks if m["window"] == args.window]
    if args.action == "begin" and matching:
        raise Blocked("Choose a new unique replay window name")
    if args.action == "end" and (not matching or matching[-1]["kind"] != "begin"):
        raise Blocked("No open replay window with this name")
    trace = events(run)
    latest = next((e for e in reversed(trace) if e["kind"] == "state"), None)
    if not latest or time.time_ns() - latest["wall_ns"] > 2_000_000_000:
        raise Blocked("Need a fresh observed native-UI state; service/UI may be closed")
    state = latest["state"]
    if not state["active"] or not state["paused"]:
        raise Blocked("Keep a current physical game active and paused throughout replay")
    snapshot = database_snapshot(manifest["database"])
    if args.action == "begin":
        saved = game_record(snapshot, args.saved_game_id)
        if saved["game"] is None or saved["game"]["status"] != "completed" or not saved["moves"]:
            raise Blocked("Saved replay game must be an actually completed test game with moves")
        if args.saved_game_id == state["game_id"]:
            raise Blocked("Use a previously saved game distinct from the current active game")
    else:
        args.saved_game_id = matching[0]["saved_game_id"]
        if latest["session"] != matching[0]["session"]:
            raise Blocked("Service restarted during replay; use a new window")
    append(run / "replay.jsonl", {"kind": args.action, "window": args.window,
           "session": latest["session"], "saved_game_id": args.saved_game_id,
           "state": state, "snapshot": snapshot})
    print(f"Replay window {args.window}: {args.action}. No command was sent to the application.")
    return 0


def evaluate(run, args):
    report = Report(33)
    stopped_observer_check(report, events(run))
    marks = [m for m in read_jsonl(run / "replay.jsonl") if m["window"] == args.window]
    if len(marks) != 2 or [m["kind"] for m in marks] != ["begin", "end"]:
        raise Blocked("Need exactly one begin and end marker for this replay window")
    begin, end = marks
    trace = [e for e in events(run) if e["session"] == begin["session"] and
             begin["monotonic_ns"] <= e["monotonic_ns"] <= end["monotonic_ns"]]
    if not trace:
        raise Blocked("No observations inside replay window")
    saved_id = begin["saved_game_id"]
    saved = game_record(begin["snapshot"], saved_id)
    game, moves = saved["game"], saved["moves"]
    active_id = begin["state"]["game_id"]
    columns = ("game_id", "fen", "moves", "active", "paused", "clocks", "result", "restore")
    baseline = {k: begin["state"][k] for k in columns}
    states = [e["state"] for e in trace if e["kind"] == "state"] + [end["state"]]
    report.check("active game's accepted state and paused clocks preserved throughout",
                 bool(states) and all({k: s[k] for k in columns} == baseline for s in states),
                 f"compared {len(states)} observed states")
    report.check("active and saved database records unchanged",
                 game_record(begin["snapshot"], active_id) == game_record(end["snapshot"], active_id)
                 and saved == game_record(end["snapshot"], saved_id), "all game/move columns compared")
    writes = [e for e in trace if e["kind"] == "call" and
              e.get("operation") in {"GameSession.commit", "GameSession.end", "GameStore.move", "GameStore.checkpoint"}]
    report.check("no accepted-state write attempted during replay", not writes, f"write/commit attempts={len(writes)}")
    commands = [e for e in trace if e["kind"] == "serial_request"]
    dangerous = [e["command"] for e in commands if e["command"].split()[0].upper() in MOVEMENT]
    report.check("no movement commands attempted during replay", not dangerous,
                 f"observed {len(commands)} serial requests; actuator commands={dangerous}")
    report.check("live command observation coverage", bool(commands) and any(
                 e["command"].split()[0] == "PING" for e in commands) and any(
                 e["kind"] == "serial_reply" and e.get("frame_kind") in {"BOARD", "SNAPSHOT", "STATUS"} for e in trace),
                 "requires live heartbeat and MCU replies; an empty trace cannot prove no commands", missing=True)
    replies = [e["message"] for e in trace if e["kind"] == "ui_reply"]
    histories = [r for r in replies if r.get("type") == "history"]
    report.check("native History received designated saved details", any(
                 g["id"] == saved_id and g["white"] == game["white_name"]
                 and g["black"] == game["black_name"] and g["result"] == game["result"]
                 for h in histories for g in h["games"]), "production History reply observed", missing=True)
    reviews = [r for r in replies if r.get("type") == "review" and r.get("game_id") == saved_id]
    expected = {0: (game["initial_fen"], ""), **{m["ply"]: (m["fen"], m["uci"]) for m in moves}}
    report.check("every replay response matches saved positions/moves", bool(reviews) and all(
                 r["ply"] in expected and (r["fen"], r["move"]) == expected[r["ply"]]
                 and r["total"] == len(moves) and r["white"] == game["white_name"]
                 and r["black"] == game["black_name"] for r in reviews),
                 f"review replies={len(reviews)}", missing=not reviews)
    plies = [r["ply"] for r in reviews]
    # Consecutive +1 and -1 traversal, not a set of arbitrary jumps to selected positions.
    def contains(sequence):
        return any(plies[i:i+len(sequence)] == sequence for i in range(len(plies)-len(sequence)+1))
    report.check("step-by-step forward and backward traversal", contains(list(range(len(moves)+1)))
                 and contains(list(range(len(moves), -1, -1))), f"observed plies={plies}", missing=True)
    report.check("native touchscreen visibly showed details and each step", bool(
                 attachments(run, "replay-visible", args.window)),
                 "operator video/notes must cover this window; service replies alone do not prove rendering", missing=True)
    report.check("final hardware documented", bool(attachments(run, "hardware")),
                 "final Pi 5, touchscreen and real board session", missing=True)
    report.check("complete observer coverage", not any(e["kind"] == "observer_error" for e in
                 events(run) if e["session"] == begin["session"]), "any observation error blocks verification", missing=True)
    return report.finish(run)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("begin", "end", "evaluate"):
        item = sub.add_parser(action)
        run_argument(item)
        item.add_argument("--window", required=True)
        if action == "begin":
            item.add_argument("--saved-game-id", type=int, required=True)
    args = parser.parse_args()
    run, manifest = load_run(args.run)
    return evaluate(run, args) if args.action == "evaluate" else marker(run, manifest, args)


if __name__ == "__main__":
    raise SystemExit(cli(main))
