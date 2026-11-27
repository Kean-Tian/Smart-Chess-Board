"""TIDR #28: original monotonic clocks, accepted transitions and physical USB loss."""
import sys

sys.dont_write_bytecode = True
from common.runtime import cli
from common.display_clock_demo import pairs, run_main, transition_bound
from common.move_demo import sensor_events


def audit_ticks(trace, game_id):
    errors, decreases = [], [0, 0]
    holds = {"paused": 0, "disconnected": 0, "ended": 0}
    for operation in ("GameSession.tick", "GameSession.tick_clock_only"):
        for call, ret in pairs(trace, operation):
            before, after = call["state"], ret["state"]
            if before["game_id"] != game_id or None in before["clocks"] or None in after["clocks"]:
                continue
            side = (0 if before["fen"].split()[1] == "w" else 1) if before["active"] and not before["paused"] else None
            delta = [b - a for a, b in zip(before["clocks"], after["clocks"])]
            if any(d > 0 or (i != side and d != 0) for i, d in enumerate(delta)):
                errors.append({"token": call["token"], "before": before["clocks"], "after": after["clocks"], "side": side})
            if side is not None and delta[side] < 0:
                decreases[side] += 1
            elif side is None and delta == [0, 0]:
                holds["ended" if not before["active"] else "disconnected" if not before["connected"] else "paused"] += 1
    previous = None
    for e in sorted(trace, key=lambda e: e.get("observed_ns", e["monotonic_ns"])):
        state = e.get("state")
        if not state or state["game_id"] != game_id or None in state["clocks"]:
            continue
        if previous is not None:
            increased = any(b > a for a, b in zip(previous["clocks"], state["clocks"]))
            frozen = ((not previous["active"] and not state["active"]) or
                      (previous["paused"] and state["paused"])) and state["clocks"] != previous["clocks"]
            if increased or frozen:
                errors.append({"token": e.get("token"), "between_observations": True,
                               "before": previous["clocks"], "after": state["clocks"]})
        previous = state
    return errors, decreases, holds


def ui_action(trace, command, child_call):
    return any(c["data"].get("production_ui_dispatch") and c["data"].get("request", {}).get("cmd") == command
               and c["observed_ns"] <= child_call["observed_ns"] <= r["observed_ns"]
               for c, r in pairs(trace, "UiCore.handle"))


def event_start(trace, command, child_call):
    for c, r in pairs(trace, "UiCore.handle"):
        if (c["data"].get("production_ui_dispatch") and c["data"].get("request", {}).get("cmd") == command
                and c["observed_ns"] <= child_call["observed_ns"] <= r["observed_ns"]):
            return c
    for c, r in pairs(trace, "UiCore.latch_fault"):
        if c["observed_ns"] <= child_call["observed_ns"] <= r["observed_ns"]:
            return c
    return child_call


