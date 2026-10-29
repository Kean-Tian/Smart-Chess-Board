import io
import gzip
import json
import os
import sys
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
from urllib import error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from openrouter_engine import OpenRouter, OpenRouterError, ask_ai_move
from stockfish_engine import START_FEN


def response(move="e2e4", **choice):
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": move}, **choice}]}).encode())


def http_response(body, media_type="application/json", encoding="identity"):
    reply = io.BytesIO(body)
    reply.status = 200
    reply.headers = {"Content-Type": media_type, "Content-Encoding": encoding}
    return reply


class OpenRouterTests(unittest.TestCase):
    def test_invalid_key_is_rejected_before_any_network_request(self):
        for key in ["你的密钥", "sk-or-中文", "sk-or-é", "sk-or-one two", "sk-or-one\ntwo", "sk-or-\x00", "sk-or-\x7f"]:
            with self.subTest(key_kind="invalid header"), patch("openrouter_engine.request.urlopen") as send:
                for invoke in [lambda: OpenRouter(key),
                               lambda: ask_ai_move(START_FEN, ["e2e4"], key, "model")]:
                    with self.assertRaisesRegex(OpenRouterError, "actual OpenRouter API key") as raised:
                        invoke()
                    self.assertFalse(raised.exception.retryable)
                    self.assertNotIn(key, str(raised.exception))
                send.assert_not_called()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "你的密钥"}), patch("openrouter_engine.request.urlopen") as send:
            with self.assertRaises(OpenRouterError):
                OpenRouter()
            send.assert_not_called()

    def test_request_side_model_and_strict_legal_move_validation(self):
        for side, legal, answer in [("w", ["e2e4"], " E2E4\n"), ("b", ["e7e5"], "e7e5")]:
            fen = START_FEN.replace(" w ", f" {side} ")
            with patch("openrouter_engine.request.urlopen", return_value=response(answer)) as send:
                self.assertEqual(ask_ai_move(fen, legal, "test-key", "test/model"), legal[0])
            req = send.call_args.args[0]
            payload = json.loads(req.data)
            self.assertEqual(req.full_url, "https://openrouter.ai/api/v1/chat/completions")
            self.assertEqual(req.get_header("Authorization"), "Bearer test-key")
            self.assertEqual(req.get_header("Accept"), "application/json")
            self.assertEqual(req.get_header("Accept-encoding"), "identity")
            self.assertEqual(payload["model"], "test/model")
            self.assertIn("White" if side == "w" else "Black", payload["messages"][0]["content"])
            self.assertIn(fen, payload["messages"][1]["content"])
            self.assertEqual(send.call_args.kwargs["timeout"], 120)

    def test_response_compression_whitespace_and_bom(self):
        body = json.dumps({"choices": [{"message": {"content": "e2e4"}}]}).encode()
        examples = [(b" \n\xef\xbb\xbf" + body, "identity"),
                    (gzip.compress(body), "gzip"), (gzip.compress(body), "identity"),
                    (zlib.compress(body), "deflate")]
        for raw, encoding in examples:
            with self.subTest(encoding=encoding), patch("openrouter_engine.request.urlopen",
                    return_value=http_response(raw, encoding=encoding)):
                self.assertEqual(ask_ai_move(START_FEN, ["e2e4"], "key", "model"), "e2e4")

    def test_non_json_diagnostics_do_not_echo_response_bodies_or_keys(self):
        examples = [(b"", "application/json", "empty response", True),
                    (b"<!doctype html><html>secret-key</html>", "text/html", "HTML page", False),
                    (b'{"secret-key":', "application/json", "malformed JSON", True),
                    (b"\xffsecret-key", "application/json", "non-UTF-8", True),
                    (b"data: secret-key\n\n", "text/event-stream", "event stream", False)]
        for body, media, message, retryable in examples:
            with self.subTest(message=message), patch("openrouter_engine.request.urlopen",
                    return_value=http_response(body, media_type=media)):
                with self.assertRaisesRegex(OpenRouterError, message) as raised:
                    ask_ai_move(START_FEN, ["e2e4"], "secret-key", "model")
                diagnostic = str(raised.exception)
                self.assertIn("HTTP 200", diagnostic)
                self.assertIn("bytes=", diagnostic)
                self.assertNotIn("secret-key", diagnostic)
                self.assertEqual(raised.exception.retryable, retryable)
        with patch("openrouter_engine.request.urlopen",
                   return_value=http_response(b"not gzip", encoding="gzip")):
            with self.assertRaisesRegex(OpenRouterError, "damaged compressed"):
                ask_ai_move(START_FEN, ["e2e4"], "key", "model")

    def test_api_errors_inside_http_200_and_http_error_responses(self):
        for code in [401, 402, 403, 404, 429, 503]:
            body = json.dumps({"error": {"code": code, "message": "do not echo secret-key"}}).encode()
            with self.subTest(code=code), patch("openrouter_engine.request.urlopen", return_value=http_response(body)):
                with self.assertRaisesRegex(OpenRouterError, str(code)) as raised:
                    ask_ai_move(START_FEN, ["e2e4"], "key", "model")
                self.assertNotIn("secret-key", str(raised.exception))
        for code, content, media in [(401, b'{"error":{"code":401}}', "application/json"),
                                     (403, b'<html>blocked</html>', "text/html")]:
            failure = error.HTTPError("url", code, "error", {"Content-Type": media}, io.BytesIO(content))
            with self.subTest(http_code=code), patch("openrouter_engine.request.urlopen", side_effect=failure):
                with self.assertRaisesRegex(OpenRouterError, str(code)) as raised:
                    ask_ai_move(START_FEN, ["e2e4"], "key", "model")
                self.assertFalse(raised.exception.retryable)
        failure = error.HTTPError("url", 503, "error", {"Content-Type": "application/json", "Retry-After": "60"},
                                  io.BytesIO(b'{"error":{"code":503}}'))
        with patch("openrouter_engine.request.urlopen", side_effect=failure):
            with self.assertRaisesRegex(OpenRouterError, "wait before retrying") as raised:
                ask_ai_move(START_FEN, ["e2e4"], "key", "model")
            self.assertFalse(raised.exception.retryable)

    def test_invalid_responses_are_rejected(self):
        results = [[], {}, {"error": {"message": "failed"}}, {"choices": []},
                   {"choices": [None]}, {"choices": [{"message": None}]},
                   {"choices": [{"message": {"content": None}}]}]
        for result in results:
            with self.subTest(result=result), patch("openrouter_engine.request.urlopen",
                    return_value=io.BytesIO(json.dumps(result).encode())):
                with self.assertRaises(OpenRouterError):
                    ask_ai_move(START_FEN, ["e2e4"], "key", "model")
        for move in ["e2e5", "I choose e2e4", "", "```e2e4```"]:
            with self.subTest(move=move), patch("openrouter_engine.request.urlopen", return_value=response(move)):
                with self.assertRaises(OpenRouterError):
                    ask_ai_move(START_FEN, ["e2e4"], "key", "model")
        with patch("openrouter_engine.request.urlopen", return_value=response(finish_reason="length")):
            with self.assertRaises(OpenRouterError):
                ask_ai_move(START_FEN, ["e2e4"], "key", "model")
        with patch("openrouter_engine.request.urlopen", return_value=io.BytesIO(b"not JSON")):
            with self.assertRaises(OpenRouterError):
                ask_ai_move(START_FEN, ["e2e4"], "key", "model")

    def test_retry_limit_and_permanent_http_error(self):
        class Game:
            def fen(self): return START_FEN
            def legal_moves(self): return ["e2e4"]
        opponent = OpenRouter("key", "model", report=lambda *_: None)
        with patch("openrouter_engine.request.urlopen", side_effect=error.URLError("offline")) as send:
            with self.assertRaises(OpenRouterError):
                opponent.choose(Game())
            self.assertEqual(send.call_count, 3)
        with patch("openrouter_engine.request.urlopen", side_effect=[response("e2e5"), response()]) as send:
            self.assertEqual(opponent.choose(Game()), "e2e4")
            self.assertEqual(send.call_count, 2)
        with patch("openrouter_engine.request.urlopen",
                   side_effect=error.HTTPError("url", 401, "Unauthorized", {}, io.BytesIO(b""))) as send:
            with self.assertRaises(OpenRouterError):
                opponent.choose(Game())
            self.assertEqual(send.call_count, 1)
        with patch("openrouter_engine.request.urlopen", side_effect=KeyboardInterrupt) as send:
            with self.assertRaisesRegex(OpenRouterError, "cancelled"):
                opponent.choose(Game())
            self.assertEqual(send.call_count, 1)

    def test_missing_key_and_no_legal_moves_never_send_requests(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}), patch("openrouter_engine.request.urlopen") as send:
            with self.assertRaisesRegex(OpenRouterError, "OPENROUTER_API_KEY"):
                OpenRouter()
            send.assert_not_called()
        with patch.dict(os.environ, {"OPENROUTER_MODEL": "chosen/model"}):
            self.assertEqual(OpenRouter("key").model, "chosen/model")
        class Finished:
            def legal_moves(self): return []
        with patch("openrouter_engine.request.urlopen") as send:
            self.assertIsNone(OpenRouter("key").choose(Finished()))
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
