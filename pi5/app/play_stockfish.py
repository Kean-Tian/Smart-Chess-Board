"""Play against local Stockfish without requiring ESP32 or Internet access."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rules" / "python"))
from scb_rules import Game
from stockfish_engine import Stockfish, EngineError


def main():
    parser = argparse.ArgumentParser(description="Smart Chess Board local Stockfish opponent")
    parser.add_argument("--engine")
    parser.add_argument("--movetime", type=int, default=500, help="Search time in milliseconds")
    parser.add_argument("--skill", type=int, choices=range(21), default=10)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--hash", type=int, default=128, dest="hash_mb")
    parser.add_argument("--computer", choices=["white", "black"], default="black")
    args = parser.parse_args()
    computer = args.computer[0]
    with Game() as game, Stockfish(args.engine, args.threads, args.hash_mb, args.skill) as engine:
        print(f"Local opponent: {engine.name}. Computer plays {args.computer}.")
        print("Enter UCI moves (e2e4, e7e8q) or quit. No network or ESP32 is required.")
        while True:
            print(game.board_text())
            status = game.status()
            if status:
                print(status)
                if status != "Check.":
                    return 0
            if game.fen().split()[1] == computer:
                move = engine.choose(game, args.movetime)
                if move is None:
                    return 0
                if not game.play(move):
                    raise EngineError("Rules layer rejected the computer move")
                print(f"Stockfish > {move}")
            else:
                try:
                    move = input("You > ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    return 0
                if move == "quit":
                    return 0
                if not game.play(move):
                    print("Illegal move. Position unchanged.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EngineError, TimeoutError, ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
