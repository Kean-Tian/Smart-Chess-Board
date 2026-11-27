"""TIDR #22: analyze illegal rejection, restoration gate and resumed physical play."""
import sys

sys.dont_write_bytecode = True
from common.runtime import cli, game_record
from common.move_demo import (accepted, between, model, paired, record_equal, run_main, sensor_events)


def evaluate_case(report, begin, end, trace):
    label, baseline = begin["window"], begin["state"]
    game_id = baseline["game_id"]
    candidates = [(c, r) for c, r in paired(trace, "GameSession.commit") if c["data"].get("move") == "e2e5"]
    physical = sensor_events(trace)
    report.check(f"{label}: physical e2e5 reported", any(c["data"].get("payload") == "MOVE e2e5"
                 for c, r in physical), "actual correlated MCU report required", missing=True)
    if not candidates:
        report.check(f"{label}: illegal candidate reached validator", False, "no observed e2e5 commit", missing=True)
        return
    call, rejection = candidates[0]
    rejected = rejection["data"]["state"]
    legal, _, _ = model(baseline, "e2e5")
    report.check(f"{label}: native rules reject e2e5 and require restoration", "e2e5" not in legal and
                 rejection["data"]["return"] is False and rejected["restore"] and
                 "illegal" in rejected["message"].lower(), rejected["message"])
    report.check(f"{label}: accepted FEN/turn/history and all stored record columns unchanged",
                 accepted(rejected) == accepted(baseline) and record_equal(
                 rejection["data"]["snapshot"], begin["snapshot"], game_id),
                 "active turn is the FEN side-to-move; No clock avoids unrelated clock checkpoints")
    restoration = [(c, r) for c, r in paired(trace, "GameSession.on_board") if
                   c["monotonic_ns"] > rejection["monotonic_ns"] and
                   c["data"]["state"]["restore"] and not r["data"]["state"]["restore"] and
                   r["data"]["state"]["mask"] == baseline["mask"]]
    if not restoration:
        report.check(f"{label}: whole-board restoration confirmed", False, "restore all disturbed pieces", missing=True)
        return
    restored_call, restored = restoration[0]
    wait = between(trace, rejection["monotonic_ns"], restored_call["monotonic_ns"] - 1)
    attempted = [(c, r) for c, r in paired(wait, "GameSession.event") if
                 c["data"].get("payload", "").startswith("MOVE ") and
                 c["data"]["payload"] != "MOVE e2e5"]
    report.check(f"{label}: subsequent physical move attempted before restoration", any(
                 c["data"].get("payload", "").startswith("MOVE ") and
                 c["data"]["payload"] != "MOVE e2e5" and
                 rejection["monotonic_ns"] < c["monotonic_ns"] < restored_call["monotonic_ns"]
                 for c, r in physical), "physically attempt d2d4 while e2e5 remains wrong", missing=True)
    writes = [e for e in wait if e["kind"] == "call" and e.get("operation") == "GameStore.move"]
    held = all(accepted(r["data"]["state"]) == accepted(baseline) and
               r["data"]["state"]["restore"] for c, r in attempted)
    states = [e["state"] for e in wait if e["kind"] == "mv_state"]
    report.check(f"{label}: subsequent play blocked until restoration", bool(attempted) and held and not writes
                 and all(accepted(s) == accepted(baseline) for s in states), f"attempts={len(attempted)}, writes={len(writes)}",
                 missing=not attempted)
    resumed = [(c, r) for c, r in paired(trace, "GameSession.commit") if
               c["monotonic_ns"] > restored["monotonic_ns"] and c["data"].get("move") == "e2e4"]
    report.check(f"{label}: restored baseline preserved", accepted(restored["data"]["state"]) == accepted(baseline),
                 "only occupancy/recovery flag changes on restoration")
    if not resumed:
        report.check(f"{label}: legal play resumed", False, "physically play e2e4 after restoration", missing=True)
        return
    _, post_mask, post_fen = model(baseline, "e2e4")
    c, r = resumed[0]
    report.check(f"{label}: physical legal move reported after restoration", any(
                 event["data"].get("payload") == "MOVE e2e4" and
                 event["monotonic_ns"] > restored["monotonic_ns"] for event, _ in physical),
                 "matching post-restoration MCU event required", missing=True)
    final = r["data"]["state"]
    record = game_record(end["snapshot"], game_id)
    report.check(f"{label}: matching legal move accepted after restoration", r["data"]["return"] is True
                 and final["fen"] == post_fen and final["mask"] == post_mask and final["moves"] == ["e2e4"]
                 and not final["restore"], "original native rules/FEN/occupancy audited")
    report.check(f"{label}: exactly one legal move persisted", len(record["moves"]) == 1 and
                 record["moves"][0]["uci"] == "e2e4" and record["game"]["current_fen"] == post_fen
                 and end["state"]["moves"] == ["e2e4"], "no illegal or intermediate candidate stored")


def main():
    return run_main(22, ("illegal-restore",), evaluate_case)


if __name__ == "__main__":
    raise SystemExit(cli(main))
