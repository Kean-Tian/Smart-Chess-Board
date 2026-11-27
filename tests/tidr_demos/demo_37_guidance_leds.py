"""TIDR #37: game-driven legal destinations and actual full-board illumination."""
import sys

sys.dont_write_bytecode = True
from common.runtime import cli
from common.display_clock_demo import pairs
from common.move_demo import model, paired
from common.led_demo import accepted_anchor, optical, production_command, run_main


def evaluate_case(report, begin, end, trace, docs):
    label = begin["window"]
    lifts = [(c, r) for c, r in paired(trace, "GameSession.event") if c["data"].get("payload", "").startswith("LIFT ")]
    seen = []
    expected_cases = {"e2": ["e3", "e4"], "g1": ["f3", "h3"], "a1": []}
    for call, ret in lifts:
        source = call["data"]["payload"].split()[1]
        if source not in expected_cases:
            continue
        seen.append(source)
        before, state = call["data"]["state"], ret["data"]["state"]
        legal, _, _ = model(before)
        destinations = sorted({m[2:4] for m in legal if m[:2] == source})
        report.check(label + ": native guidance " + source, before["guidance"] and
                     destinations == expected_cases[source] and state["legal_destinations"] == destinations,
                     {"expected": destinations, "observed": state["legal_destinations"]})
        inputs = [e for e in trace if e["kind"] == "led_input" and e["observed_ns"] >= ret["observed_ns"] and
                  e["desired"] == state["feedback_command"] and e["state"]["legal_source"] == source and
                  e["state"]["moves"] == state["moves"]]
        report.check(label + ": feedback controller received destinations " + source, bool(inputs),
                     "original UiCore.feedback_update input observation", missing=True)
        if inputs:
            controller = inputs[0]
            production_command(report, trace, label, state["feedback_command"], controller["observed_ns"])
            # Reception lies between event handling entry (before generation) and
            # first feedback-controller observation (before queue submission).
            optical(report, docs, label, "guidance", call["token"], {s: "green" for s in destinations},
                    call["observed_ns"], controller["observed_ns"])
    report.check(label + ": pawn/knight/blocked-rook cases captured", set(expected_cases) <= set(seen), str(seen), missing=True)
    returns = [(c, r) for c, r in pairs(trace, "GameSession.on_board") if c["state"]["legal_source"] in expected_cases
               and not r["state"]["legal_source"] and not r["state"]["restore"]
               and c["state"]["moves"] == r["state"]["moves"] and r["state"]["feedback_command"] == "LED_CLEAR"]
    returned = set()
    for c, r in returns:
        returned.add(c["state"]["legal_source"])
        production_command(report, trace, label, "LED_CLEAR", r["observed_ns"])
        optical(report, docs, label, "return", c["token"], {})
    report.check(label + ": returning each tested piece clears guidance", set(expected_cases) <= returned,
                 str(sorted(returned)), missing=True)
    moves = [(c, r) for c, r in pairs(trace, "GameSession.commit") if r["value"] is True and c["data"].get("move") == "e2e4"]
    report.check(label + ": legal move completes guidance", bool(moves), "lift e2 again, then physically complete e2e4", missing=True)
    for c, r in moves:
        accepted_anchor(report, trace, label, c, r)
        report.check(label + ": guidance replaced by legal feedback", r["state"]["feedback_command"] == "MARK e2 e4 LEGAL"
                     and r["state"]["legal_destinations"] == [], r["state"]["feedback_command"])
        production_command(report, trace, label, "MARK e2 e4 LEGAL", r["observed_ns"])
        optical(report, docs, label, "move-complete", c["token"], {"e2": "blue", "e4": "green"})


def main():
    return run_main(37, "guidance", evaluate_case)


if __name__ == "__main__":
    raise SystemExit(cli(main))
