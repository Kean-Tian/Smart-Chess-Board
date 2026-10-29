#!/usr/bin/env python3
"""Compatibility entry point: choose Local Mode or OpenRouter AI Mode."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pi5" / "app"))
from openrouter_engine import OpenRouterError, ask_ai_move
from play import main
from stockfish_engine import EngineError
from scb_link import DeviceError


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DeviceError, EngineError, OpenRouterError, TimeoutError, ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
