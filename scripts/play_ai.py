#!/usr/bin/env python3
"""Play White against an OpenAI-powered Black using the project's rules engine."""

import json
import os
import sys
from urllib import error, request

from scb_rules import Game, LIBRARY

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
