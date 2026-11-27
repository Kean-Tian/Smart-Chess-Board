"""TIDR #23: audit real legal guidance and explicitly bounded response timings."""
import sys

sys.dont_write_bytecode = True
from common.runtime import cli
from common.move_demo import accepted, model, paired, queries, record_equal, run_main, sensor_events

EXPECTED = {"e2": ["e3", "e4"], "g1": ["f3", "h3"], "a1": []}


def evaluate_case(report, begin, end, trace):
    label, source = begin["window"], begin["case"]
    baseline = begin["state"]
    lifts = [(c, r) for c, r in paired(trace, "GameSession.event")
             if c["data"].get("payload") == f"LIFT {source}"]
    report.check(f"{label}: actual identified MCU lift", any(
                 c["data"].get("payload") == f"LIFT {source}" for c, r in sensor_events(trace)),
                 "requires reader frame and original service dispatch", missing=True)
    if not lifts:
        report.check(f"{label}: lift reached validator", False, "physically lift the designated piece", missing=True)
        return
    legal, _, _ = model(baseline)
    expected = sorted({move[2:4] for move in legal if move[:2] == source})
    report.check(f"{label}: authoritative expected destinations", expected == EXPECTED[source],
                 f"native Game.legal_moves(): {expected}")
    for index, (call, ret) in enumerate(lifts, 1):
        state = ret["data"]["state"]
        square = (int(source[1]) - 1) * 8 + ord(source[0]) - ord("a")
        report.check(f"{label} lift {index}: only designated square lifted",
                     call["data"]["state"]["mask"] == baseline["mask"] & ~(1 << square)
                     and not state["ambiguous"] and not state["restore"],
                     "actual occupancy must match the standard position with this piece absent")
        returns = [e for e in queries(trace, call["token"]) if e["operation"] == "Game.legal_moves"
                   and e["phase"] == "return"]
        report.check(f"{label} lift {index}: production guidance set correct", call["data"]["state"]["guidance"]
                     and state["legal_source"] == source and state["legal_destinations"] == expected
                     and bool(returns) and sorted({m[2:4] for m in returns[0]["value"] if m[:2] == source}) == expected,
                     f"observed={state['legal_destinations']}, expected={expected}")
        received = call["data"].get("received_ns")
        available = ret["observed_ns"]
        bound = begin["bound_start_ns"]
        if received is None or not (bound <= received <= call["observed_ns"] <= available):
            report.check(f"{label} lift {index}: response timing observable", False,
                         "need the real correlated frame timestamp and valid monotonic endpoint order", missing=True)
            continue
        pi_ms = (available - received) / 1e6
        full_upper_ms = (available - bound) / 1e6
        query_entries = [q for q in queries(trace, call["token"]) if q["phase"] == "call"]
        lower_ms = (min(q["observed_ns"] for q in query_entries) - received) / 1e6 if query_entries else None
        detail = {"source": source, "received_ns": received, "available_upper_ns": available,
                  "pre_action_marker_ns": bound, "pi_receive_to_availability_upper_ms": pi_ms,
                  "pre_action_to_availability_upper_ms": full_upper_ms,
                  "pi_receive_to_rule_query_lower_ms": lower_ms,
                  "deadline_ms": 500, "includes_observer_overhead": True}
        # The firmware provides no identification timestamp. Pi receipt is later,
        # so receipt-only timing cannot prove the entire required deadline.
        if lower_ms is not None and lower_ms > 500:
            report.check(f"{label} lift {index}: response <=500 ms", False, detail)
        else:
            report.check(f"{label} lift {index}: response <=500 ms", full_upper_ms <= 500,
                         detail, missing=True)
    report.check(f"{label}: no accepted game/record change", accepted(end["state"]) == accepted(baseline)
                 and record_equal(end["snapshot"], begin["snapshot"], baseline["game_id"]),
                 "lifting a piece produces guidance, not a committed move")


def main():
    return run_main(23, ("e2", "g1", "a1"), evaluate_case)


if __name__ == "__main__":
    raise SystemExit(cli(main))
