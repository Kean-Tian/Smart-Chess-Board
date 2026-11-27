"""TIDR #39: actual rejected-move warning persists until full board restoration."""
import sys

sys.dont_write_bytecode = True
from common.runtime import cli
from common.display_clock_demo import pairs
from common.move_demo import accepted, record_equal, sensor_events
from common.led_demo import optical, production_command, run_main


def evaluate_case(report, begin, end, trace, docs):
    label = begin["window"]
    illegal = [(c, r) for c, r in pairs(trace, "GameSession.commit") if c["data"].get("move") == "e2e5"]
    report.check(label + ": illegal e2e5 reaches validator", bool(illegal), "standard-position physical attempt required", missing=True)
    if not illegal:
        return
    c, r = illegal[0]
    report.check(label + ": rejection selects red source/destination", r["value"] is False and
                 r["state"]["restore"] and r["state"]["feedback_command"] == "MARK e2 e5 ILLEGAL", r["state"]["message"])
    warning_commands = production_command(report, trace, label, "MARK e2 e5 ILLEGAL", r["observed_ns"])
    optical(report, docs, label, "rejected", c["token"], {"e2": "red", "e5": "red"})
    restored = [(a, b) for a, b in pairs(trace, "GameSession.on_board") if a["state"]["restore"] and
                not b["state"]["restore"] and a["observed_ns"] > r["observed_ns"]]
    report.check(label + ": full restoration confirmed", bool(restored), "restore all squares to accepted position", missing=True)
    if not restored:
        return
    a, b = restored[0]
    partial = [(x, y) for x, y in pairs(trace, "GameSession.on_board") if
               r["observed_ns"] < x["observed_ns"] < a["observed_ns"] and y["state"]["restore"] and
               y["state"]["mask"] & (1 << 12) and not y["state"]["mask"] & (1 << 36) and
               y["state"]["mask"] != begin["state"]["mask"]]
    report.check(label + ": partial restoration leaves another mismatch", bool(partial),
                 "return e5 pawn to e2 while d2 remains displaced", missing=True)
    seen_partial_masks = set()
    for x, y in partial:
        report.check(label + ": warning retained during partial restoration", y["state"]["feedback_command"] == "MARK e2 e5 ILLEGAL",
                     "no premature reset of the original rejected-move warning")
        # Periodic SCAN may reconfirm an unchanged partial board. One optical
        # annotation per distinct partial configuration plus continuous footage
        # is sufficient; do not demand duplicate annotations every polling cycle.
        if y["state"]["mask"] not in seen_partial_masks:
            seen_partial_masks.add(y["state"]["mask"])
            optical(report, docs, label, "partial", x["token"], {"e2": "red", "e5": "red"})
    actions = [(x, y) for x, y in pairs(trace, "UiCore.handle") if x["data"].get("production_ui_dispatch") and
               x["data"].get("request", {}).get("cmd") == "guidance" and
               r["observed_ns"] < x["observed_ns"] < a["observed_ns"]]
    further_moves = [(x, y) for x, y in sensor_events(trace) if
                     x["data"].get("payload", "").startswith("MOVE ") and
                     r["observed_ns"] < x["observed_ns"] < a["observed_ns"]]
    report.check(label + ": unrelated move or native Guidance action captured", bool(actions or further_moves),
                 "physically attempt another move or toggle Guidance while board is wrong", missing=True)
    hold_start = warning_commands[0]["observed_ns"] if warning_commands else r["observed_ns"]
    early = [e["command"] for e in trace if e["kind"] == "led_command" and
             hold_start <= e["observed_ns"] < a["observed_ns"] and e["command"] != "MARK e2 e5 ILLEGAL"]
    report.check(label + ": no premature clear/guidance replacement commands", not early, str(early))
    report.check(label + ": accepted game records unchanged", accepted(end["state"]) == accepted(begin["state"])
                 and record_equal(end["snapshot"], begin["snapshot"], begin["state"]["game_id"]),
                 "no rejected or restoration move was committed")
    production_command(report, trace, label, "LED_CLEAR", b["observed_ns"])
    optical(report, docs, label, "restored", a["token"], {})
    continuous = [d["persistence"] for d in docs if isinstance(d.get("persistence"), dict) and
                  d["persistence"].get("rejection_token") == c["token"] and
                  d["persistence"].get("restoration_token") == a["token"]]
    flags = ("continuous_video_review", "no_warning_gap", "warning_until_confirmation",
             "unrelated_actions_covered", "partial_restoration_covered", "cleared_only_after_restoration")
    report.check(label + ": continuous physical warning until confirmed restoration", bool(continuous) and all(
                 all(p.get(f) is True for f in flags) and p.get("frame_range") for p in continuous),
                 "continuous final-hardware optical evidence required; endpoint screenshots are insufficient",
                 missing=not continuous or any(p.get(f) is None for p in continuous for f in flags))


def main():
    return run_main(39, "rejected", evaluate_case)


if __name__ == "__main__":
    raise SystemExit(cli(main))
