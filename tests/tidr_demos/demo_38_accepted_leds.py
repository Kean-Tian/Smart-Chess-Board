"""TIDR #38: post-persistence accepted indications, replacement and clearing."""
import sys

sys.dont_write_bytecode = True
from common.runtime import cli
from common.display_clock_demo import pairs
from common.led_demo import accepted_anchor, optical, production_command, run_main


def evaluate_case(report, begin, end, trace, docs):
    label = begin["window"]
    accepted = [(c, r) for c, r in pairs(trace, "GameSession.commit") if r["value"] is True]
    moves = [c["data"].get("move") for c, r in accepted]
    report.check(label + ": both legal moves in order", moves[:2] == ["e2e4", "e7e5"], str(moves), missing=len(moves) < 2)
    for c, r in accepted[:2]:
        move = c["data"]["move"]
        lower = accepted_anchor(report, trace, label, c, r)
        command = f"MARK {move[:2]} {move[2:4]} LEGAL"
        report.check(label + ": accepted feedback selected", r["state"]["feedback_command"] == command, command)
        production_command(report, trace, label, command, r["observed_ns"])
        optical(report, docs, label, "accepted", c["token"], {move[:2]: "blue", move[2:4]: "green"},
                lower, r["observed_ns"] if lower is not None else None)
        if lower is None:
            report.check(label + ": accepted optical timing", False, "no verified post-persistence anchor", missing=True)
    illegal = [(c, r) for c, r in pairs(trace, "GameSession.commit") if r["value"] is False and
               r["state"]["restore"] and "Illegal" in r["state"]["message"]]
    report.check(label + ": actual illegal-feedback comparison", bool(illegal), "after e7e5 physically attempt g1g3", missing=True)
    for c, r in illegal:
        move = c["data"]["move"]
        command = f"MARK {move[:2]} {move[2:4]} ILLEGAL"
        production_command(report, trace, label, command, r["observed_ns"])
        optical(report, docs, label, "illegal-comparison", c["token"], {move[:2]: "red", move[2:4]: "red"})
    endings = [(c, r) for c, r in pairs(trace, "GameSession.end") if c["state"]["active"] and not r["state"]["active"]]
    report.check(label + ": game completion captured", bool(endings), "End through native UI after restoring the rejected move", missing=True)
    for c, r in endings:
        report.check(label + ": completion selects clear", r["state"]["feedback_command"] == "LED_CLEAR", r["state"]["feedback_command"])
        optical(report, docs, label, "end", c["token"], {})
    prepared = [(c, r) for c, r in pairs(trace, "GameSession.prepare") if endings and
                c["observed_ns"] > endings[0][1]["observed_ns"]]
    report.check(label + ": new game preparation captured", bool(prepared), "prepare next game without restarting the service", missing=True)
    for c, r in prepared:
        report.check(label + ": preparation keeps clear", r["state"]["feedback_command"] == "LED_CLEAR", r["state"]["feedback_command"])
        optical(report, docs, label, "prepare", c["token"], {})
    # Every optical accepted observation covers the ENTIRE array: this also
    # verifies removal of prior indications and absence of extra squares.


def main():
    return run_main(38, "accepted", evaluate_case)


if __name__ == "__main__":
    raise SystemExit(cli(main))
