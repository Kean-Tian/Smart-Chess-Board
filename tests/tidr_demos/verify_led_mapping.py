"""MANUAL, exclusive-owner 64-square sensor/LED characterization, outside gameplay."""
import argparse
import fcntl
import sys
import uuid

sys.dont_write_bytecode = True
from common.runtime import Blocked, Report, append, bootstrap, cli, load_run, no_symlinks, run_argument
from preflight import inspect


def squares():
    return [f"{chr(97 + i % 8)}{i // 8 + 1}" for i in range(64)]


def capture():
    parser = argparse.ArgumentParser(description=__doc__)
    run_argument(parser)
    parser.add_argument("--port", required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--operator-confirms-controller-stopped", action="store_true", required=True)
    args = parser.parse_args()
    if not sys.stdin.isatty():
        raise Blocked("Mapping capture requires an interactive operator terminal; no unattended hardware launch")
    run, manifest = load_run(args.run)
    if manifest["purpose"] != "records":
        raise Blocked("Use a records-purpose run")
    checks = inspect(args.port)
    if any(not item["ok"] for item in checks):
        raise Blocked("Preflight: " + "; ".join(c["name"] + ": " + c["detail"] for c in checks if not c["ok"]))
    bootstrap()
    from scb_link import ScbLink
    from ui_hardware import fresh_snapshot, stopped_status
    token = uuid.uuid4().hex
    report = Report("LED-MAPPING")
    path = run / "led_mapping.jsonl"
    with no_symlinks(run / "service.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        append(path, {"kind": "begin", "mapping": token, "operator": args.operator, "port": args.port})
        print(f"Mapping ID: {token}. Attach reviewed video later with label mapping-{token}", flush=True)
        with ScbLink.open(args.port, exclusive=True) as link:
            clean = False
            try:
                stopped_status(link)
                link.request("LED_CLEAR")
                input("Record video. Remove ALL pieces. Press Enter when the final board is empty: ")
                mask, _ = fresh_snapshot(link)
                if mask != 0:
                    raise Blocked("Empty board does not read empty; retain evidence and diagnose without changing firmware")
                for index, square in enumerate(squares()):
                    link.request("LED_CLEAR")
                    link.request(f"LED {square} 0 0 20")
                    only = input(f"Observe ALL 64 LEDs. Type 'ONLY {square}' only if that physical labelled square alone is blue: ") == f"ONLY {square}"
                    input(f"Place one final piece on physical {square}; press Enter: ")
                    actual, received = fresh_snapshot(link)
                    input("Remove that piece; press Enter: ")
                    empty, _ = fresh_snapshot(link)
                    ok = only and actual == 1 << index and empty == 0
                    report.check(square, ok, {"sensed_mask": f"{actual:016X}", "empty_after": f"{empty:016X}",
                                              "only_named_LED_observed": only})
                    append(path, {"kind": "square", "mapping": token, "square": square,
                           "sensed": actual, "expected": 1 << index, "empty_after": empty,
                           "only_named_led_observed": only, "sensor_received_at": received, "ok": ok})
            finally:
                try:
                    link.request("LED_CLEAR", timeout=0.6)
                    link.request("STOP", timeout=0.6)
                    state = stopped_status(link)
                    clean = True
                    append(path, {"kind": "cleanup", "mapping": token, "safe_acknowledged": True, "status": state})
                except Exception as exc:
                    append(path, {"kind": "cleanup", "mapping": token, "safe_acknowledged": False, "error": str(exc)})
                    print("BLOCKED: cleanup unacknowledged; verify outputs and LEDs physically before leaving")
        append(path, {"kind": "complete", "mapping": token, "safe_acknowledged": clean})
    report.check("cleanup", clean, "LED_CLEAR/STOP/STATUS acknowledged; optical darkness still operator verified", missing=True)
    report.check("physical video reviewed", False, "attach video as hardware/led-mapping for the LED demos; this tool alone is characterization", missing=True)
    return report.finish(run)


def main():
    try:
        return capture()
    except (RuntimeError, EOFError) as exc:
        raise Blocked(f"Mapping incomplete: {exc}. Retain capture and verify physical safe outputs.") from exc


if __name__ == "__main__":
    raise SystemExit(cli(main))
