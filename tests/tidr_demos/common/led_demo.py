"""LED windows, full-board optical observations, mapping and bounded latency."""
import argparse
import json
from pathlib import Path
import shutil
import uuid

from .runtime import (Blocked, append, attachments, digest, events, load_run, read_jsonl, run_argument)
from .display_clock_demo import duration_check, evaluate, mark, pairs
from .move_demo import initial_position, paired, sensor_events

SQUARES = [f"{chr(97 + i % 8)}{i // 8 + 1}" for i in range(64)]


def mapping_proof(run, before_ns=None):
    records = read_jsonl(run / "led_mapping.jsonl")
    completed = [r for r in records if r["kind"] == "complete" and
                 (before_ns is None or r["monotonic_ns"] < before_ns)]
    if not completed:
        return False, "no completed 64-square physical mapping capture before this window"
    latest = completed[-1]
    rows = [r for r in records if r.get("mapping") == latest["mapping"] and r["kind"] == "square"]
    ok = (len(rows) == 64 and {r["square"] for r in rows} == set(SQUARES) and
          latest["safe_acknowledged"] and all(not r.get("synthetic") and r["only_named_led_observed"]
          and r["sensed"] == 1 << SQUARES.index(r["square"]) and r["empty_after"] == 0 for r in rows))
    video = attachments(run, "hardware", "mapping-" + latest["mapping"])
    ok = ok and bool(video) and not any(r.get("synthetic") for r in records if r.get("mapping") == latest["mapping"])
    return ok, {"mapping": latest["mapping"], "squares": len(rows), "reviewed_attachments": len(video)}


def import_optical(run, filename):
    source = Path(filename)
    doc = json.loads(source.read_text())
    if doc.get("version") != 1 or not all(doc.get(k) for k in
            ("window", "session", "reviewer", "method", "evidence_sha256")):
        raise Blocked("Need version=1, window, session, reviewer, method and evidence_sha256")
    if not isinstance(doc.get("observations", []), list) or not all(isinstance(o, dict) for o in doc.get("observations", [])):
        raise Blocked("observations must be objects")
    target = run / "evidence" / ("led-optical-" + uuid.uuid4().hex + ".json")
    shutil.copyfile(source, target)
    append(run / "led_optical.jsonl", {"document": doc, "path": str(target.relative_to(run)), "sha256": digest(target)})
    print(f"Imported operator optical evidence: {target}; no hardware PASS implied")
    return 0


def optical_documents(run, begin):
    hashes = {a["sha256"] for a in attachments(run, "hardware", begin["window"])}
    result = []
    for entry in read_jsonl(run / "led_optical.jsonl"):
        doc = entry["document"]
        if doc["window"] != begin["window"] or doc["session"] != begin["session"]:
            continue
        path = (run / entry["path"]).resolve()
        if not path.is_relative_to((run / "evidence").resolve()) or digest(path) != entry["sha256"]:
            raise Blocked("Optical annotation file changed or escaped evidence directory")
        if doc["evidence_sha256"] in hashes and doc.get("measurement_kind") == "physical_leds":
            result.append(doc)
    return result


def optical(report, docs, label, role, token, expected_lit, start_lower=None, start_upper=None):
    found = [(d, o) for d in docs for o in d.get("observations", []) if
             o.get("role") == role and o.get("anchor_token") == token]
    if not found:
        report.check(f"{label}: optical {role}", False,
                     {"anchor_token": token, "expected_lit": expected_lit, "all_other_squares": "off"}, missing=True)
        if start_lower is not None:
            report.check(f"{label}: optical {role} <=500 ms", False, "physical timing evidence unavailable", missing=True)
        return
    for doc, item in found:
        lit = item.get("lit")
        valid = (item.get("all_64_inspected") is True and isinstance(lit, dict) and
                 all(s in SQUARES and c in {"red", "green", "blue", "other"} for s, c in lit.items())
                 and bool(item.get("frame_reference")))
        report.check(f"{label}: optical {role}", valid and lit == expected_lit,
                     {"anchor_token": token, "observed_lit": lit, "expected_lit": expected_lit,
                      "all_other_squares": "off", "evidence_sha256": doc["evidence_sha256"],
                      "frame_reference": item.get("frame_reference")}, missing=not valid)
        if start_lower is None:
            continue
        lo, hi, u = item.get("optical_lower_ns"), item.get("optical_upper_ns"), doc.get("uncertainty_ns")
        numeric = all(isinstance(v, int) and not isinstance(v, bool) for v in (lo, hi, u))
        if (doc.get("synchronized") is not True or doc.get("timebase") != "pi_monotonic_ns"
                or not numeric or lo < 0 or hi < lo or u < 0):
            report.check(f"{label}: optical {role} <=500 ms", False,
                         "need physical onset/frame bounds synchronized to Pi monotonic time with measured uncertainty", missing=True)
        else:
            duration_check(report, f"{label}: optical {role} <=500 ms", max(0, lo - u - start_upper),
                           hi + u - start_lower, 500,
                           {"anchor_token": token, "start_lower_ns": start_lower, "start_upper_ns": start_upper,
                            "optical_lower_ns": lo, "optical_upper_ns": hi, "uncertainty_ns": u,
                            "evidence_sha256": doc["evidence_sha256"], "method": doc["method"]})


