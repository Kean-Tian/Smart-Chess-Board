"""Shared SQLite players and actual games; never seeds demonstration records."""
from pathlib import Path
import os
import sqlite3

SCHEMA = Path(__file__).resolve().parents[1] / "storage" / "schema.sql"


def database_path(value=None):
    if value or os.environ.get("SCB_PLAYER_DB"):
        return Path(value or os.environ["SCB_PLAYER_DB"]).expanduser()
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "scb" / "players.sqlite3"


class GameStore:
    def __init__(self, path=None):
        self.path = database_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=0.25)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > 2:
            self.db.close()
            raise ValueError("This database needs a newer application version")
        try:
            self.db.executescript(SCHEMA.read_text())
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def board_settings(self):
        return dict(self.db.execute("SELECT port FROM board_settings WHERE id=1").fetchone())

    def save_board_port(self, port):
        # Keep the old schema column for compatibility, but never apply rotations.
        with self.db:
            self.db.execute("UPDATE board_settings SET port=?,orientation=0 WHERE id=1", (port,))

    def player(self, player_id):
        row = self.db.execute("SELECT id,name FROM players WHERE id=?", (player_id,)).fetchone()
        if row is None:
            raise ValueError("Choose a saved player")
        return dict(row)

    def start(self, white, black, mode, minutes, fen, clocks):
        with self.db:
            cur = self.db.execute("""INSERT INTO games
                (white_player_id,black_player_id,white_name,black_name,mode,minutes,
                 initial_fen,current_fen,status,white_ms,black_ms)
                VALUES(?,?,?,?,?,?,?,?, 'active',?,?)""",
                (white.get("id"), black.get("id"), white["name"], black["name"], mode,
                 minutes, fen, fen, *clocks))
        return cur.lastrowid

    def move(self, game_id, ply, uci, fen, clocks, result="*", reason=""):
        with self.db:
            row = self.db.execute("SELECT status FROM games WHERE id=?", (game_id,)).fetchone()
            if row is None or row[0] != "active":
                raise ValueError("Game is no longer active")
            self.db.execute("INSERT INTO game_moves(game_id,ply,uci,fen,white_ms,black_ms) VALUES(?,?,?,?,?,?)",
                            (game_id, ply, uci, fen, *clocks))
            self.db.execute("""UPDATE games SET current_fen=?,white_ms=?,black_ms=?,result=?,reason=?,
                status=?,ended_at=CASE WHEN ?<>'*' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id=?""",
                (fen, *clocks, result, reason, "completed" if result != "*" else "active", result, game_id))

    def checkpoint(self, game_id, clocks, status, reason="", result="*"):
        if status not in {"active", "paused", "completed", "interrupted"}:
            raise ValueError("Invalid game state")
        with self.db:
            self.db.execute("""UPDATE games SET white_ms=?,black_ms=?,status=?,reason=?,result=?,
                ended_at=CASE WHEN ? IN ('completed','interrupted') THEN CURRENT_TIMESTAMP ELSE NULL END
                WHERE id=?""", (*clocks, status, reason, result, status, game_id))

    def interrupt_previous(self):
        with self.db:
            self.db.execute("""UPDATE games SET status='interrupted',reason='Service stopped before this game ended',
                ended_at=CURRENT_TIMESTAMP WHERE status IN ('active','paused')""")

    def history(self, offset=0):
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("Invalid history page")
        total = self.db.execute("SELECT count(*) FROM games").fetchone()[0]
        offset = min(offset, ((total - 1) // 4) * 4) if total else 0
        rows = self.db.execute("""SELECT id,white_name AS white,black_name AS black,mode,result,status,
            created_at,reason FROM games ORDER BY id DESC LIMIT 4 OFFSET ?""", (offset,)).fetchall()
        return {"type": "history", "offset": offset, "total": total, "games": [dict(r) for r in rows]}

    def review(self, game_id, ply):
        if not isinstance(ply, int) or ply < 0:
            raise ValueError("Invalid review position")
        game = self.db.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
        if game is None:
            raise ValueError("Saved game not found")
        total = self.db.execute("SELECT count(*) FROM game_moves WHERE game_id=?", (game_id,)).fetchone()[0]
        ply = min(ply, total)
        row = self.db.execute("SELECT fen,uci FROM game_moves WHERE game_id=? AND ply=?", (game_id, ply)).fetchone() if ply else None
        if ply and row is None:
            raise ValueError("Saved move sequence is incomplete")
        return {"type": "review", "game_id": game_id, "ply": ply, "total": total,
                "fen": row["fen"] if row else game["initial_fen"], "move": row["uci"] if row else "",
                "white": game["white_name"], "black": game["black_name"], "result": game["result"],
                "status": game["status"], "reason": game["reason"]}
