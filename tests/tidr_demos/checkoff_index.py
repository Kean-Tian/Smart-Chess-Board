"""Read-only IDs, evidence hashes and selected event tokens; no device/socket/test opens."""
import argparse
import json
import sys

sys.dont_write_bytecode = True
from common.runtime import cli, database_snapshot, events, load_run, read_jsonl, run_argument


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    run_argument(parser)
    parser.add_argument("--window", help="Show annotation candidates for one existing window")
    args = parser.parse_args()
    run, manifest = load_run(args.run)
    print(json.dumps({"database": manifest["database"], "socket": manifest["socket"]}))
    if (run / "players.sqlite3").exists():
        snapshot = database_snapshot(manifest["database"])  # Separate read-only transaction.
        for game in snapshot["games"]:
            print(json.dumps({"game_id": game["id"], "status": game["status"], "white": game["white_name"],
                              "black": game["black_name"], "minutes": game["minutes"], "result": game["result"],
                              "moves": [m["uci"] for m in snapshot["moves"] if m["game_id"] == game["id"]]}))
    mapping = [r for r in read_jsonl(run / "led_mapping.jsonl") if r["kind"] == "complete"]
    if mapping:
        print(json.dumps({"latest_mapping_id": mapping[-1]["mapping"],
                          "mapping_video_label": "mapping-" + mapping[-1]["mapping"]}))
    for attachment in read_jsonl(run / "attachments.jsonl"):
        if not args.window or attachment["label"] == args.window:
            print(json.dumps({"attachment": attachment["path"], "kind": attachment["kind"],
                              "label": attachment["label"], "sha256": attachment["sha256"]}))
    if not args.window:
        return 0
    markers = []
    for filename in ("move_windows.jsonl", "display_clock_windows.jsonl", "replay.jsonl"):
        markers.extend(r for r in read_jsonl(run / filename) if r["window"] == args.window)
    if not markers:
        print("BLOCKED: requested window not found")
        return 2
    markers.sort(key=lambda r: r["monotonic_ns"])
    begin, end = markers[0], markers[-1]
    print(json.dumps({"window": args.window, "session": begin["session"], "markers": len(markers)}))
    selected = [e for e in events(run) if e["session"] == begin["session"] and
                begin["monotonic_ns"] <= e["monotonic_ns"] <= (end["monotonic_ns"] if len(markers) > 1 else 2**63)]
    returns = {e["token"]: e for e in selected if e["kind"] == "dc_return"}
    tick_selected = set()
    for e in selected:
        if e["kind"] in {"led_input", "led_store_return"}:
            print(json.dumps(e))
        elif e["kind"] == "mv_call" and e["operation"] == "GameSession.event":
            print(json.dumps({"kind": e["kind"], "operation": e["operation"], "token": e["token"],
                              "payload": e["data"].get("payload"), "observed_ns": e["observed_ns"]}))
        elif e["kind"] == "dc_call":
            ret = returns.get(e["token"])
            op, state = e["operation"], e["state"]
            show = op in {"GameSession.start", "GameSession.commit", "GameSession.end", "GameSession.prepare"}
            if ret and op == "GameSession.on_board":
                after = ret["state"]
                show = state["restore"] or state["legal_source"] != after["legal_source"]
            if ret and op in {"GameSession.tick", "GameSession.tick_clock_only"} and state["active"] and not state["paused"]:
                side = 0 if state["fen"].split()[1] == "w" else 1
                if ret["state"]["clocks"][side] is not None and ret["state"]["clocks"][side] <= 299000 and side not in tick_selected:
                    tick_selected.add(side)
                    show = True
            if show:
                print(json.dumps({"operation": op, "token": e["token"], "call_ns": e["observed_ns"],
                                  "return_ns": ret["observed_ns"] if ret else None,
                                  "state_after": ret["state"] if ret else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli(main))