def production_command(report, trace, label, command, lower, upper=None):
    if upper is None:
        changes = [e["observed_ns"] for e in trace if e["kind"] == "led_input" and
                   e["observed_ns"] > lower and e["desired"] != command]
        upper = min(changes) if changes else None
    actual = [e for e in trace if e["kind"] == "led_command" and e["command"] == command and
              e["observed_ns"] >= lower and (upper is None or e["observed_ns"] <= upper)]
    report.check(label + ": production " + command, bool(actual) and all(e.get("production_feedback_path") for e in actual),
                 "must originate in original UiCore.feedback_update worker; ACK is not light", missing=not actual)
    return actual


def accepted_anchor(report, trace, label, call, ret):
    state = ret["state"]
    persisted = [e for e in trace if e["kind"] == "led_store_return" and e["game_id"] == state["game_id"] and
                 e["uci"] == call["data"].get("move") and e["ply"] == len(state["moves"]) and
                 call["observed_ns"] <= e["observed_ns"] <= ret["observed_ns"]]
    verified = [r for c, r in paired(trace, "GameSession.commit") if r["data"].get("return") is True and
                r["data"]["state"]["game_id"] == state["game_id"] and
                r["data"]["state"]["moves"] == state["moves"] and
                any(g["id"] == state["game_id"] and g["current_fen"] == state["fen"] for g in r["data"]["snapshot"]["games"]) and
                len([m for m in r["data"]["snapshot"]["moves"] if m["game_id"] == state["game_id"]]) == len(state["moves"])]
    report.check(label + ": successful persistence precedes accepted LED feedback", bool(persisted and verified),
                 "store-return anchor is after transaction exit and before accepted-state swap; snapshot confirms success",
                 missing=True)
    return persisted[-1]["observed_ns"] if persisted and verified else None


def common_case(evaluator):
    def wrapped(report, run, begin, end, trace):
        label = begin["window"]
        fen, mask = initial_position()
        state = begin["state"]
        report.check(label + ": standard active No-clock PvP baseline", state["active"] and not state["paused"]
                     and state["mode"] == "pvp" and state["minutes"] == 0 and not state["moves"]
                     and state["fen"] == fen and state["mask"] == mask,
                     "test precondition, not a product performance failure", missing=True)
        ok, detail = mapping_proof(run, begin["monotonic_ns"])
        report.check(label + ": all-64 physical coordinate mapping", ok, detail, missing=True)
        report.check(label + ": real Hall-event dispatch", bool(sensor_events(trace)),
                     "requires original serial reader -> UiCore event path", missing=True)
        commands = [e for e in trace if e["kind"] == "serial_request"]
        forbidden = [e["command"] for e in commands if e["command"].split()[0] in
                     {"ARM", "GOTO", "MOVE", "JOG", "MAGNET", "HOME", "ORIGIN", "SET_STEPS", "LED"}]
        report.check(label + ": no actuator or manual LED fixture commands", not forbidden, str(forbidden))
        status = [e["payload"].get("board_status", {}) for e in trace if e["kind"] == "dc_state"]
        known = [s for s in status if all(k in s for k in ("armed", "moving", "magnet", "fault"))]
        report.check(label + ": safe idle actuator telemetry", bool(known) and all(
                     all(s[k] == "0" for k in ("armed", "moving", "magnet")) and s["fault"] == "NONE" for s in known),
                     "motor/magnet motion remains disabled", missing=not known)
        docs = optical_documents(run, begin)
        evaluator(report, begin, end, trace, docs)
    return wrapped


def run_main(tidr, case, evaluator):
    parser = argparse.ArgumentParser(description=f"TIDR #{tidr}: manual real-board LED observations and offline optical analysis")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("begin", "end", "evaluate", "import-optical"):
        item = sub.add_parser(action)
        run_argument(item)
        if action == "evaluate":
            item.add_argument("--windows", nargs="+")
        elif action == "import-optical":
            item.add_argument("--file", required=True)
        else:
            item.add_argument("--window", required=True)
    args = parser.parse_args()
    run, manifest = load_run(args.run)
    if manifest["purpose"] != "records":
        raise Blocked("Use an isolated records-purpose run")
    if args.action == "import-optical":
        return import_optical(run, args.file)
    if args.action == "evaluate":
        return evaluate(run, args, tidr, (case,), common_case(evaluator))
    if args.action == "begin":
        ok, detail = mapping_proof(run)
        if not ok:
            raise Blocked("Complete/attach all-64 physical mapping before this test: " + str(detail))
        latest = next((e for e in reversed(events(run)) if e["kind"] == "dc_state"), None)
        fen, mask = initial_position()
        if latest is None:
            raise Blocked("Need fresh native-UI state from run_led_service.py")
        state = latest["state"]
        if (not state["active"] or state["paused"] or state["mode"] != "pvp" or state["minutes"] != 0
                or state["fen"] != fen or state["mask"] != mask or state["moves"]):
            raise Blocked("Begin from an active, synchronized standard PvP / No clock game")
        args.case = case
    return mark(run, manifest, args, tidr)
