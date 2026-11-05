"""Measure target timing over USB. Never arms or moves motors."""
import argparse
import json
import time
from pathlib import Path

from scb_link import ScbLink


def values(frame):
    return {key: int(value) for key, value in
            (token.split("=", 1) for token in frame.payload.split())}


def assess(timing, platform, elapsed_s, frame_delta, require_led=True):
    observed_hz = frame_delta / elapsed_s if elapsed_s > 0 else 0
    scan_pass = (frame_delta > 1 and observed_hz > 50 and
                 0 < timing['max_us'] < 20000 and timing['misses'] == 0)
    led_pass = (0 < platform['max_us'] < 100000 and
                platform['late'] == 0 and platform['failed'] == 0) if require_led else None
    return {
        'mcu_target': 'ESP32-S2-Saola-1',
        "observed_full_board_hz": observed_hz,
        'scan_pass': scan_pass,
        'led_exercise_requested': require_led,
        'led_software_pass': led_pass,
        'overall_pass': scan_pass and (led_pass if require_led else True),
        "timing": timing, "platform": platform,
        "optical_or_physical_move_latency_measured": False,
        "power_or_enclosure_temperature_measured": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Measure ESP32-S2 scan timing; optionally exercise external LEDs")
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--exercise-leds", action="store_true",
                        help="Alternate a dim a1 LED while measuring; never enable motion")
    args = parser.parse_args()
    if not 2 <= args.seconds <= 300:
        parser.error("--seconds must be 2..300")
    with ScbLink.open(args.port) as link:
        # Allow the first two complete sensor frames to settle.
        time.sleep(0.05)
        first = values(link.request("TIMING"))
        started = time.monotonic()
        i = 0
        try:
            while time.monotonic() - started < args.seconds:
                if args.exercise_leds:
                    link.request(f"LED a1 0 {20 if i % 2 else 0} 0", timeout=0.08)
                    i += 1
                time.sleep(0.05)
            last = values(link.request("TIMING"))
            elapsed = time.monotonic() - started
            platform = values(link.request("PLATFORM"))
        finally:
            if args.exercise_leds:
                link.request("LED_CLEAR")
        report = assess(last, platform, elapsed, last["frames"] - first["frames"],
                        require_led=args.exercise_leds)
    print(json.dumps(report, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report['overall_pass'] else 1


if __name__ == "__main__":
    raise SystemExit(main())
