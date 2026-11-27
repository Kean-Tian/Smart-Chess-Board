"""Read-only measurement windows and bounded-timestamp analysis for #27/#28."""
import argparse
import json
import time

from .runtime import (Blocked, Report, append, attachments, cli, database_snapshot, events,
                      load_run, read_jsonl, run_argument, stopped_observer_check)


def pairs(trace, operation):
    calls = {e["token"]: e for e in trace if e["kind"] == "dc_call" and e["operation"] == operation}
    return [(calls[r["token"]], r) for r in trace if r["kind"] == "dc_return" and
            r["operation"] == operation and r.get("token") in calls]


def duration_check(report, name, lower_ns, upper_ns, limit_ms, detail=None):
    if lower_ns < 0 or upper_ns < lower_ns:
        report.check(name, False, "invalid or contradictory endpoint bounds", missing=True)
    else:
        detail = {"latency_lower_ms": lower_ns / 1e6, "latency_upper_ms": upper_ns / 1e6,
                  "limit_ms": limit_ms, **(detail or {})}
        report.check(name, upper_ns <= limit_ms * 1e6, detail,
                     missing=lower_ns <= limit_ms * 1e6)


def transition_bound(report, name, call, ret, predicate, limit_ms=500):
    report.check(name + ": expected backend effect", predicate(ret["state"]),
                 {"token": call["token"], "operation": call["operation"]})
    # Entry precedes the accepted decision; return follows the effect. This is
    # an upper bound, not a fabricated exact transition timestamp.
    duration_check(report, name + f": <= {limit_ms} ms", 0,
                   ret["observed_ns"] - call["observed_ns"], limit_ms,
                   {"backend_token": call["token"], "start_ns": call["observed_ns"],
                    "effect_upper_ns": ret["observed_ns"], "includes_observer_overhead": True})


def mark(run, manifest, args, tidr):
    previous = [m for m in read_jsonl(run / "display_clock_windows.jsonl") if m["window"] == args.window]
    if args.action == "begin" and previous:
        raise Blocked("Use a new unique window name")
    if args.action == "end" and (len(previous) != 1 or previous[0]["tidr"] != tidr):
        raise Blocked("Need one matching open window")
    latest = next((e for e in reversed(events(run)) if e["kind"] == "dc_state"), None)
    if latest is None or time.time_ns() - latest["wall_ns"] > 2_000_000_000:
        raise Blocked("Need fresh real-UI state from run_display_clock_service.py")
    if args.action == "end" and latest["session"] != previous[0]["session"]:
        raise Blocked("Service changed during the window")
    append(run / "display_clock_windows.jsonl", {"tidr": tidr, "kind": args.action,
           "window": args.window, "case": args.case if args.action == "begin" else previous[0]["case"],
           "session": latest["session"], "state": latest["state"],
           "snapshot": database_snapshot(manifest["database"])})
    print(f"TIDR #{tidr}: {args.action} {args.window}; observation only, no application command sent")
    return 0


def evaluate(run, args, tidr, required_cases, case_evaluator):
    report = Report(tidr)
    trace = events(run)
    marks = [m for m in read_jsonl(run / "display_clock_windows.jsonl") if m["tidr"] == tidr
             and (not args.windows or m["window"] in args.windows)]
    names = list(dict.fromkeys(m["window"] for m in marks))
    cases = []
    for name in names:
        window = [m for m in marks if m["window"] == name]
        if len(window) != 2 or [m["kind"] for m in window] != ["begin", "end"]:
            report.check(name + ": complete window", False, "missing begin/end", missing=True)
            continue
        begin, end = window
        session = [e for e in trace if e["session"] == begin["session"]]
        current = [e for e in session if begin["monotonic_ns"] <= e["monotonic_ns"] <= end["monotonic_ns"]]
        cases.append(begin["case"])
        stopped_observer_check(report, session, name)
        report.check(name + ": no observation errors", not any(e["kind"] == "observer_error" for e in session),
                     "incomplete observations block verification", missing=True)
        report.check(name + ": final hardware evidence", bool(attachments(run, "hardware", name)),
                     "operator/TA reviewed physical display, board and actions", missing=True)
        case_evaluator(report, run, begin, end, current)
    report.check("all required scenarios", set(required_cases) <= set(cases),
                 {"required": list(required_cases), "recorded": cases}, missing=True)
    if args.windows:
        report.check("all selected windows exist", set(args.windows) <= set(names), str(args.windows), missing=True)
    return report.finish(run)


def run_main(tidr, cases, evaluator, importer=None):
    parser = argparse.ArgumentParser(description=f"TIDR #{tidr}: observe real native UI/backend; no device/socket opens")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("begin", "end", "evaluate") + (("import-visibility",) if importer else ()):
        item = sub.add_parser(action)
        run_argument(item)
        if action == "evaluate":
            item.add_argument("--windows", nargs="+")
        elif action == "import-visibility":
            item.add_argument("--file", required=True)
        else:
            item.add_argument("--window", required=True)
            if action == "begin":
                item.add_argument("--case", choices=cases, required=True)
    args = parser.parse_args()
    run, manifest = load_run(args.run)
    if manifest["purpose"] != "records":
        raise Blocked("Use an isolated records-purpose run")
    if args.action == "evaluate":
        return evaluate(run, args, tidr, cases, evaluator)
    if args.action == "import-visibility":
        return importer(run, args.file)
    return mark(run, manifest, args, tidr)
