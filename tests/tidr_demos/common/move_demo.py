"""Read-only window markers and analysis shared by #20, #22 and #23."""
import argparse
import time

from .runtime import (Blocked, Report, append, attachments, bootstrap, database_snapshot,
                      events, game_record, load_run, read_jsonl, run_argument, stopped_observer_check)


def initial_position():
    bootstrap()
    from scb_rules import Game
    from board_game import occupancy, fen_board
    try:
        with Game() as game:
            fen = game.fen()
    except OSError as exc:
        raise Blocked(f"Production native rules unavailable: {exc}") from exc
    return fen, occupancy(fen_board(fen))


def accepted(state):
    return {k: state[k] for k in ("game_id", "fen", "moves", "result")}


def model(state, move=None):
    """Audit captured history using original native rules, never a second validator."""
    bootstrap()
    from scb_rules import Game
    from board_game import expected_occupancy
    with Game() as game:
        for prior in state["moves"]:
            if not game.play(prior):
                raise Blocked("Captured history cannot be reconstructed by production rules")
        if game.fen() != state["fen"]:
            raise Blocked("Captured FEN/history are inconsistent")
        legal = game.legal_moves()
        occupancy = expected_occupancy(game.fen(), move) if move in legal else None
        post = None
        if move in legal:
            game.play(move)
            post = game.fen()
        return legal, occupancy, post


def marker(run, manifest, args, tidr):
    marks = [m for m in read_jsonl(run / "move_windows.jsonl") if m["window"] == args.window]
    if args.action == "begin" and marks:
        raise Blocked("Window names must be unique across all move-validation demos")
    if args.action == "end" and (len(marks) != 1 or marks[0]["tidr"] != tidr):
        raise Blocked("This TIDR has no single open window with that name")
    trace = events(run)
    latest = next((e for e in reversed(trace) if e["kind"] == "mv_state"), None)
    if latest is None or time.time_ns() - latest["wall_ns"] > 2_000_000_000:
        raise Blocked("Need fresh native-UI state from run_move_validation_service.py")
    state = latest["state"]
    if not state["active"] or state["paused"] or not state["connected"]:
        raise Blocked("Need an active, connected, unpaused physical PvP game")
    snapshot = database_snapshot(manifest["database"])
    if args.action == "begin":
        fen, mask = initial_position()
        row = game_record(snapshot, state["game_id"])["game"]
        if (state["fen"] != fen or state["moves"] or state["mask"] != mask or state["ambiguous"]
                or state["restore"] or row is None or row["mode"] != "pvp" or row["minutes"] != 0):
            raise Blocked("Begin from verified standard physical position: PvP, No clock, no unresolved errors")
        if tidr == 23 and not state["guidance"]:
            raise Blocked("Enable Guidance in the real UI before starting a #23 window")
    elif latest["session"] != marks[0]["session"]:
        raise Blocked("Service restarted during window")
    now = time.monotonic_ns()
    append(run / "move_windows.jsonl", {"tidr": tidr, "kind": args.action,
           "window": args.window, "case": args.case if args.action == "begin" else marks[0]["case"],
           "session": latest["session"], "bound_start_ns": now,
           "state": state, "snapshot": snapshot})
    print(f"TIDR #{tidr} {args.window}: {args.action}; monotonic_ns={now}")
    if args.action == "begin":
        print("Marker recorded. Perform the physical action NOW. The marker never sends a hardware/UI command.")
    return 0


def paired(trace, operation):
    calls = {e["token"]: e for e in trace if e["kind"] == "mv_call" and e["operation"] == operation}
    return [(calls[e["token"]], e) for e in trace if e["kind"] == "mv_return" and
            e.get("token") in calls and e["operation"] == operation]


def between(trace, first, last):
    return [e for e in trace if first <= e["monotonic_ns"] <= last]


def queries(trace, token):
    return [e for e in trace if e["kind"] == "mv_query" and e.get("parent_token") == token]


