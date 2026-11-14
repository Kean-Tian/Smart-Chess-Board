"""Test square LED guidance over USB without starting a chess game."""
import argparse
import re
import sys
import time

from move_guidance import MoveGuidance, add_led_hint_arguments
from scb_link import ScbLink, DeviceError
from software_limits import BOARD_EVENT_POLL_S


def move_argument(value):
    value = value.lower()
    if not re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", value) or value[:2] == value[2:4]:
        raise argparse.ArgumentTypeError("Use two different squares, for example e2e4")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="ESP32 USB serial port")
    parser.add_argument("--move", type=move_argument, default="e2e4", help="Square pair to demonstrate (default: e2e4)")
    parser.add_argument("--seconds", type=float, default=15, help="Test duration, 6..300 seconds (default: 15)")
    parser.add_argument("--timer-only", action="store_true", help="Ignore sensors to verify the 5-second fallback")
    add_led_hint_arguments(parser)
    args = parser.parse_args(argv)
    if not 6 <= args.seconds <= 300:
        parser.error("--seconds must be 6..300")

    with ScbLink.open(args.port) as link:
        link.request("STOP")
        # SCAN supplies a baseline even when occupancy has not changed since boot.
        if not args.timer_only:
            try:
                link.request("SCAN")
            except DeviceError as exc:
                if str(exc) != "NOT_READY":
                    raise
        guide = MoveGuidance(link, args.led_hints)
        source, target = args.move[:2], args.move[2:4]
        print(f"Testing {source} -> {target} for {args.seconds:g} seconds. Ctrl+C to stop.", flush=True)
        if args.led_hints == "both":
            print(f"Expect {source} steady blue and {target} steady green immediately.", flush=True)
        else:
            print(f"Expect {source} blue first; {target} blinks green after a source lift or 5 seconds.", flush=True)
            source_bit = 1 << ((int(source[1]) - 1) * 8 + ord(source[0]) - ord("a"))
            if args.timer_only:
                print("Timer-only test: sensor changes are ignored.", flush=True)
            elif link.board is None or not link.board & source_bit:
                print("Source piece not detected yet. The 5-second fallback still works; "
                      "place a piece on the source before restarting to test an early lift.", flush=True)
        try:
            guide.start(args.move, None if args.timer_only else link.board)
            started = time.monotonic()
            while time.monotonic() - started < args.seconds:
                guide.update(None if args.timer_only else link.board)
                time.sleep(BOARD_EVENT_POLL_S)
        finally:
            guide.clear()
    print("Test ended; hint LEDs cleared. Check the observed lights against the expected sequence.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nTest stopped.")
        raise SystemExit(130)
    except (DeviceError, TimeoutError, OSError, ValueError) as exc:
        print(f"LED test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
