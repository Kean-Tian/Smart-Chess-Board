"""Select Local Mode or AI Mode before starting a chess game."""
import argparse
import sys

from openrouter_engine import OpenRouterError
from opponents import add_opponent_arguments, configure_api_key
from stockfish_engine import EngineError
from scb_link import DeviceError
from coaching import add_coaching_arguments


def select_opponent():
    while True:
        print("\nSmart Chess Board\n1. Local Mode - Play with Stockfish\n2. AI Mode\n0. Quit")
        try:
            choice = input("Select mode > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        if choice in {"0", "q", "quit"}:
            return None
        if choice == "1":
            return "local"
        if choice != "2":
            print("Choose 1, 2, or 0.")
            continue
        while True:
            print("\nAI Mode\n1. Play with AI (OpenRouter)\n2. AI Coaching (two players)\n0. Back")
            try:
                action = input("Select AI feature > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None
            if action == "1":
                return "openrouter"
            if action == "2":
                return "coaching"
            if action in {"0", "back"}:
                break
            if action in {"q", "quit"}:
                return None
            print("Choose 1, 2, or 0.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Choose Local Mode or OpenRouter AI Mode")
    add_opponent_arguments(parser, default=None)
    add_coaching_arguments(parser)
    parser.add_argument("--board", action="store_true", help="Play using the ESP32 physical board")
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--set-api-key", action="store_true", help="Save or replace the locally remembered OpenRouter key")
    args = parser.parse_args(argv)
    if args.set_api_key:
        return configure_api_key()
    args.coaching = args.coaching or args.coach_white is not None or args.coach_black is not None
    if args.coaching and args.opponent == "local":
        parser.error("AI Coaching uses OpenRouter; omit --opponent local.")
    if args.coaching:
        args.opponent = "coaching"
    if args.opponent is None:
        args.opponent = select_opponent()
    if args.opponent is None:
        return 0
    if args.opponent == "coaching":
        args.coaching = True
        args.opponent = "openrouter"
    if args.board:
        from board_game import run
        args.mode = "pvp" if args.coaching else "pvc"
    elif args.coaching:
        from coaching import run
    else:
        from play_stockfish import run
    return run(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DeviceError, EngineError, OpenRouterError, TimeoutError, ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