def evaluate_case(report, run, begin, end, trace):
    label = begin["window"]
    starts = [(c, r) for c, r in pairs(trace, "GameSession.start") if r["state"]["active"]]
    report.check(label + ": five-minute game start captured", bool(starts), "begin before Start", missing=True)
    if not starts:
        return
    start_call, start = starts[0]
    game_id = start["state"]["game_id"]
    report.check(label + ": original five-minute PvP clocks", start["state"]["minutes"] == 5 and
                 start["state"]["mode"] == "pvp" and start["state"]["clocks"] == [300000, 300000],
                 {"raw_ms": start["state"]["clocks"], "rounded_ms": start["state"]["rounded_clocks_ms"]})
    report.check(label + ": started through native UI", ui_action(trace, "start", start_call),
                 "original native Server request path", missing=True)
    errors, decreases, holds = audit_ticks(trace, game_id)
    report.check(label + ": only active clock decreases; clocks never reset/increase in ticks", not errors,
                 {"errors": errors, "decreasing_samples_white_black": decreases})
    report.check(label + ": both active turns observed", all(n > 0 for n in decreases), str(decreases), missing=True)
    for mode, count in holds.items():
        report.check(f"{label}: both clocks frozen while {mode}", count > 0, f"exact raw-value hold samples={count}", missing=True)
    states = [e["state"] for e in trace if e["kind"] == "dc_state" and e["observed_ns"] > start["observed_ns"]]
    report.check(label + ": one game throughout", bool(states) and all(s["game_id"] == game_id for s in states),
                 "do not prepare another game inside the clock window")
    moves = [(c, r) for c, r in pairs(trace, "GameSession.commit") if r["value"] is True and r["state"]["game_id"] == game_id]
    report.check(label + ": accepted clock-switch event", bool(moves), "physically play e2e4", missing=True)
    for c, r in moves:
        before_side = c["state"]["fen"].split()[1]
        transition_bound(report, label + ": clock switch " + c["token"], c, r,
                         lambda s: s["fen"].split()[1] != before_side and not s["paused"])
    report.check(label + ": physical accepted move report", any(c["data"].get("payload") == "MOVE e2e4"
                 for c, r in sensor_events(trace)), "no synthetic event substitution", missing=True)
    pauses = [(c, r) for c, r in pairs(trace, "GameSession.pause") if not c["state"]["paused"]]
    manual = [(c, r) for c, r in pauses if ui_action(trace, "pause", c)]
    report.check(label + ": native UI pause action", bool(manual), "existing Pause button", missing=True)
    for c, r in pauses:
        transition_bound(report, label + ": pause " + c["token"], event_start(trace, "pause", c), r, lambda s: s["paused"])
    resumes = [(c, r) for c, r in pairs(trace, "GameSession.resume") if c["state"]["paused"] and not r["state"]["paused"]]
    report.check(label + ": manual and post-disconnect resumes observed", len(resumes) >= 2, f"resumes={len(resumes)}", missing=True)
    for c, r in resumes:
        report.check(label + ": resume preserves exact raw remaining times " + c["token"],
                     c["state"]["clocks"] == r["state"]["clocks"],
                     {"before_raw_ms": c["state"]["clocks"], "after_raw_ms": r["state"]["clocks"]})
        previous_pause = max([p["observed_ns"] for p, _ in pauses if p["observed_ns"] < c["observed_ns"]] or [0])
        resume_requests = [a for a, b in pairs(trace, "UiCore.handle") if
                           a["data"].get("production_ui_dispatch") and
                           a["data"].get("request", {}).get("cmd") == "resume" and
                           previous_pause < a["observed_ns"] < c["observed_ns"]]
        report.check(label + ": explicit native Resume request " + c["token"], bool(resume_requests),
                     "resume is asynchronous; verify earlier native request, not a direct API call", missing=True)
        next_stop = min([a["observed_ns"] for op in ("GameSession.pause", "GameSession.end")
                         for a, _ in pairs(trace, op) if a["observed_ns"] > r["observed_ns"]] or [2**63])
        resumed_ticks = [(a, b) for op in ("GameSession.tick", "GameSession.tick_clock_only") for a, b in pairs(trace, op)
                         if r["observed_ns"] < a["observed_ns"] < b["observed_ns"] < next_stop and
                         a["state"]["active"] and not a["state"]["paused"] and
                         any(y < x for x, y in zip(a["state"]["clocks"], b["state"]["clocks"]))]
        report.check(label + ": clock actually runs after Resume " + c["token"], bool(resumed_ticks),
                     f"running tick samples={len(resumed_ticks)}", missing=True)
    lost = [(c, r) for c, r in pairs(trace, "GameSession.connection") if c["data"].get("connected") is False
            and c["data"].get("production_io_dispatch") and c["state"]["game_id"] == game_id]
    failures = [e for e in trace if e["kind"] == "dc_link_failure" and not e["intentional_stop"]]
    disconnect_buttons = [c for c, r in pairs(trace, "UiCore.handle") if c["data"].get("request", {}).get("cmd") == "disconnect"]
    report.check(label + ": physical link failure, not UI Disconnect", bool(lost) and bool(failures) and not disconnect_buttons,
                 {"detected_connections_lost": len(lost), "serial_worker_errors": len(failures)}, missing=True)
    if lost:
        c, r = lost[0]
        report.check(label + ": link loss pauses both clocks", r["state"]["paused"] and not r["state"]["connected"],
                     {"detected_loss_ns": c["observed_ns"], "paused_upper_ns": r["observed_ns"],
                      "raw_remaining_ms": r["state"]["clocks"], "no_unplug_detection_deadline_specified": True})
        recovered = [(a, b) for a, b in pairs(trace, "GameSession.connection") if
                     a["data"].get("connected") is True and a["data"].get("production_io_dispatch") and
                     a["observed_ns"] > r["observed_ns"]]
        later_resume = [(a, b) for a, b in resumes if a["observed_ns"] > r["observed_ns"]]
        report.check(label + ": reconnect does not reset remaining times", bool(recovered) and all(
                     b["state"]["clocks"] == r["state"]["clocks"] and b["state"]["paused"] for a, b in recovered),
                     "same game, both clocks remain paused", missing=not recovered)
        report.check(label + ": post-disconnect resume preserves frozen times", bool(later_resume) and
                     later_resume[0][0]["state"]["clocks"] == r["state"]["clocks"],
                     "compare exact backend values, not displayed seconds", missing=not later_resume)
        resets = [a for a, b in pairs(trace, "UiCore.handle") if a["data"].get("production_ui_dispatch") and
                  a["data"].get("request", {}).get("cmd") == "reset_fault" and a["observed_ns"] > r["observed_ns"]]
        report.check(label + ": normal fault resolution workflow observed", bool(resets),
                     "resolve cause, reconnect, Reset fault, then explicit Resume; fixture never resets for you", missing=True)
    ends = [(c, r) for c, r in pairs(trace, "GameSession.end") if c["state"]["active"] and not r["state"]["active"]]
    report.check(label + ": end event captured", bool(ends), "End through native UI, then wait for frozen samples", missing=True)
    for c, r in ends:
        report.check(label + ": ended through native UI " + c["token"], ui_action(trace, "end", c),
                     "original End confirmation workflow", missing=True)
        transition_bound(report, label + ": stop " + c["token"], event_start(trace, "end", c), r, lambda s: not s["active"])


def main():
    return run_main(28, ("clock-workflow",), evaluate_case)


if __name__ == "__main__":
    raise SystemExit(cli(main))
