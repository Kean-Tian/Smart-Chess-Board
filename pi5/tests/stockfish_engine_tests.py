import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from stockfish_engine import Stockfish, EngineError, START_FEN

FAKE = '''import os,sys
mode=os.environ.get("SCB_FAKE_MODE", "normal")
for command in sys.stdin:
 command=command.strip()
 log=os.environ.get("SCB_FAKE_LOG")
 if log:
  with open(log,"a") as f:f.write(command+"\\n")
 if command=="uci" and mode!="no_uci":
  print("id name Stockfish Test")
  for name in ["Threads","Hash","Ponder","UCI_Chess960","Skill Level"]:
   print("option name "+name+" type spin default 1 min 0 max 512")
  print("uciok",flush=True)
 elif command=="isready":print("readyok",flush=True)
 elif command.startswith("go "):
  move=command.split("searchmoves ")[1].split()[0]
  print("info depth 1 nodes 42",flush=True)
  print("bestmove "+("a1a9" if mode=="illegal" else move),flush=True)
 elif command=="quit":break
'''


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "fake-stockfish"
        self.log = Path(self.tmp.name) / "commands.log"
        self.path.write_text("#!" + sys.executable + "\n" + FAKE)
        self.path.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def test_handshake_search_history_and_quit(self):
        with patch.dict(os.environ, {"SCB_FAKE_LOG": str(self.log)}):
            with Stockfish(self.path) as engine:
                self.assertEqual(engine.name, "Stockfish Test")
                self.assertEqual(engine.best_move(START_FEN, ["e2e4", "d2d4"], 50), "e2e4")
                self.assertEqual(engine.best_move(START_FEN, ["e7e5"], 50, history=["e2e4"]), "e7e5")
                self.assertIsNone(engine.best_move(START_FEN, [], 50))
            self.assertIsNotNone(engine.process.poll())
        commands = self.log.read_text()
        self.assertIn("setoption name Threads value 2", commands)
        self.assertIn("setoption name Hash value 128", commands)
        self.assertIn("position startpos moves e2e4", commands)
        self.assertIn("go movetime 50 searchmoves e2e4 d2d4", commands)
        self.assertIn("quit", commands)

    def test_illegal_engine_output_is_rejected(self):
        with patch.dict(os.environ, {"SCB_FAKE_MODE": "illegal"}):
            with Stockfish(self.path) as engine:
                with self.assertRaises(EngineError):
                    engine.best_move(START_FEN, ["e2e4"], 50)

    def test_argument_and_line_injection_checks(self):
        with Stockfish(self.path) as engine:
            for fen, legal, duration in [(START_FEN + "\nquit", ["e2e4"], 50),
                                          (START_FEN, ["e2e4\nquit"], 50),
                                          (START_FEN, ["e2e4"], 0)]:
                with self.assertRaises(ValueError):
                    engine.best_move(fen, legal, duration)
            with self.assertRaises(ValueError):
                engine.best_move(START_FEN, ["e2e4"], 50, history=["quit"])
        with self.assertRaises(EngineError):
            Stockfish(Path(self.tmp.name) / "missing")

    def test_missing_uci_ack_is_bounded(self):
        with patch.dict(os.environ, {"SCB_FAKE_MODE": "no_uci"}):
            with self.assertRaises(TimeoutError):
                Stockfish(self.path, startup_timeout=0.05)


if __name__ == "__main__":
    unittest.main()
