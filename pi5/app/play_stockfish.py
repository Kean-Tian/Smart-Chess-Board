"""Keyboard chess against Stockfish or OpenRouter; defaults to local play."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rules" / "python"))
from scb_rules import Game
from stockfish_engine import EngineError
from openrouter_engine import OpenRouterError
from opponents import add_opponent_arguments, create_opponent


def play_game(game, engine, computer, movetime_ms):
    """Both providers use the same authoritative rules and turn handling."""
    while True:
        print(game.board_text())
        status = game.status()
        if status:
            print(status)
            if status != "Check.":
                return 0
        if game.fen().split()[1] == computer:
            while True:
                try:
                    move = engine.choose(game, movetime_ms)
                    break
                except OpenRouterError as exc:
                    print(exc, file=sys.stderr, flush=True)
                    try:
                        action = input("Position preserved, computer to move. Enter to retry, or quit: ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        return 0
                    if action in {"quit", "q"}:
                        return 0
            if move is None:
                return 0
            if not game.play(move):
                raise EngineError("Rules layer rejected the computer move")
            print(f"{engine.name} > {move}")
        else:
            try:
                move = input("You > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return 0
            if move == "quit":
                return 0
            if not game.play(move):
                print("Illegal move. Position unchanged.")


def run(args):
    computer = args.computer[0]
    with create_opponent(args) as engine, Game() as game:
        print(f"Opponent: {engine.name}. Computer plays {args.computer}.")
        print("Enter UCI moves (e2e4, e7e8q) or quit.")
        return play_game(game, engine, computer, args.movetime)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Smart Chess Board keyboard opponent")
    add_opponent_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EngineError, OpenRouterError, TimeoutError, ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
