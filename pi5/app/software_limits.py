"""Software targets from the Team 24 specification, not hardware measurements."""
import argparse

DEFAULT_MOVE_TIME_MS = 3000
MIN_GAME_MOVE_TIME_MS = 2000
MAX_ENGINE_TURN_MS = 5000
DEFAULT_ENGINE_THREADS = 1
DEFAULT_ENGINE_HASH_MB = 16
FEEDBACK_ACK_TIMEOUT_S = 0.08
BOARD_EVENT_POLL_S = 0.005


def game_move_time(value):
    try:
        value = int(value)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("Move time must be 2000..5000 ms") from exc
    if not MIN_GAME_MOVE_TIME_MS <= value <= MAX_ENGINE_TURN_MS:
        raise argparse.ArgumentTypeError("Move time must be 2000..5000 ms")
    return value
