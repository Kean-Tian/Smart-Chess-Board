#!/usr/bin/env python3
"""Play White against an OpenAI-powered Black using the project's rules engine."""

import ctypes
import json
import os
from pathlib import Path
import sys
from urllib import error, request

#link to the chess engine 
ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "build" / ("libscb_rules.dylib" if sys.platform == "darwin" else "libscb_rules.so")

# Using Ctypes to interface with the chess rules engine
class Game:
    def __init__(self):
        rules = ctypes.CDLL(str(LIBRARY))
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
        for name in ("scb_rules_is_checkmate", "scb_rules_is_stalemate", "scb_rules_is_draw", "scb_rules_is_in_check"):
            function = getattr(rules, name)
            function.argtypes = [ctypes.c_void_p]
            function.restype = ctypes.c_bool
        self.rules = rules
        self.handle = rules.scb_rules_create()
        if not self.handle:
            raise RuntimeError("Could not create the chess rules engine.")

#package to close the chess engine when done
    def close(self):
        self.rules.scb_rules_destroy(self.handle)

    def text(self, name, size):
        buffer = ctypes.create_string_buffer(size)
        if not getattr(self.rules, name)(self.handle, buffer, size):
            raise RuntimeError(f"Could not read {name} from the rules engine.")
        return buffer.value.decode("ascii")

    def play(self, move):
        try:
            return self.rules.scb_rules_play_move(self.handle, move.encode("ascii"))
        except UnicodeEncodeError:
            return False

    def status(self):
        if self.rules.scb_rules_is_checkmate(self.handle):
            return "Checkmate. White wins." if self.text("scb_rules_fen", 128).split()[1] == "b" else "Checkmate. Black wins."
        if self.rules.scb_rules_is_stalemate(self.handle):
            return "Stalemate."
        if self.rules.scb_rules_is_draw(self.handle):
            return "Draw by repetition or the 50-move rule."
        if self.rules.scb_rules_is_in_check(self.handle):
            return "Check."
        return ""

# function to ask the AI for its move based on the current FEN and legal moves
# FEN UCI -> Json -> API request -> JSON response -> move
def ask_ai_move(fen, legal_moves, api_key, model):
    payload = {
        "model": model,
        "instructions": "You play Black in chess. Pick one move from the supplied legal UCI moves. Reply with only that move, with no other text.",
        "input": f"FEN: {fen}\nLegal UCI moves: {' '.join(legal_moves)}",
        "max_output_tokens": 16,
    }
    api_request = request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(api_request, timeout=30) as response:
            result = json.load(response)
    except error.HTTPError as exc:
        raise RuntimeError(f"OpenAI API returned HTTP {exc.code}.") from exc
    except (error.URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc

    texts = [
        content["text"]
        for item in result.get("output", [])
        if item.get("type") == "message"
        for content in item.get("content", [])
        if content.get("type") == "output_text"
    ]
    move = "".join(texts).strip().lower()
    if move not in legal_moves:
        raise RuntimeError(f"AI returned an illegal move: {move!r}")
    return move

# API key -> loop 
def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Set OPENAI_API_KEY before starting the AI game.", file=sys.stderr)
        return 1
    if not LIBRARY.exists():
        print("Build the project first: cmake --build build", file=sys.stderr)
        return 1

    game = Game()
    try:
        print("You are White. Enter UCI moves (e2e4), or 'quit'.")
        print(game.text("scb_rules_board_text", 256), end="")
        while True:
            try:
                move = input("You > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if move == "quit":
                break
            if not game.play(move):
                print("Illegal move.")
                continue
            print(game.text("scb_rules_board_text", 256), end="")
            status = game.status()
            if status:
                print(status)
                if status != "Check.":
                    break

            legal_moves = game.text("scb_rules_legal_moves", 2048).split()
            try:
                ai_move = ask_ai_move(
                    game.text("scb_rules_fen", 128),
                    legal_moves,
                    api_key,
                    os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
                )
            except RuntimeError as exc:
                print(exc, file=sys.stderr)
                return 1
            if not game.play(ai_move):
                print("The rules engine rejected the AI move.", file=sys.stderr)
                return 1
            print(f"AI > {ai_move}")
            print(game.text("scb_rules_board_text", 256), end="")
            status = game.status()
            if status:
                print(status)
                if status != "Check.":
                    break
    finally:
        game.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
