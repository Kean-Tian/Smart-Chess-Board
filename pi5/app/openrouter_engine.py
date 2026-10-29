"""OpenRouter chess opponent. Only validated UCI moves leave this module.

API reference: https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion
"""
from __future__ import annotations

import json
import gzip
import os
import re
import zlib
from http.client import HTTPException
from dataclasses import dataclass
from urllib import error, request

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MOVE = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?\Z")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class CoachingHint:
    move: str
    hint: str


class OpenRouterError(RuntimeError):
    def __init__(self, message, retryable=True):
        super().__init__(message)
        self.retryable = retryable


def validate_api_key(value):
    if not isinstance(value, str) or not value.strip():
        raise OpenRouterError("Set OPENROUTER_API_KEY before starting AI Mode.", retryable=False)
    key = value.strip()
    if any(not 33 <= ord(character) <= 126 for character in key):
        raise OpenRouterError(
            "OPENROUTER_API_KEY contains non-ASCII characters, spaces or control characters. "
            "Paste your actual OpenRouter API key; replace any placeholder text.", retryable=False,
        )
    return key


def read_response(response):
    """Expose only response-format metadata, never raw bodies or credentials."""
    headers = getattr(response, "headers", {}) or {}
    media_type = headers.get("Content-Type", "unknown").split(";", 1)[0].strip().lower()
    if not re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", media_type):
        media_type = "unknown"
    encoding = headers.get("Content-Encoding", "identity").strip().lower()
    if encoding not in {"identity", "gzip", "deflate"}:
        raise OpenRouterError("OpenRouter returned unsupported response compression. Check your network/proxy.",
                              retryable=False)
    status = getattr(response, "status", None)
    status = str(status) if isinstance(status, int) else "unknown"
    raw = response.read(MAX_RESPONSE_BYTES + 1)
    details = f"HTTP {status}, type={media_type}, encoding={encoding}, bytes={len(raw)}"
    if len(raw) > MAX_RESPONSE_BYTES:
        raise OpenRouterError(f"OpenRouter response exceeded the size limit ({details}).", retryable=False)
    try:
        if encoding == "gzip" or raw.startswith(b"\x1f\x8b"):
            raw = gzip.decompress(raw)
        elif encoding == "deflate":
            raw = zlib.decompress(raw)
    except (OSError, EOFError, zlib.error) as exc:
        raise OpenRouterError(f"OpenRouter returned damaged compressed data ({details}).") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise OpenRouterError(f"OpenRouter decoded response exceeded the size limit ({details}).", retryable=False)
    try:
        text = raw.decode("utf-8-sig").strip().lstrip("\ufeff").lstrip()
    except UnicodeError as exc:
        raise OpenRouterError(f"OpenRouter returned non-UTF-8 data ({details}). Check your network/proxy.") from exc
    if not text:
        raise OpenRouterError(f"OpenRouter returned an empty response ({details}). Try again or check your network/proxy.")
    if media_type == "text/html" or text.lower().startswith(("<!doctype html", "<html")):
        raise OpenRouterError(f"OpenRouter returned an HTML page instead of API JSON ({details}). "
                              "Check your network/proxy or a sign-in/block page.", retryable=False)
    if media_type == "text/event-stream" or text.startswith(("data:", ": OPENROUTER")):
        raise OpenRouterError(f"OpenRouter returned an event stream despite stream=false ({details}). "
                              "Check your network/proxy.", retryable=False)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise OpenRouterError(f"OpenRouter returned malformed JSON ({details}; "
                              f"line={getattr(exc, 'lineno', 'unknown')}, column={getattr(exc, 'colno', 'unknown')}). "
                              "The response may be incomplete; retry or check your network/proxy.") from exc


def api_error(result, status=None, retry_after=None):
    """Report actionable API error codes without echoing arbitrary server text."""
    problem = result.get("error") if isinstance(result, dict) else None
    code = problem.get("code", status) if isinstance(problem, dict) else status
    if isinstance(code, str) and code.isdecimal():
        code = int(code)
    if not isinstance(code, int):
        code = None
    hints = {
        400: "Check the model ID and request settings.",
        401: "Check your OpenRouter API key; use --set-api-key to replace the saved key.",
        402: "Check your OpenRouter account credits and spending limits.",
        403: "Check your account permissions and model access.",
        404: "Check OPENROUTER_MODEL or --model.",
        429: "Rate limit reached; wait before retrying.",
        503: "No available provider; try again later or choose another model.",
    }
    retryable = code is None or code == 408 or code >= 500
    message = f"OpenRouter API error {code if code is not None else 'unknown'}. "
    message += hints.get(code, "Try again or choose another OpenRouter model.")
    if retry_after is not None:
        message += " The server requested a delay; wait before retrying."
        retryable = False
    return OpenRouterError(message, retryable=retryable)


