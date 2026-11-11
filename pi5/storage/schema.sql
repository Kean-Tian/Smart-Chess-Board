PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS players (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK(length(name) BETWEEN 1 AND 24 AND name=trim(name)),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ui_state (
 id INTEGER PRIMARY KEY CHECK(id=1),
 selected_player_id INTEGER REFERENCES players(id) ON DELETE SET NULL
);
INSERT OR IGNORE INTO ui_state(id,selected_player_id) VALUES(1,NULL);
CREATE TABLE IF NOT EXISTS games (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 white_player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
 black_player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
 white_name TEXT NOT NULL, black_name TEXT NOT NULL,
 mode TEXT NOT NULL CHECK(mode IN ('pvp','pvc','coach')),
 minutes INTEGER NOT NULL CHECK(minutes IN (0,5,10)),
 initial_fen TEXT NOT NULL, current_fen TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('active','paused','completed','interrupted')),
 result TEXT NOT NULL DEFAULT '*' CHECK(result IN ('*','1-0','0-1','1/2-1/2')),
 reason TEXT NOT NULL DEFAULT '',
 white_ms INTEGER, black_ms INTEGER,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 ended_at TEXT
);
CREATE TABLE IF NOT EXISTS game_moves (
 game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
 ply INTEGER NOT NULL CHECK(ply>0),
 uci TEXT NOT NULL, fen TEXT NOT NULL,
 white_ms INTEGER, black_ms INTEGER,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(game_id,ply)
);
-- The orientation column is retained only for compatibility and is not used.
CREATE TABLE IF NOT EXISTS board_settings (
 id INTEGER PRIMARY KEY CHECK(id=1),
 port TEXT NOT NULL DEFAULT '', orientation INTEGER NOT NULL DEFAULT 0 CHECK(orientation BETWEEN 0 AND 7)
);
INSERT OR IGNORE INTO board_settings(id) VALUES(1);
PRAGMA user_version=2;
COMMIT;
