"""TIDR #27: native-display evidence with bounded, operator-synchronized visibility."""
import json
from pathlib import Path
import shutil
import sys
import uuid

sys.dont_write_bytecode = True
from common.runtime import Blocked, append, attachments, cli, digest, read_jsonl
from common.display_clock_demo import duration_check, pairs, run_main
from common.move_demo import sensor_events


def import_visibility(run, filename):
    source = Path(filename)
    data = json.loads(source.read_text())
    if data.get("version") != 1 or not all(data.get(k) for k in ("window", "session", "reviewer", "method", "video_sha256")):
        raise Blocked("Visibility document needs version=1, window, session, reviewer, method, video_sha256")
    if not isinstance(data.get("observations", []), list) or not all(
            isinstance(o, dict) for o in data.get("observations", [])):
        raise Blocked("observations must be a list of objects")
    target = run / "evidence" / ("visibility-" + uuid.uuid4().hex + ".json")
    shutil.copyfile(source, target)
    append(run / "display_visibility.jsonl", {"kind": "visibility", "document": data,
           "path": str(target.relative_to(run)), "sha256": digest(target)})
    print(f"Imported operator evidence: {target}; this does not establish a hardware PASS by itself")
    return 0


def documents(run, begin):
    video_hashes = {a["sha256"] for a in attachments(run, "hardware", begin["window"])
                    if Path(a["path"]).suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm"}}
    found = []
    for entry in read_jsonl(run / "display_visibility.jsonl"):
        doc = entry["document"]
        if doc["window"] != begin["window"] or doc["session"] != begin["session"]:
            continue
        path = (run / entry["path"]).resolve()
        if not path.is_relative_to((run / "evidence").resolve()) or digest(path) != entry["sha256"]:
            raise Blocked("Imported visibility document was altered or moved outside evidence")
        if doc["video_sha256"] in video_hashes:
            found.append(doc)
    return found


def visible(report, docs, label, call, ret, field):
    candidates = [(d, o) for d in docs for o in d.get("observations", [])
                  if o.get("backend_token") == call["token"] and o.get("field") == field]
    if not candidates:
        report.check(f"{label}: {field} visible and correct", False,
                     f"need physical video annotation for backend token {call['token']}", missing=True)
        report.check(f"{label}: {field} <=1000 ms", False, "physical visibility timing unavailable", missing=True)
        return
    for doc, item in candidates:
        detail = {"backend_token": call["token"], "observed_text": item.get("observed_text"),
                  "reviewer": doc["reviewer"], "video_sha256": doc["video_sha256"]}
        text, state = item.get("observed_text", ""), ret["state"]
        if not isinstance(text, str):
            text = ""
        content = bool(text)
        if field == "players":
            content = state["white"] in text and state["black"] in text
        elif field == "turn":
            content = ("White" if state["fen"].split()[1] == "w" else "Black") in text
        elif field == "moves":
            content = bool(state["last_move"]) and state["last_move"] in text
        elif field == "status":
            content = bool(state["game_status"]) and state["game_status"] in text
        elif field == "error":
            content = "Illegal" in text
        elif field == "error-cleared":
            content = bool(text) and "Illegal" not in text and not state["restore"]
        elif field == "clocks":
            content = len(item.get("displayed_clocks", [])) == 2
        detail["backend_state"] = {k: state[k] for k in ("white", "black", "fen", "last_move", "game_status", "clocks")}
        report.check(f"{label}: {field} visible and correct", item.get("correct") is True and content,
                     detail, missing=item.get("correct") is None)
        lower, upper, uncertainty = (item.get("visible_lower_ns"), item.get("visible_upper_ns"),
                                     doc.get("uncertainty_ns"))
        integers = all(isinstance(v, int) and not isinstance(v, bool) for v in (lower, upper, uncertainty))
        if (doc.get("measurement_kind") != "physical_touchscreen" or doc.get("synchronized") is not True
                or doc.get("timebase") != "pi_monotonic_ns" or not integers
                or uncertainty < 0 or lower < 0 or upper < lower or not item.get("frame_reference")):
            report.check(f"{label}: {field} <=1000 ms", False,
                         "need synchronized physical frame bounds, uncertainty and frame reference; socket timestamps are insufficient",
                         missing=True)
            continue
        duration_check(report, f"{label}: {field} <=1000 ms",
                       max(0, lower - uncertainty - ret["observed_ns"]),
                       upper + uncertainty - call["observed_ns"], 1000,
                       {**detail, "backend_lower_ns": call["observed_ns"], "backend_upper_ns": ret["observed_ns"],
                        "visible_lower_ns": lower, "visible_upper_ns": upper,
                        "uncertainty_ns": uncertainty, "frame_reference": item["frame_reference"],
                        "sync_method": doc["method"]})


def evaluate_case(report, run, begin, end, trace):
    label, case = begin["window"], begin["case"]
    docs = documents(run, begin)
    commits = [(c, r) for c, r in pairs(trace, "GameSession.commit") if r["value"] is True]
    if case == "overview":
        starts = [(c, r) for c, r in pairs(trace, "GameSession.start") if r["state"]["active"]]
        report.check(label + ": initial player/turn/clock backend update", bool(starts), "begin before pressing Start", missing=True)
        if starts:
            c, r = starts[0]
            report.check(label + ": named five-minute PvP game", bool(r["state"]["white"] and r["state"]["black"])
                         and r["state"]["minutes"] == 5 and r["state"]["mode"] == "pvp", r["state"]["clocks"])
            for field in ("players", "turn", "clocks"):
                visible(report, docs, label, c, r, field)
            ticks = pairs(trace, "GameSession.tick") + pairs(trace, "GameSession.tick_clock_only")
            for side, name in ((0, "White"), (1, "Black")):
                samples = [(a, b) for a, b in ticks if a["state"]["active"] and not a["state"]["paused"]
                           and a["state"]["game_id"] == r["state"]["game_id"]
                           and isinstance(b["state"]["clocks"][side], (int, float))
                           and a["state"]["fen"].split()[1] == ("w" if side == 0 else "b") and
                           b["state"]["clocks"][side] <= r["state"]["clocks"][side] - 1000]
                samples.sort(key=lambda pair: pair[1]["observed_ns"])
                report.check(f"{label}: {name} remaining-time update sampled", bool(samples),
                             "wait for at least one second of visible active-clock change; sampling rule, not an accuracy tolerance",
                             missing=True)
                if samples:
                    visible(report, docs, label + " " + name + " remaining time", *samples[0], "clocks")
        report.check(label + ": accepted move observed", bool(commits), "make e2e4 on the actual board", missing=True)
        if commits:
            c, r = commits[0]
            for field in ("turn", "moves"):
                visible(report, docs, label, c, r, field)
            reviews = [d.get("history_review", {}) for d in docs]
            report.check(label + ": native position-review history correct", any(
                         h.get("correct") is True and h.get("native_view_position") is True and
                         h.get("moves") == end["state"]["moves"] and h.get("frame_reference") for h in reviews),
                         "active Game page shows last move; use existing View position for step-by-step history", missing=True)
    elif case in {"check", "checkmate"}:
        updates = [(c, r) for c, r in commits if (r["state"]["game_status"] == "Check." if case == "check"
                   else r["state"]["game_status"].startswith("Checkmate"))]
        report.check(label + ": native rules identify " + case, bool(updates), "must arise from accepted legal physical play", missing=True)
        for c, r in updates:
            visible(report, docs, label, c, r, "status")
    else:
        rejected = [(c, r) for c, r in pairs(trace, "GameSession.commit") if r["value"] is False and
                    r["state"]["restore"] and "Illegal" in r["state"]["message"]]
        report.check(label + ": blocking illegal-move error", bool(rejected), "physical e2e5 from standard position", missing=True)
        if not rejected:
            return
        c, r = rejected[0]
        visible(report, docs, label, c, r, "error")
        restorations = [(a, b) for a, b in pairs(trace, "GameSession.on_board") if a["state"]["restore"]
                        and not b["state"]["restore"] and a["monotonic_ns"] > r["monotonic_ns"]]
        report.check(label + ": physical board restoration", bool(restorations), "restore the complete accepted board", missing=True)
        if restorations:
            a, b = restorations[0]
            visible(report, docs, label, a, b, "error-cleared")
            held = [e for e in trace if e["kind"] == "dc_state" and
                    r["monotonic_ns"] < e["monotonic_ns"] < a["monotonic_ns"]]
            report.check(label + ": backend error persists through unrelated refreshes", len(held) >= 2 and
                         all(s["state"]["restore"] and "Illegal" in s["payload"].get("message", "") for s in held),
                         f"real native-UI state updates={len(held)}", missing=len(held) < 2)
            unrelated = [(u, v) for u, v in pairs(trace, "UiCore.handle") if
                         u["data"].get("production_ui_dispatch") and
                         u["data"].get("request", {}).get("cmd") == "guidance" and
                         r["monotonic_ns"] < u["monotonic_ns"] < a["monotonic_ns"]]
            report.check(label + ": unrelated UI action observed while blocked", bool(unrelated),
                         "toggle Guidance while the board remains wrong", missing=True)
            persistence = [d.get("persistence", {}) for d in docs if
                           d.get("persistence", {}).get("rejection_token") == c["token"] and
                           d.get("persistence", {}).get("restoration_token") == a["token"]]
            report.check(label + ": physical warning continuously visible until resolution", bool(persistence) and
                         all(p.get("continuous_video_review") is True and p.get("warning_persisted") is True
                             and p.get("cleared_after_restoration") is True and p.get("frame_range") for p in persistence),
                         "continuous final-touchscreen video review required; two screenshots are insufficient", missing=not persistence)
    report.check(label + ": actual sensor event evidence", bool(sensor_events(trace)),
                 "correlated original ESP event reader and UiCore dispatch required", missing=True)
    reference_id = begin.get("state", {}).get("game_id")
    if reference_id is None:
        starts = pairs(trace, "GameSession.start")
        reference_id = starts[0][1]["state"]["game_id"] if starts else None
    states = [e["state"] for e in trace if e["kind"] == "dc_state" and e["state"]["game_id"] is not None]
    report.check(label + ": one game context throughout", reference_id is not None and
                 all(s["game_id"] == reference_id for s in states), "do not change games within a window", missing=reference_id is None)


def main():
    return run_main(27, ("overview", "check", "checkmate", "error"), evaluate_case, import_visibility)


if __name__ == "__main__":
    raise SystemExit(cli(main))
