"""TIDR #20: observe physical ambiguity and native touchscreen confirmations."""
import sys

sys.dont_write_bytecode = True
from common.runtime import cli, game_record
from common.move_demo import (accepted, between, model, paired, queries, record_equal,
                              run_main, sensor_events, ui_confirmation)


def evaluate_case(report, begin, end, trace):
    label, case = begin["window"], begin["case"]
    baseline, game_id = begin["state"], begin["state"]["game_id"]
    ambiguity = [(c, r) for c, r in paired(trace, "GameSession.event")
                 if c["data"].get("payload", "").startswith("AMBIGUOUS")]
    report.check(f"{label}: actual MCU AMBIGUOUS event", any(
                 c["data"]["payload"].startswith("AMBIGUOUS") for c, r in sensor_events(trace)),
                 "generic lift/move events do not substitute for ambiguity", missing=True)
    if not ambiguity:
        report.check(f"{label}: ambiguity reached validator", False, "repeat physical simultaneous change", missing=True)
        return
    ambiguous_call, ambiguous_return = ambiguity[0]
    state = ambiguous_return["data"]["state"]
    report.check(f"{label}: confirmation requested", state["ambiguous"] and
                 "confirm" in state["message"].lower() and accepted(state) == accepted(baseline),
                 state["message"])
    confirmations = [(c, r) for c, r in paired(trace, "GameSession.commit") if
                     c["monotonic_ns"] > ambiguous_return["monotonic_ns"] and c["data"].get("explicit")]
    if not confirmations:
        report.check(f"{label}: explicit confirmation observed", False, "use Confirm move in native UI", missing=True)
        return
    call, ret = confirmations[0]
    report.check(f"{label}: native UI confirmation path", ui_confirmation(trace, call),
                 "requires original Server.run -> UiCore.handle(commit) -> GameSession.commit", missing=True)
    wait = between(trace, ambiguous_return["monotonic_ns"], call["monotonic_ns"] - 1)
    changes = [e for e in wait if e["kind"] == "mv_state" and accepted(e["state"]) != accepted(baseline)]
    checks = [e for e in wait if e["kind"] == "mv_query"]
    writes = [e for e in wait if e["kind"] == "call" and e.get("operation") == "GameStore.move"]
    report.check(f"{label}: no candidate validation/write/advance before confirmation",
                 not changes and not checks and not writes and
                 accepted(call["data"]["state"]) == accepted(baseline) and
                 record_equal(call["data"]["snapshot"], begin["snapshot"], game_id),
                 f"state changes={len(changes)}, candidate rule/occupancy queries={len(checks)}, writes={len(writes)}")
    # Continuous accepted-board synchronization is distinct from validating an ambiguous candidate.
    report.check(f"{label}: ambiguous guard active at confirmation", call["data"]["state"]["ambiguous"],
                 "do not restore the whole initial board before confirming")
    move = call["data"]["move"]
    legal, expected_mask, post_fen = model(baseline, move)
    result = ret["data"]["state"]
    traced_checks = queries(trace, call["token"])
    rule_checks = [q for q in traced_checks if q["operation"] == "Game.legal_moves" and q["phase"] == "return"]
    report.check(f"{label}: production rules run after confirmation", bool(rule_checks),
                 "direct candidate query recorded", missing=True)
    if case == "valid":
        report.check(f"{label}: only confirmed matching legal move accepted", move == "e2e4" and
                     move in legal and call["data"]["state"]["mask"] == expected_mask
                     and ret["data"]["return"] is True and result["fen"] == post_fen
                     and result["moves"] == baseline["moves"] + [move] and not result["ambiguous"], str(move))
        saved = game_record(ret["data"]["snapshot"], game_id)
        report.check(f"{label}: accepted result persisted once", len(saved["moves"]) == 1 and
                     saved["moves"][0]["uci"] == move and saved["game"]["current_fen"] == post_fen,
                     "original GameStore write verified through separate read-only snapshot")
        report.check(f"{label}: no extra accepted moves", end["state"]["moves"] == ["e2e4"], str(end["state"]["moves"]))
    else:
        expected_move = "e2e5" if case == "invalid" else "e2e4"
        condition = move not in legal if case == "invalid" else (move in legal and
                     call["data"]["state"]["mask"] != expected_mask)
        report.check(f"{label}: designated invalid/mismatched confirmation", move == expected_move and condition,
                     f"move={move}, case={case}")
        report.check(f"{label}: rejected without accepted-state or DB changes", ret["data"]["return"] is False
                     and accepted(result) == accepted(baseline) and accepted(end["state"]) == accepted(baseline)
                     and record_equal(ret["data"]["snapshot"], begin["snapshot"], game_id)
                     and record_equal(end["snapshot"], begin["snapshot"], game_id), result["message"])
        if case == "mismatch":
            report.check(f"{label}: production candidate occupancy check observed", any(
                         q["operation"] == "expected_occupancy" and q["phase"] == "return"
                         and q["value"] == expected_mask for q in traced_checks),
                         "mask audit uses original expected_occupancy", missing=True)


def main():
    return run_main(20, ("valid", "invalid", "mismatch"), evaluate_case)


if __name__ == "__main__":
    raise SystemExit(cli(main))
