import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import play_ai


class PlayAiTests(unittest.TestCase):
    def test_rules_and_api_move(self):
        game = play_ai.Game()
        try:
            self.assertTrue(game.play("e2e4"))
            legal_moves = game.text("scb_rules_legal_moves", 2048).split()
            self.assertIn("e7e5", legal_moves)
            self.assertNotIn("e2e5", legal_moves)
            response = {
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "e7e5"}]}]
            }
            with patch.object(play_ai.request, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as urlopen:
                move = play_ai.ask_ai_move(game.text("scb_rules_fen", 128), legal_moves, "test-key", "gpt-4.1-mini")
                self.assertEqual(move, "e7e5")
                self.assertIn("FEN:", json.loads(urlopen.call_args.args[0].data)["input"])
            self.assertTrue(game.play(move))
            self.assertIn("White to move", game.text("scb_rules_board_text", 256))
            with patch.object(play_ai.request, "urlopen", return_value=io.BytesIO(b'{"output":[]}')):
                with self.assertRaisesRegex(RuntimeError, "illegal move"):
                    play_ai.ask_ai_move(game.text("scb_rules_fen", 128), legal_moves, "test-key", "gpt-4.1-mini")
        finally:
            game.close()

    def test_interactive_round(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch("builtins.input", side_effect=["e2e4", "quit"]), patch.object(play_ai, "ask_ai_move", return_value="e7e5"), redirect_stdout(output):
            self.assertEqual(play_ai.main(), 0)
        self.assertIn("AI > e7e5", output.getvalue())
        self.assertIn("White to move", output.getvalue())


if __name__ == "__main__":
    unittest.main()
