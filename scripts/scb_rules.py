#!/usr/bin/env python3
"""Small Python wrapper around the project's C chess-rules library."""

import ctypes
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "build" / ("libscb_rules.dylib" if sys.platform == "darwin" else "libscb_rules.so")


class Game:
    """Own a rules-engine game and expose its text-based C API to Python."""

    def __init__(self, library=LIBRARY):
        rules = ctypes.CDLL(str(library))
        rules.scb_rules_create.restype = ctypes.c_void_p
        rules.scb_rules_destroy.argtypes = [ctypes.c_void_p]
        for name in ("scb_rules_is_legal_move", "scb_rules_play_move"):
            function = getattr(rules, name)
            function.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            function.restype = ctypes.c_bool
        for name in ("scb_rules_fen", "scb_rules_board_text", "scb_rules_legal_moves"):
            function = getattr(rules, name)
            function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
            function.restype = ctypes.c_size_t
        for name in (
            "scb_rules_is_checkmate",
            "scb_rules_is_stalemate",
            "scb_rules_is_draw",
            "scb_rules_is_in_check",
        ):
            function = getattr(rules, name)
            function.argtypes = [ctypes.c_void_p]
            function.restype = ctypes.c_bool
        self.rules = rules
        self.handle = rules.scb_rules_create()
        if not self.handle:
            raise RuntimeError("Could not create the chess rules engine.")

    def close(self):
        if self.handle:
            self.rules.scb_rules_destroy(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        self.close()

    def text(self, name, size):
        buffer = ctypes.create_string_buffer(size)
        if not getattr(self.rules, name)(self.handle, buffer, size):
            raise RuntimeError(f"Could not read {name} from the rules engine.")
        return buffer.value.decode("ascii")

    def fen(self):
        return self.text("scb_rules_fen", 128)

    def legal_moves(self):
        return self.text("scb_rules_legal_moves", 4096).split()

    def board_text(self):
        return self.text("scb_rules_board_text", 256)

    def play(self, move):
        try:
            return self.rules.scb_rules_play_move(self.handle, move.encode("ascii"))
        except UnicodeEncodeError:
            return False

    def status(self):
        if self.rules.scb_rules_is_checkmate(self.handle):
            return "Checkmate. White wins." if self.fen().split()[1] == "b" else "Checkmate. Black wins."
        if self.rules.scb_rules_is_stalemate(self.handle):
            return "Stalemate."
        if self.rules.scb_rules_is_draw(self.handle):
            return "Draw by repetition or the 50-move rule."
        if self.rules.scb_rules_is_in_check(self.handle):
            return "Check."
        return ""