def chat_completion(messages, api_key, model, timeout=120):
    """Shared HTTP transport for the opponent and the coach."""
    api_key = validate_api_key(api_key)
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 2048,
        "stream": False,
    }
    api_request = request.Request(
        ENDPOINT, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                 "Accept": "application/json", "Accept-Encoding": "identity",
                 "User-Agent": "Smart-Chess-Board/1.0"},
        method="POST",
    )
    try:
        with request.urlopen(api_request, timeout=timeout) as response:
            result = read_response(response)
    except error.HTTPError as exc:
        try:
            result = read_response(exc)
        except OpenRouterError as detail:
            raise OpenRouterError(f"OpenRouter HTTP {exc.code}. {detail}",
                                  retryable=detail.retryable and (exc.code == 408 or exc.code >= 500)) from exc
        finally:
            exc.close()
        raise api_error(result, exc.code, (exc.headers or {}).get("Retry-After")) from exc
    except KeyboardInterrupt as exc:
        raise OpenRouterError("OpenRouter request cancelled.", retryable=False) from exc
    except (error.URLError, TimeoutError, OSError, HTTPException) as exc:
        raise OpenRouterError("OpenRouter connection failed or timed out.") from exc
    if not isinstance(result, dict):
        raise OpenRouterError("OpenRouter returned an unexpected response format.")
    if result.get("error"):
        raise api_error(result)
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise OpenRouterError("OpenRouter returned no move.")
    choice = choices[0]
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if choice.get("finish_reason") in {"error", "content_filter", "length"}:
        raise OpenRouterError("OpenRouter did not finish a move; try again or choose another model.")
    if not isinstance(content, str) or not content.strip():
        raise OpenRouterError("OpenRouter returned no move; try again or choose another model.")
    return content.strip()


def legal_position(fen, legal_moves):
    fields = fen.split()
    legal = tuple(legal_moves)
    if len(fields) != 6 or fields[1] not in {"w", "b"}:
        raise ValueError("Expected a complete chess FEN")
    if not legal or not all(isinstance(m, str) and MOVE.fullmatch(m) for m in legal):
        raise ValueError("Expected legal UCI moves")
    return ("White" if fields[1] == "w" else "Black"), legal


def ask_ai_move(fen, legal_moves, api_key, model, timeout=120):
    """Keep the original OpenRouter request method, with side-aware prompts."""
    side, legal = legal_position(fen, legal_moves)
    messages = [
        {"role": "system", "content": f"You play {side} in standard chess. "
         "Pick one move from the supplied legal UCI moves. "
         "Reply with only that move, with no other text."},
        {"role": "user", "content": f"FEN: {fen}\nLegal UCI moves: {' '.join(legal)}"},
    ]
    move = chat_completion(messages, api_key, model, timeout).lower()
    if move not in legal:
        raise OpenRouterError("OpenRouter returned a move outside the legal-move list.")
    return move


def ask_coaching_hint(fen, legal_moves, api_key, model, timeout=120):
    side, legal = legal_position(fen, legal_moves)
    messages = [
        {"role": "system", "content": f"You coach {side}, the player to move, in a game between two humans. "
         "Recommend exactly one move from the supplied legal UCI moves and explain its purpose "
         "in one short English sentence, at most 20 words. Focus only on this player's next move. "
         'Return only a JSON object with string fields "move" and "hint", without Markdown.'},
        {"role": "user", "content": f"FEN: {fen}\nLegal UCI moves: {' '.join(legal)}"},
    ]
    content = chat_completion(messages, api_key, model, timeout)
    try:
        advice = json.loads(content)
    except ValueError as exc:
        raise OpenRouterError("AI coach returned an invalid hint format; try again.") from exc
    if not isinstance(advice, dict):
        raise OpenRouterError("AI coach returned an invalid hint format; try again.")
    move, hint = advice.get("move"), advice.get("hint")
    if not isinstance(move, str) or move.strip().lower() not in legal:
        raise OpenRouterError("AI coach suggested a move outside the legal-move list.")
    if not isinstance(hint, str) or not hint.strip() or len(hint) > 1000:
        raise OpenRouterError("AI coach returned no usable explanation; try again.")
    hint = " ".join(hint.split())
    if not hint.isprintable():
        raise OpenRouterError("AI coach returned an unusable explanation; try again.")
    words = hint.split()
    if len(words) > 20:
        hint = " ".join(words[:20]) + "..."
    return CoachingHint(move.strip().lower(), hint)


class OpenRouter:
    def __init__(self, api_key=None, model=None, timeout=120, attempts=3, report=print):
        self.api_key = validate_api_key(api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", ""))
        self.model = (model or os.environ.get("OPENROUTER_MODEL") or "openrouter/free").strip()
        if not self.model or any(ord(c) < 32 for c in self.model):
            raise ValueError("Provide a valid OpenRouter model ID")
        if timeout <= 0 or not 1 <= attempts <= 3:
            raise ValueError("Use a positive timeout and 1..3 attempts")
        self.timeout, self.attempts, self.report = timeout, attempts, report
        self.name = f"OpenRouter ({self.model})"

    def choose(self, game, movetime_ms=500):
        # movetime_ms configures Stockfish only; OpenRouter uses its HTTP timeout.
        legal = tuple(game.legal_moves())
        if not legal:
            return None
        fen = game.fen()
        return self._retry(lambda: ask_ai_move(fen, legal, self.api_key, self.model, self.timeout),
                           "AI is thinking")

    def coach(self, game):
        legal = tuple(game.legal_moves())
        if not legal:
            return None
        fen = game.fen()
        return self._retry(lambda: ask_coaching_hint(fen, legal, self.api_key, self.model, self.timeout),
                           "AI coach is thinking")

    def _retry(self, operation, label):
        for attempt in range(1, self.attempts + 1):
            self.report(f"{label}... (attempt {attempt}/{self.attempts})")
            try:
                return operation()
            except OpenRouterError as exc:
                if not exc.retryable or attempt == self.attempts:
                    raise
                self.report(str(exc))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass
