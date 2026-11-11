"""Authoritative physical-game state for the native UI, independent of widgets."""
from concurrent.futures import ThreadPoolExecutor
import time

from board_game import Game, expected_occupancy, occupancy, fen_board
from stockfish_engine import Stockfish

START_OCCUPANCY = 0xFFFF00000000FFFF


class GameSession:
    def __init__(self, store, *, now=time.monotonic, game_factory=Game, engine_factory=Stockfish):
        self.store, self.now = store, now
        self.game_factory, self.engine_factory = game_factory, engine_factory
        self.game = None
        self.engine = None
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scb-engine")
        self.search = None
        self.search_key = None
        self.search_role = None
        self.generation = 0
        self.connected = False
        self.mask = None
        self.board_at = None
        self.board_generation = 0
        self.committed_generation = -1
        self.ready = False
        self.verified = False
        self.active = self.paused = False
        self.game_id = None
        self.mode = "pvp"
        self.human = "w"
        self.minutes = 10
        self.white = self.black = None
        self.clocks = [None, None]
        self.last_tick = now()
        self.pending = None
        self.promotions = []
        self.restore = False
        self.computer_move = ""
        self.last_move = ""
        self.hint = ""
        self.message = "Connect the board to begin."
        self.result = "*"
        self.reason = ""
        self.hint_error = ""

    def fresh(self):
        return self.connected and self.board_at is not None and self.now() - self.board_at < 2.0

    def synchronized(self):
        return self.fresh() and self.game is not None and self.mask == occupancy(fen_board(self.game.fen()))

    def tick(self):
        now = self.now()
        elapsed = max(0.0, now - self.last_tick) * 1000
        self.last_tick = now
        if self.active and not self.paused and self.minutes:
            side = 0 if self.game.fen().split()[1] == "w" else 1
            self.clocks[side] = max(0.0, self.clocks[side] - elapsed)
            if not self.clocks[side]:
                # Clock expiry is measured; do not invent a FIDE result without material adjudication.
                self.pause("Time expired. End the game and record its result.")
        if self.active and not self.paused and not self.fresh():
            self.pause("Board data is stale. Reconnect and restore the current position.")
        self.poll_search()

    def clock_values(self):
        return tuple(None if value is None else max(0, round(value)) for value in self.clocks)

    def connection(self, connected):
        self.connected = connected
        if not connected:
            self.ready = self.verified = False
            self.board_at = None
            if self.active and not self.paused:
                self.pause("Board disconnected. Reconnect and restore the current position.")

    def prepare(self, mode, white_id, black_id, human, minutes):
        if self.active:
            raise ValueError("End the current game before preparing another")
        if mode not in {"pvp", "pvc", "coach"} or human not in {"w", "b"} or minutes not in {0, 5, 10}:
            raise ValueError("Invalid game settings")
        if mode == "pvc":
            player = self.store.player(white_id if human == "w" else black_id)
            computer = {"id": None, "name": "Stockfish"}
            white, black = (player, computer) if human == "w" else (computer, player)
        else:
            white, black = self.store.player(white_id), self.store.player(black_id)
            if white["id"] == black["id"]:
                raise ValueError("Choose two different saved players")
        game = self.game_factory()
        if self.game:
            self.game.close()
        self.game = game
        self.generation += 1
        self.active = self.paused = False
        self.search_key = None
        self.mode, self.human, self.minutes = mode, human, minutes
        self.white, self.black = white, black
        self.ready = self.verified = False
        self.game_id = None
        self.last_move = self.computer_move = self.hint = self.hint_error = ""
        self.pending = None
        self.promotions = []
        self.restore = False
        self.result, self.reason = "*", ""
        self.message = "Arrange the standard starting position, then check the board."

    def check(self):
        if self.game is None or self.active:
            raise ValueError("Prepare a new game first")
        self.verified = False
        self.ready = self.fresh() and self.mask == START_OCCUPANCY
        self.message = ("Occupancy matches. Confirm the piece types and colors before starting."
                        if self.ready else "Starting occupancy does not match, or board data is unavailable.")
        return self.ready

    def start(self, verified):
        if self.game is None or self.game.move_history or self.active or not self.ready or not self.fresh() or self.mask != START_OCCUPANCY:
            raise ValueError("Check a fresh, matching starting board first")
        if verified is not True:
            raise ValueError("Confirm the physical piece types and colors")
        self.clocks = [self.minutes * 60000 if self.minutes else None] * 2
        self.game_id = self.store.start(self.white, self.black, self.mode, self.minutes, self.game.fen(), self.clock_values())
        self.verified = True
        self.active, self.paused = True, False
        self.last_tick = self.now()
        self.message = "White to move. Play on the physical board."
        self.committed_generation = self.board_generation
        self.maybe_search()

    def on_board(self, mask):
        self.mask = mask
        self.board_at = self.now()
        self.board_generation += 1
        if not self.active:
            if self.ready and mask != START_OCCUPANCY:
                self.ready = self.verified = False
            return
        if self.synchronized():
            self.restore = False
            self.pending = None
            self.promotions = []
            if not self.paused:
                self.message = "Board synchronized."
        elif self.pending and not self.paused:
            self.commit(self.pending)

    def event(self, payload):
        if not self.active or self.paused or self.committed_generation == self.board_generation:
            return
        if payload.startswith("MOVE "):
            self.commit(payload.split()[1])
        elif payload.startswith("AMBIGUOUS"):
            self.message = "Ambiguous board change. Finish the move, or use Confirm move."
        elif payload.startswith("LIFT"):
            self.message = "Piece lifted. Complete the move on the board."

    def commit(self, move, *, explicit=False):
        self.tick_clock_only()
        accepted_at = self.last_tick
        if not self.active or self.paused or not self.fresh() or self.restore:
            raise ValueError("Resume and synchronize the board before confirming a move")
        legal = self.game.legal_moves()
        choices = [m for m in legal if m == move or (len(move) == 4 and m[:4] == move)]
        if not choices:
            self.pending = None
            self.restore = True
            self.message = "Illegal move. Restore the last accepted position; use View current position to check it."
            return False
        if len(choices) > 1:
            self.pending = move
            self.promotions = choices
            self.message = "Place the promoted piece, then choose Queen, Rook, Bishop or Knight."
            return False
        move = choices[0]
        if self.mode == "pvc" and self.game.fen().split()[1] != self.human:
            if not self.computer_move or move != self.computer_move:
                self.restore = True
                self.message = "Restore the board, then execute the displayed computer move."
                return False
        if expected_occupancy(self.game.fen(), move) != self.mask:
            self.pending = move
            self.message = "Waiting for the complete physical move."
            return False
        # Build a candidate first: a failed SQLite commit must not advance the live game.
        candidate = self.game_factory()
        try:
            for prior in self.game.move_history:
                if not candidate.play(prior):
                    raise RuntimeError("Could not reconstruct the current position")
            if not candidate.play(move):
                raise ValueError("Rules rejected this move")
            status = candidate.status()
            result = "*"
            if status.startswith("Checkmate"):
                result = "0-1" if candidate.fen().split()[1] == "w" else "1-0"
            elif status and status != "Check.":
                result = "1/2-1/2"
            self.store.move(self.game_id, len(candidate.move_history), move, candidate.fen(), self.clock_values(), result, status)
        except BaseException:
            candidate.close()
            self.pause("Move was not saved. Restore the board before resuming.")
            self.restore = True
            raise
        self.game.close()
        self.game = candidate
        self.last_move, self.pending = move, None
        self.promotions = []
        self.computer_move = self.hint = self.hint_error = ""
        self.committed_generation = self.board_generation
        self.result, self.reason = result, status
        self.message = status or "Move accepted."
        if result != "*":
            self.active = self.ready = self.verified = False
        self.last_tick = accepted_at
        self.maybe_search()
        return True

    def tick_clock_only(self):
        # A command received between timer ticks must charge elapsed time to the old turn.
        now = self.now()
        if self.active and not self.paused and self.minutes:
            i = 0 if self.game.fen().split()[1] == "w" else 1
            self.clocks[i] = max(0.0, self.clocks[i] - max(0.0, now - self.last_tick) * 1000)
            if not self.clocks[i]:
                self.pause("Time expired. End the game and record its result.")
        self.last_tick = now

    def pause(self, reason="Game paused."):
        if not self.active:
            raise ValueError("There is no active game")
        if not self.paused:
            self.paused = True
            self.store.checkpoint(self.game_id, self.clock_values(), "paused", reason)
        self.message = reason

    def resume(self):
        if not self.active or not self.paused or not self.synchronized():
            raise ValueError("Restore the current position and reconnect before resuming")
        if self.minutes and any(value <= 0 for value in self.clocks):
            raise ValueError("A clock has expired. End the game and record its result")
        self.paused = False
        self.pending = None
        self.restore = False
        self.store.checkpoint(self.game_id, self.clock_values(), "active")
        self.last_tick = self.now()
        self.message = "Game resumed."
        self.maybe_search()

    def end(self, result="*"):
        if not self.active:
            raise ValueError("There is no active game")
        if result not in {"*", "1-0", "0-1", "1/2-1/2"}:
            raise ValueError("Invalid game result")
        self.tick_clock_only()
        reason = "Ended by players" if result == "*" else "Result confirmed by players"
        self.store.checkpoint(self.game_id, self.clock_values(), "completed", reason, result)
        self.active = self.paused = self.ready = self.verified = False
        self.result, self.reason, self.message = result, reason, reason
        self.generation += 1
        self.pending = None
        self.promotions = []

    def _search_move(self, fen, legal, history):
        if self.engine is None:
            self.engine = self.engine_factory()
        return self.engine.best_move(fen, legal, 2000, history)

    def maybe_search(self, force_hint=False):
        if not self.active or self.paused or not self.synchronized() or self.search:
            return
        if self.hint_error and not force_hint:
            return
        computer = self.mode == "pvc" and self.game.fen().split()[1] != self.human
        if not computer and not (force_hint or self.mode == "coach"):
            return
        if computer and self.computer_move:
            return
        if not computer and self.hint and not force_hint:
            return
        fen = self.game.fen()
        self.search_key = (self.generation, fen)
        self.search_role = "computer" if computer else "hint"
        self.search = self.worker.submit(self._search_move, fen, tuple(self.game.legal_moves()), tuple(self.game.move_history))
        self.hint_error = ""
        self.message = "Stockfish is thinking. Board input remains active."

    def poll_search(self):
        if not self.search or not self.search.done() or self.paused:
            return
        future, key, role = self.search, self.search_key, self.search_role
        self.search = None
        try:
            move = future.result()
        except Exception as exc:
            if self.engine:
                self.engine.close()
                self.engine = None
            if self.active and key == (self.generation, self.game.fen()):
                self.hint_error = str(exc)
                self.message = "Stockfish unavailable. Check engine installation, then retry Hint."
            return
        if not self.active or key != (self.generation, self.game.fen()) or move not in self.game.legal_moves():
            return
        if role == "computer":
            self.computer_move = move
            self.message = f"Computer move: {move}. Execute it on the physical board."
        else:
            names = {"p": "pawn", "n": "knight", "b": "bishop", "r": "rook", "q": "queen", "k": "king"}
            board = fen_board(self.game.fen())
            source = (int(move[1]) - 1) * 8 + ord(move[0]) - 97
            piece = names[board[source].lower()]
            self.hint = f"Stockfish recommends {piece} {move[:2]} - {move[2:4]}" + (f", promote to {names[move[4]]}." if len(move) == 5 else ".")
            self.message = "Hint ready. Choose your own move on the board."

    def state(self):
        return {"active": self.active, "paused": self.paused, "ready": self.ready and self.fresh(),
                "verified": self.verified, "synced": self.synchronized(), "restore": self.restore,
                "game_id": self.game_id, "mode": self.mode, "minutes": self.minutes,
                "fen": self.game.fen() if self.game else "", "white": self.white["name"] if self.white else "",
                "black": self.black["name"] if self.black else "", "white_ms": self.clock_values()[0],
                "black_ms": self.clock_values()[1], "last_move": self.last_move, "computer_move": self.computer_move,
                "hint": self.hint, "thinking": bool(self.search and not self.search.done()), "message": self.message,
                "result": self.result, "reason": self.reason, "promotions": self.promotions}

    def close(self):
        if self.active:
            self.tick_clock_only()
            self.store.checkpoint(self.game_id, self.clock_values(), "interrupted", "UI service stopped")
            self.active = False
        self.worker.shutdown(wait=True, cancel_futures=True)
        if self.engine:
            self.engine.close()
        if self.game:
            self.game.close()
