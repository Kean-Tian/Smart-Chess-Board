"""Sample digital sensor reports without changing polarity, GPIO or filtering.

Close the touchscreen/serial console first. Keep the board empty for the full
capture. Percentages describe these samples, not sensor accuracy or every scan.
"""
import argparse
import json
from pathlib import Path
import queue
import time

from scb_link import ScbLink, DeviceError, format_occupancy


def summarize(masks):
    if not masks:
        raise ValueError("No RAW reports received")
    counts = [sum((mask >> q) & 1 for mask in masks) for q in range(64)]
    flips = [sum(((a ^ b) >> q) & 1 for a, b in zip(masks, masks[1:])) for q in range(64)]
    return {"samples": len(masks), "empty_samples": sum(mask == 0 for mask in masks),
            "occupied_counts": counts, "observed_transitions": flips}


def raw_sample(link):
    # Clear old unsolicited reports, then wait for this RAW request's report.
    while True:
        try:
            link.events.get_nowait()
        except queue.Empty:
            break
    requested = time.monotonic()
    link.request("RAW", timeout=0.8)
    deadline = time.monotonic() + 0.8
    while time.monotonic() < deadline:
        try:
            frame = link.events.get(timeout=max(0.001, deadline-time.monotonic()))
        except queue.Empty as exc:
            raise TimeoutError("RAW report missing after ACK") from exc
        if frame.kind == "FAULT":
            raise DeviceError(f"MCU fault: {frame.payload}")
        if frame.kind == "RAW" and frame.received_at >= requested:
            return int(frame.payload, 16)
    raise TimeoutError("RAW report missing after ACK")


def capture(link, seconds, interval):
    status = link.request("STATUS", timeout=0.8).payload
    fields = dict(t.split("=", 1) for t in status.split() if "=" in t)
    if any(fields.get(key) != "0" for key in ("armed", "moving", "magnet")):
        raise ValueError("Stop/disarm actuators before sensor diagnostics")
    if fields.get("fault", "NONE") != "NONE":
        raise ValueError(f"Resolve MCU fault first: {fields['fault']}")
    timing_before = link.request("TIMING", timeout=0.8).payload
    masks, times = [], []
    start = time.monotonic()
    while time.monotonic()-start < seconds:
        sampled = time.monotonic()
        masks.append(raw_sample(link))
        times.append(round(time.monotonic()-start, 4))
        time.sleep(max(0.0, interval-(time.monotonic()-sampled)))
    link.request("SCAN", timeout=0.8)
    timing_after = link.request("TIMING", timeout=0.8).payload
    return dict(summarize(masks), status=status, timing_before=timing_before,
                timing_after=timing_after, raw_masks=[f"{m:016X}" for m in masks],
                sample_times_s=times,
                latest_stable_board=None if link.board is None else f"{link.board:016X}")


def display(report):
    n = report["samples"]
    print("\nEMPTY-BOARD DIGITAL DIAGNOSTICS (not a calibration)")
    print("STATUS:", report["status"])
    print(f"RAW samples: {n}; completely empty: {report['empty_samples']}/{n}")
    print("Occupied percentage in sampled RAW reports; an empty board should be 0 throughout.")
    print("        a      b      c      d      e      f      g      h")
    for rank in range(7, -1, -1):
        print(f"{rank+1}  " + " ".join(f"{100*report['occupied_counts'][rank*8+c]/n:5.1f}%" for c in range(8)))
    print("\nNonzero squares: sampled occupied count / observed toggles")
    for q, count in enumerate(report["occupied_counts"]):
        if count:
            square = f"{chr(97+q%8)}{q//8+1}"
            label = "CONSISTENT OCCUPANCY" if count == n else "INTERMITTENT OCCUPANCY"
            print(f"  {square}: {count}/{n}, toggles={report['observed_transitions'][q]} [{label}]")
    stable = report["latest_stable_board"]
    print("Latest stable BOARD:", "Unavailable" if stable is None else format_occupancy(stable))
    print("TIMING before:", report["timing_before"])
    print("TIMING after: ", report["timing_after"])
    print("RAW is polarity-normalized digital occupancy BEFORE debounce, not analog voltage.")
    print("Samples may miss faster glitches; compare TIMING frame counters to confirm scanning advances.")
    print("Persistent wrong levels need wiring/power/threshold checks; filtering alone cannot correct them.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--output", type=Path, help="Save JSON report, e.g. empty_board.json")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60 or not 0.05 <= args.interval <= 1:
        parser.error("Use 1..60 seconds and a 0.05..1 second sample interval")
    print("Close the UI and all other serial clients. Remove all pieces/magnets and keep them away from the board.")
    print("No GPIO/polarity/filter settings are changed. Closing the connection sends STOP.")
    with ScbLink.open(args.port, exclusive=True) as link:
        report = capture(link, args.seconds, args.interval)
    display(report)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2)+"\n")
        print("Report saved:", args.output)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, TimeoutError, queue.Empty) as exc:
        raise SystemExit(f"Sensor diagnostics failed: {exc}")
