"""Local Stockfish process, using UCI. No network or cloud API is used."""
from __future__ import annotations

import os
import platform
import queue
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLED = ROOT / "engines" / "stockfish" / "stockfish-linux-arm64-universal"
MOVE = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?\Z")
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class EngineError(RuntimeError):
    pass


def resolve_engine(executable=None):
    explicit = executable or os.environ.get("STOCKFISH_EXECUTABLE")
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
    elif platform.system() == "Linux" and platform.machine().lower() in {"aarch64", "arm64"}:
        candidate = BUNDLED
    elif platform.system() == "Darwin" and (ROOT.parent / "tools" / "mac_test" / "binaries" / "stockfish-macos-universal").is_file():
        candidate = ROOT.parent / "tools" / "mac_test" / "binaries" / "stockfish-macos-universal"
    else:
        found = shutil.which("stockfish")
        candidate = Path(found) if found else Path("/usr/games/stockfish")
    if not candidate.is_file():
        raise EngineError("Stockfish not found. Restore the bundled engine for your platform "
                          "or use --engine or STOCKFISH_EXECUTABLE for another build.")
    if not os.access(candidate, os.X_OK):
        raise EngineError(f"Engine is not executable. Run: chmod +x {candidate}")
    return candidate


class Stockfish:
    def __init__(self, executable=None, threads=2, hash_mb=128, skill=10, startup_timeout=15):
        if not 1 <= threads <= 4 or not 16 <= hash_mb <= 512 or not 0 <= skill <= 20:
            raise ValueError("Use threads 1..4, hash 16..512 MB, skill 0..20")
        self.executable = resolve_engine(executable)
        self.name = "Stockfish"
        self.options = set()
        self._lines = queue.Queue()
        self._recent = deque(maxlen=12)
        self._transaction = threading.Lock()
        self._closed = False
        try:
            self.process = subprocess.Popen(
                [str(self.executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
        except OSError as exc:
            raise EngineError(f"Cannot run {self.executable}: {exc}") from exc
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()
        try:
            self._send("uci")
            self._until(lambda line: line == "uciok", startup_timeout)
            for name, value in [("Threads", threads), ("Hash", hash_mb),
                                ("Ponder", "false"), ("UCI_Chess960", "false"),
                                ("Skill Level", skill)]:
                if name in self.options:
                    self._send(f"setoption name {name} value {value}")
            self._ready(startup_timeout)
            self.new_game()
        except Exception:
            self.close()
            raise

    def _read_output(self):
        try:
            for line in self.process.stdout:
                self._lines.put(line.rstrip("\r\n"))
        finally:
            self._lines.put(None)

    def _send(self, command):
        if self._closed or self.process.poll() is not None:
            raise EngineError("Stockfish process is not running")
        try:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise EngineError("Stockfish process disconnected") from exc

    def _until(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Stockfish response timed out")
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError("Stockfish response timed out") from exc
            if line is None:
                raise EngineError("Stockfish exited: " + " / ".join(self._recent))
            self._recent.append(line)
            if line.startswith("id name "):
                self.name = line[8:]
            match = re.match(r"option name (.+?) type ", line)
            if match:
                self.options.add(match[1])
            if predicate(line):
                return line

    def _ready(self, timeout=5):
        self._send("isready")
        self._until(lambda line: line == "readyok", timeout)

    def new_game(self):
        with self._transaction:
            self._send("ucinewgame")
            self._ready()

    def best_move(self, fen, legal_moves, movetime_ms=500, history=None):
        if not isinstance(movetime_ms, int) or not 50 <= movetime_ms <= 10000:
            raise ValueError("movetime_ms must be 50..10000")
        legal = tuple(legal_moves)
        if not legal:
            return None
        if not all(isinstance(m, str) and MOVE.fullmatch(m) for m in legal):
            raise ValueError("Invalid legal-move list")
        if not isinstance(fen, str) or any(ord(ch) < 32 or ord(ch) > 126 for ch in fen):
            raise ValueError("FEN must be one ASCII line")
        if len(fen.split()) != 6:
            raise ValueError("Expected complete six-field FEN")
        if history is not None:
            history = tuple(history)
            if not all(isinstance(m, str) and MOVE.fullmatch(m) for m in history):
                raise ValueError("Invalid game history")
        with self._transaction:
            self._ready()
            if history is None:
                self._send("position fen " + fen)
            else:
                # Preserve repetition history when using our start-position Game.
                self._send("position startpos" + (" moves " + " ".join(history) if history else ""))
            self._send(f"go movetime {movetime_ms} searchmoves " + " ".join(legal))
            try:
                result = self._until(lambda line: line.startswith("bestmove "), movetime_ms / 1000 + 3)
            except TimeoutError:
                # An uncertain search is discarded; never reuse a stale bestmove.
                try:
                    self._send("stop")
                finally:
                    self.close()
                raise
            move = result.split()[1]
            if move not in legal:
                raise EngineError(f"Stockfish returned a move rejected by the rules layer: {move}")
            return move

    def choose(self, game, movetime_ms=500):
        return self.best_move(game.fen(), game.legal_moves(), movetime_ms,
                              getattr(game, "move_history", None))

    def close(self):
        if self._closed:
            return
        try:
            if self.process.poll() is None:
                self._send("quit")
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
        finally:
            self._closed = True
            if self.process.stdin:
                self.process.stdin.close()
            self._reader.join(timeout=1)
            if self.process.stdout:
                self.process.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def self_test(executable=None):
    import hashlib
    opening = [f"{f}2{f}{rank}" for f in "abcdefgh" for rank in "34"] + ["b1a3", "b1c3", "g1f3", "g1h3"]
    black = [f"{f}7{f}{rank}" for f in "abcdefgh" for rank in "65"] + ["b8a6", "b8c6", "g8f6", "g8h6"]
    with Stockfish(executable) as engine:
        first = engine.best_move(START_FEN, opening, 100)
        reply = engine.best_move("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
                                 black, 100, history=["e2e4"])
        return {"engine": engine.name, "executable": str(engine.executable),
                "sha256": hashlib.sha256(engine.executable.read_bytes()).hexdigest(),
                "platform": platform.system(), "machine": platform.machine(),
                "uci_handshake": "passed", "start_position_move": first,
                "reply_to_e2e4": reply, "legal_move_check": "passed", "network_used": False}


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Test the bundled local Stockfish engine")
    parser.add_argument("--engine")
    parser.add_argument("--self-test", action="store_true", required=True)
    parser.add_argument("--report")
    args = parser.parse_args()
    result = self_test(args.engine)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    print(serialized)
    if args.report:
        Path(args.report).write_text(serialized + "\n", encoding="utf-8")