def sensor_events(trace):
    result = []
    for call, ret in paired(trace, "GameSession.event"):
        data = call["data"]
        backed = any(e["kind"] == "serial_reply" and e.get("frame_kind") == "EVENT"
                     and e.get("payload") == data["payload"] and
                     round(e["received_at"] * 1e9) == data.get("received_ns") for e in trace)
        if data.get("production_serial_dispatch") and backed:
            result.append((call, ret))
    return result


def ui_confirmation(trace, commit_call):
    """Original Server.run -> UiCore.handle(commit) must enclose the candidate commit."""
    return any(c["data"].get("production_ui_dispatch") and
               c["data"].get("request", {}).get("cmd") == "commit" and
               c["data"]["request"].get("move") == commit_call["data"].get("move") and
               c["monotonic_ns"] <= commit_call["monotonic_ns"] <= r["monotonic_ns"]
               for c, r in paired(trace, "UiCore.handle"))


def record_equal(snapshot, baseline, game_id):
    return game_record(snapshot, game_id) == game_record(baseline, game_id)


def evaluate_windows(run, args, tidr, required, evaluator):
    report = Report(tidr)
    all_events = events(run)
    marks = [m for m in read_jsonl(run / "move_windows.jsonl") if m["tidr"] == tidr
             and (not args.windows or m["window"] in args.windows)]
    names = list(dict.fromkeys(m["window"] for m in marks))
    completed = []
    for name in names:
        window = [m for m in marks if m["window"] == name]
        if len(window) != 2 or [m["kind"] for m in window] != ["begin", "end"]:
            report.check(f"{name}: complete observation window", False, "missing begin/end", missing=True)
            continue
        begin, end = window
        session_trace = [e for e in all_events if e["session"] == begin["session"]]
        trace = between(session_trace, begin["bound_start_ns"], end["bound_start_ns"])
        completed.append(begin["case"])
        stopped_observer_check(report, session_trace, name)
        report.check(f"{name}: observation errors absent", not any(
                     e["kind"] == "observer_error" for e in session_trace), "errors block reliable analysis", missing=True)
        report.check(f"{name}: final hardware and visible UI evidence", bool(attachments(run, "hardware", name)),
                     "TA-reviewed actual video/notes must cover this named window and final hardware", missing=True)
        report.check(f"{name}: real sensor dispatch captured", bool(sensor_events(trace)),
                     "requires correlated original reader EVENT and UiCore.update dispatch", missing=True)
        states = [e["state"] for e in trace if e["kind"] == "mv_state"] + [end["state"]]
        report.check(f"{name}: same active game throughout", bool(states) and all(
                     s["game_id"] == begin["state"]["game_id"] and s["active"] and not s["paused"]
                     for s in states), "no ending, restarting or switching games inside a window")
        evaluator(report, begin, end, trace)
    report.check("all required cases recorded", set(required) <= set(completed),
                 f"required={list(required)}, completed={completed}", missing=True)
    if args.windows:
        report.check("all selected windows found", set(args.windows) <= set(names), str(args.windows), missing=True)
    return report.finish(run)


def run_main(tidr, cases, evaluator):
    parser = argparse.ArgumentParser(description=f"TIDR #{tidr}: manually mark real UI actions, then analyze; no device opens")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("begin", "end", "evaluate"):
        item = sub.add_parser(action)
        run_argument(item)
        if action == "evaluate":
            item.add_argument("--windows", nargs="+", help="Analyze only these named windows")
        else:
            item.add_argument("--window", required=True)
            if action == "begin":
                item.add_argument("--case", choices=cases, required=True)
    args = parser.parse_args()
    run, manifest = load_run(args.run)
    if manifest["purpose"] != "records":
        raise Blocked("Move-validation demos require a records-purpose isolated run")
    if args.action == "evaluate":
        return evaluate_windows(run, args, tidr, cases, evaluator)
    return marker(run, manifest, args, tidr)
