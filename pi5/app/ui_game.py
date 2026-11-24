"""Authoritative physical-game state for the native UI, independent of widgets."""
from concurrent.futures import ThreadPoolExecutor
import time

from board_game import Game, expected_occupancy, occupancy, fen_board
from stockfish_engine import Stockfish
from ui_coach import request_ui_coaching

START_OCCUPANCY = 0xFFFF00000000FFFF


class GameSession:
    # 保存真实游戏状态；界面切页不会销毁这份状态。
    def __init__(self, store, *, now=time.monotonic, game_factory=Game, engine_factory=Stockfish,
                 coach_request=request_ui_coaching):
        self.store, self.now = store, now
        self.game_factory, self.engine_factory = game_factory, engine_factory
        self.game = None
        self.engine = None
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scb-engine")
        self.coach_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scb-ai-coach")
        self.coach_request = coach_request
        self.coaching = {"w": False, "b": False}
        self.search_started = None
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
        self.guidance = False
        self.legal_source = ""
        self.legal_destinations = []
        self.ambiguous = False
        self.motion_active = False
        self.motion_move = ""
        self.feedback_command = "LED_CLEAR"

    def fresh(self):
        # 只有连接正常且两秒内收到棋盘数据，才把占用当作可用实况。
        return self.connected and self.board_at is not None and self.now() - self.board_at < 2.0

    def synchronized(self):
        # 比较传感器占用与逻辑局面；Hall 传感器不能区分棋子种类。
        return self.fresh() and self.game is not None and self.mask == occupancy(fen_board(self.game.fen()))

    def tick(self):
        # 按实际经过时间扣当前一方的时钟，并检查失联与搜索结果。
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

    def prepare(self, mode, white_id, black_id, human, minutes, guidance=None,
                coach_white=None, coach_black=None):
        # 检查设置和玩家，准备开局；这里只准备，不创建对局记录。
        if self.active:
            raise ValueError("End the current game before preparing another")
        if mode not in {"pvp", "pvc", "coach"} or human not in {"w", "b"} or minutes not in {0, 5, 10}:
            raise ValueError("Invalid game settings")
        if guidance is not None and not isinstance(guidance, bool):
            raise ValueError("Guidance must be on or off")
        if mode == "coach" and (not isinstance(coach_white, bool) or not isinstance(coach_black, bool)):
            raise ValueError("White and Black must each choose AI coaching ON or OFF")
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
        if self.search:
            self.search.cancel()
            self.search = None
        self.generation += 1
        self.active = self.paused = False
        self.search_key = None
        self.mode, self.human, self.minutes = mode, human, minutes
        self.guidance = mode == "pvp" and bool(guidance)
        self.motion_active, self.motion_move = False, ""
        self.feedback_command = "LED_CLEAR"
        self.coaching = {"w": coach_white is True, "b": coach_black is True} if mode == "coach" else {"w": False, "b": False}
        self.legal_source, self.legal_destinations, self.ambiguous = "", [], False
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
        # 开局检查要求新鲜整盘数据与标准初始占用一致。
        if self.game is None or self.active:
            raise ValueError("Prepare a new game first")
        self.verified = False
        self.ready = self.fresh() and self.mask == START_OCCUPANCY
        self.message = ("Occupancy matches. Confirm the piece types and colors before starting."
                        if self.ready else "Starting occupancy does not match, or board data is unavailable.")
        return self.ready

    def start(self, verified):
        # 后台重新核对条件，保存对局记录后才启动时钟。
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
        # 收到整盘占用后更新时间，并尝试确认等待中的完整走法。
        if not isinstance(mask, int) or isinstance(mask, bool) or not 0 <= mask < (1 << 64):
            self.board_at = None
            self.ready = self.verified = False
            if self.active:
                self.pause("Invalid board data. Reconnect and check the current position.")
            raise ValueError("Invalid 64-square occupancy")
        self.mask = mask
        self.board_at = self.now()
        self.board_generation += 1
        if self.motion_active:
            return  # 运动中的传感器变化只作实况，不作为玩家走法提交。
        if not self.active:
            if self.ready and mask != START_OCCUPANCY:
                self.ready = self.verified = False
            return
        if self.synchronized():
            if self.restore or self.legal_source:
                self.feedback_command = "LED_CLEAR"
            self.restore = False
            self.ambiguous = False
            self.legal_source, self.legal_destinations = "", []
            self.pending = None
            self.promotions = []
            if not self.paused:
                self.message = "Board synchronized."
        elif self.pending and not self.paused:
            self.commit(self.pending)

    def event(self, payload):
        if not self.active or self.paused or self.motion_active or self.committed_generation == self.board_generation:
            return
        if self.restore or self.ambiguous:
            return  # 阻止后续抬起事件覆盖尚未解决的错误提示。
        if payload.startswith("MOVE "):
            self.commit(payload.split()[1])
        elif payload.startswith("AMBIGUOUS"):
            self.ambiguous = True
            self.pending = None
            self.legal_source, self.legal_destinations = "", []
            self.message = "Ambiguous board change. Finish the move, or use Confirm move."
        elif payload.startswith("LIFT"):
            parts = payload.split()
            source = parts[1] if len(parts) == 2 else ""
            if self.guidance and not self.restore and len(source) == 2:
                self.legal_source = source
                self.legal_destinations = sorted({m[2:4] for m in self.game.legal_moves() if m[:2] == source})
                mask = sum(1 << ((int(sq[1])-1)*8 + ord(sq[0])-97) for sq in self.legal_destinations)
                self.feedback_command = f"GUIDE {mask:016X}"
            self.message = "Piece lifted. Complete the move on the board."

    def set_guidance(self, enabled):
        # 开关只控制建议，不影响棋规检查或电脑对手。
        if self.mode != "pvp":
            raise ValueError("Local guidance is only available in Two players mode")
        if not isinstance(enabled, bool):
            raise ValueError("Guidance must be on or off")
        self.guidance = enabled
        self.hint = self.hint_error = ""
        self.legal_source, self.legal_destinations = "", []
        if not enabled and self.search_role == "hint":
            self.search_key = None  # 关闭后，不再采用已经排队的提示结果。
        if not enabled and self.feedback_command.startswith("GUIDE "):
            self.feedback_command = "LED_CLEAR"
        self.maybe_search()

    def set_coaching(self, side, enabled):
        # 两个玩家独立决定；关闭一方不会改变另一方的选择。
        if self.mode != "coach" or side not in {"w", "b"} or not isinstance(enabled, bool):
            raise ValueError("Choose White or Black AI coaching ON or OFF")
        self.coaching[side] = enabled
        if self.game and self.game.fen().split()[1] == side:
            self.hint = self.hint_error = ""
            if self.search_role == "coach":
                self.search_key = None
            self.maybe_search()

    def computer_action(self):
        """Describe manual steps and whether the optional motion interface may run."""
        if not self.computer_move or not self.game:
            return None
        move, board = self.computer_move, fen_board(self.game.fen())
        source = (int(move[1])-1)*8 + ord(move[0])-97
        target = (int(move[3])-1)*8 + ord(move[2])-97
        piece = board[source]
        steps = []
        removal = target if target in board else None
        if piece.lower() == "p" and source % 8 != target % 8 and removal is None:
            removal = target-8 if piece == "P" else target+8
        def name(square):
            return f"{chr(97 + square % 8)}{square // 8 + 1}"
        if removal is not None:
            steps.append(f"Remove the opponent's piece from {name(removal)}.")
        steps.append(f"Move your piece from {move[:2]} to {move[2:4]}.")
        coordinated = piece.lower() == "k" and abs(source-target) == 2
        if coordinated:
            rook_source = source // 8 * 8 + (7 if target > source else 0)
            rook_target = source + (1 if target > source else -1)
            steps.append(f"Move the rook from {name(rook_source)} to {name(rook_target)}.")
        replacement = {"q": "queen", "r": "rook", "b": "bishop", "n": "knight"}.get(move[4:])
        if replacement:
            steps.append(f"Replace the pawn on {move[2:4]} with a {replacement} of the same color.")
            steps.append("Confirm the replacement below after placing it.")
        else:
            steps.append("The game continues only after the sensed board matches.")
        return {"move": move, "source": move[:2], "destination": move[2:4], "steps": steps,
                "replacement": replacement, "execution": "manual",
                "placement_matches": self.fresh() and self.mask == expected_occupancy(self.game.fen(), move),
                "automatic_eligible": removal is None and not coordinated and not replacement}

    def begin_motion(self, move):
        # 只有已经校验的电脑普通走法，才可进入运动等待状态。
        action = self.computer_action()
        if (not self.active or self.paused or self.motion_active or not self.synchronized() or
                self.mode != "pvc" or self.game.fen().split()[1] == self.human or
                not action or move != action["move"] or not action["automatic_eligible"] or
                move not in self.game.legal_moves()):
            raise ValueError("Automatic motion requires a validated simple computer move and a synchronized board")
        self.motion_active, self.motion_move = True, move
        self.feedback_command = "LED_CLEAR"
        self.message = "Automatic motion in progress. Human moves are blocked."

    def finish_motion(self, move, mask):
        # 调用方必须先收到 DONE，再取得请求之后新扫描的 SNAPSHOT。
        if not self.motion_active or self.motion_move != move or self.paused or move != self.computer_move:
            raise ValueError("The motion result is no longer valid")
        self.on_board(mask)
        self.motion_active, self.motion_move = False, ""
        if self.mask != expected_occupancy(self.game.fen(), move):
            self.pause("Motion completed but occupancy does not match. Restore the accepted position before resuming.")
            raise ValueError("Post-motion board mismatch")
        return self.commit(move)

    def cancel_motion(self):
        self.motion_active, self.motion_move = False, ""

    def commit(self, move, *, explicit=False):
        # 先查棋规与占用；数据库保存成功后才替换正式局面。
        self.tick_clock_only()
        accepted_at = self.last_tick
        if not self.active or self.paused or self.motion_active or not self.fresh() or self.restore:
            raise ValueError("Resume and synchronize the board before confirming a move")
        if self.ambiguous and not explicit:
            self.message = "Confirm the intended move before continuing."
            return False
        legal = self.game.legal_moves()
        choices = [m for m in legal if m == move or (len(move) == 4 and m[:4] == move)]
        if not choices:
            self.pending = None
            self.restore = True
            if len(move) >= 4:
                self.feedback_command = f"MARK {move[:2]} {move[2:4]} ILLEGAL"
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
        if len(move) == 5 and not explicit:
            self.pending = None
            self.promotions = choices
            self.message = "Place the indicated replacement piece and confirm it on screen."
            return False
        if expected_occupancy(self.game.fen(), move) != self.mask:
            # 模糊走法与替换棋子必须在摆好后重新人工确认，不能后台自动通过。
            self.pending = None if explicit or self.ambiguous else move
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
        self.ambiguous = False
        self.legal_source, self.legal_destinations = "", []
        self.promotions = []
        self.computer_move = self.hint = self.hint_error = ""
        self.committed_generation = self.board_generation
        self.result, self.reason = result, status
        self.message = status or "Move accepted."
        self.feedback_command = f"MARK {move[:2]} {move[2:4]} LEGAL"
        if result != "*":
            self.active = self.ready = self.verified = False
            self.feedback_command = "LED_CLEAR"
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
        # 停止游戏计时并保存状态；传感器通信仍继续。
        if not self.active:
            raise ValueError("There is no active game")
        if not self.paused:
            self.paused = True
            self.store.checkpoint(self.game_id, self.clock_values(), "paused", reason)
        if self.feedback_command.startswith("GUIDE "):
            self.feedback_command = "LED_CLEAR"
        self.message = reason

    def resume(self):
        # 实体棋盘恢复到当前逻辑局面后才能继续。
        if not self.active or not self.paused or self.motion_active or not self.synchronized():
            raise ValueError("Restore the current position and reconnect before resuming")
        if self.minutes and any(value <= 0 for value in self.clocks):
            raise ValueError("A clock has expired. End the game and record its result")
        self.store.checkpoint(self.game_id, self.clock_values(), "active")
        self.paused = False
        self.pending = None
        self.restore = self.ambiguous = False
        self.last_tick = self.now()
        self.message = "Game resumed."
        self.maybe_search()

    def end(self, result="*"):
        # 保存结束状态；* 表示未指定结果，不是和棋。
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
        self.feedback_command = "LED_CLEAR"

    def _search_move(self, fen, legal, history):
        if self.engine is None:
            self.engine = self.engine_factory()
        return self.engine.best_move(fen, legal, 2000, history)

    def maybe_search(self, force_hint=False):
        # 将电脑走法或提示计算交给工作线程，避免阻塞通信。
        if not self.active or self.paused or self.motion_active or not self.synchronized() or self.search:
            return
        if self.hint_error and not force_hint:
            return
        computer = self.mode == "pvc" and self.game.fen().split()[1] != self.human
        coach = self.mode == "coach" and self.coaching[self.game.fen().split()[1]]
        if self.mode == "pvc" and not computer:
            return
        if not computer and not coach and not (self.mode == "pvp" and force_hint):
            return
        if computer and self.computer_move:
            return
        if not computer and self.hint and not force_hint:
            return
        fen = self.game.fen()
        self.search_key = (self.generation, fen)
        self.search_role = "computer" if computer else "coach" if coach else "hint"
        self.search_started = self.now()
        if coach:
            self.search = self.coach_worker.submit(self.coach_request, fen, tuple(self.game.legal_moves()))
        else:
            self.search = self.worker.submit(self._search_move, fen, tuple(self.game.legal_moves()), tuple(self.game.move_history))
        self.hint_error = ""
        self.message = "AI coach is thinking. You can keep playing." if coach else "Stockfish is thinking. Board input remains active."

    def poll_search(self):
        # 只采用仍对应当前对局和局面的结果，丢弃过期搜索。
        if self.search and self.search_role == "coach" and not self.search.done() and self.now() - self.search_started >= 10:
            self.search.cancel()
            self.search = None
            if self.search_key == (self.generation, self.game.fen()) and self.coaching[self.game.fen().split()[1]]:
                self.hint_error = "AI coaching timed out. Check the connection and retry."
                self.message = "AI coaching unavailable. Both players can continue."
        if not self.search or not self.search.done() or self.paused:
            return
        future, key, role = self.search, self.search_key, self.search_role
        self.search = None
        try:
            answer = future.result()
            move = answer.move if role == "coach" else answer
        except Exception as exc:
            if role != "coach" and self.engine:
                self.engine.close()
                self.engine = None
            if self.active and key == (self.generation, self.game.fen()):
                self.hint_error = str(exc)
                self.message = "AI coaching unavailable. Both players can continue; open AI coaching to retry." if role == "coach" else "Stockfish unavailable. Check engine installation, then retry Hint."
            return
        if not self.active or key != (self.generation, self.game.fen()):
            return
        if role == "coach" and not self.coaching[self.game.fen().split()[1]]:
            return
        if move not in self.game.legal_moves():
            self.hint_error = "AI coach returned an invalid move" if role == "coach" else "Engine returned an invalid move"
            self.message = "Advice rejected. Open AI coaching or Hint to retry."
            return
        if role == "computer":
            self.computer_move = move
            self.message = f"Computer move: {move}. Execute it on the physical board."
        elif role == "coach":
            side = "White" if self.game.fen().split()[1] == "w" else "Black"
            self.hint = f"AI coaching [{side}] / {move[:2]} - {move[2:]}\n{answer.hint}"
            self.message = "AI coaching ready. The suggestion is optional; play your own move."
        else:
            if not self.guidance:
                return
            names = {"p": "pawn", "n": "knight", "b": "bishop", "r": "rook", "q": "queen", "k": "king"}
            board = fen_board(self.game.fen())
            source = (int(move[1]) - 1) * 8 + ord(move[0]) - 97
            piece = names[board[source].lower()]
            self.hint = f"Stockfish recommends {piece} {move[:2]} - {move[2:4]}" + (f", promote to {names[move[4]]}." if len(move) == 5 else ".")
            self.message = "Hint ready. Choose your own move on the board."

    def state(self):
        # 整理 UI 需要的状态；这里返回数据，不直接修改界面控件。
        return {"active": self.active, "paused": self.paused, "ready": self.ready and self.fresh(),
                "verified": self.verified, "synced": self.synchronized(), "restore": self.restore,
                "game_id": self.game_id, "mode": self.mode, "minutes": self.minutes,
                "fen": self.game.fen() if self.game else "", "white": self.white["name"] if self.white else "",
                "black": self.black["name"] if self.black else "", "white_ms": self.clock_values()[0],
                "black_ms": self.clock_values()[1], "last_move": self.last_move, "computer_move": self.computer_move,
                "hint": self.hint, "thinking": bool(self.search and not self.search.done()), "message": self.message,
                "result": self.result, "reason": self.reason, "promotions": self.promotions,
                "guidance": self.guidance, "legal_source": self.legal_source,
                "motion_active": self.motion_active, "motion_move": self.motion_move,
                "coach_white": self.coaching["w"], "coach_black": self.coaching["b"],
                "coaching_enabled": self.mode == "coach" and self.game is not None and self.coaching[self.game.fen().split()[1]],
                "legal_destinations": self.legal_destinations, "ambiguous": self.ambiguous,
                "computer_action": self.computer_action(), "game_status": self.game.status() if self.game else "",
                "moves": self.game.move_history[-8:] if self.game else []}

    def close(self):
        if self.active:
            self.tick_clock_only()
            self.store.checkpoint(self.game_id, self.clock_values(), "interrupted", "UI service stopped")
            self.active = False
        self.worker.shutdown(wait=True, cancel_futures=True)
        self.coach_worker.shutdown(wait=True, cancel_futures=True)
        if self.engine:
            self.engine.close()
        if self.game:
            self.game.close()
