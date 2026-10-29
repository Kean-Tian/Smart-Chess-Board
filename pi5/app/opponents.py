"""Shared opponent options for keyboard and physical-board games."""
import argparse
import getpass
import os
import sys
import warnings

from openrouter_engine import OpenRouter, OpenRouterError
from api_key_store import load_api_key, save_api_key
from stockfish_engine import Stockfish


def search_time(value):
    duration = int(value)
    if not 50 <= duration <= 10000:
        raise argparse.ArgumentTypeError("movetime must be 50..10000 milliseconds")
    return duration


def add_opponent_arguments(parser, default="local"):
    parser.add_argument("--opponent", choices=["local", "openrouter"], default=default,
                        help="local = Stockfish; openrouter = AI Mode")
    parser.add_argument("--computer", choices=["white", "black"], default="black")
    parser.add_argument("--engine", help="Local Stockfish executable")
    parser.add_argument("--movetime", type=search_time, default=500,
                        help="Local search time in milliseconds (50..10000)")
    parser.add_argument("--skill", type=int, choices=range(21), default=10,
                        help="Local Stockfish skill (0..20)")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--hash", type=int, default=128, dest="hash_mb")
    parser.add_argument("--model", help="OpenRouter model ID (or OPENROUTER_MODEL)")


def prompt_api_key():
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass("OpenRouter API Key (hidden; remembered locally): ")
    except (EOFError, KeyboardInterrupt) as exc:
        raise OpenRouterError("AI Mode setup cancelled.", retryable=False) from exc
    except getpass.GetPassWarning as exc:
        raise OpenRouterError("Cannot hide API key input in this terminal. "
                              "Use Terminal or set OPENROUTER_API_KEY.", retryable=False) from exc


def configure_api_key():
    save_api_key(prompt_api_key())
    print("OpenRouter key saved locally. Future games will load it automatically.")
    return 0


def create_openrouter(model=None):
    key = os.environ.get("OPENROUTER_API_KEY", "").strip() or load_api_key()
    entered = not key and sys.stdin.isatty()
    if entered:
        key = prompt_api_key()
    provider = OpenRouter(api_key=key, model=model)
    if entered:
        try:
            save_api_key(provider.api_key)
            print("OpenRouter key remembered locally for future games.")
        except OpenRouterError as exc:
            print(f"{exc} The key is available for this game only.", file=sys.stderr)
    return provider


def create_opponent(args):
    if args.opponent == "openrouter":
        return create_openrouter(args.model)
    return Stockfish(args.engine, args.threads, args.hash_mb, args.skill)
