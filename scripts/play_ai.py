#!/usr/bin/env python3
"""Play White against an OpenRouter-powered Black using the project's rules engine."""

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
        "messages": [
            {"role": "system", "content": "You play Black in chess. Pick one move from the supplied legal UCI moves. Reply with only that move, with no other text."},
            {"role": "user", "content": f"FEN: {fen}\nLegal UCI moves: {' '.join(legal_moves)}"},
        ],
        "max_tokens": 2048,
    }
    api_request = request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(api_request, timeout=120) as response:
            result = json.load(response)
    except error.HTTPError as exc:
        raise RuntimeError(f"OpenRouter API returned HTTP {exc.code}.") from exc
    except (error.URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"OpenRouter API request failed: {exc}") from exc

    if not isinstance(result, dict):
        raise RuntimeError("OpenRouter returned an unexpected response format.")
    if result.get("error"):
        raise RuntimeError(f"OpenRouter API error: {result['error']}")
    try:
        content = result["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Missing text content")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        choice = (result.get("choices") or [{}])[0]
        reason = choice.get("finish_reason", "unknown") if isinstance(choice, dict) else "unknown"
        raise RuntimeError(f"OpenRouter returned no move (finish_reason={reason}). "
                           "If length, the model exhausted its output budget while thinking.") from exc
    move = content.strip().lower()
    if move not in legal_moves:
        raise RuntimeError(f"AI returned an illegal move: {move!r}")
    return move

# API key -> loop 
def main():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Set OPENROUTER_API_KEY before starting the AI game.", file=sys.stderr)
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
            ai_move = None
            while ai_move is None:
                for attempt in range(1, 4):
                    print(f"AI is thinking... (attempt {attempt}/3, timeout 120s)", flush=True)
                    try:
                        ai_move = ask_ai_move(
                            game.text("scb_rules_fen", 128), legal_moves, api_key,
                            os.environ.get("OPENROUTER_MODEL", "openrouter/free"),
                        )
                        break
                    except RuntimeError as exc:
                        print(exc, file=sys.stderr, flush=True)
                    except KeyboardInterrupt:
                        print("\nRequest cancelled. The current position is preserved.")
                        break
                if ai_move is None:
                    try:
                        action = input("Position preserved, Black to move. Enter to retry, or 'quit': ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        return 0
                    if action == "quit":
                        return 0
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
