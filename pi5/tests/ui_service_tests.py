"""Local IPC + PTY tests. No physical GPIO/board, network API or motor is used."""
import json
import os
from pathlib import Path
import pty
import queue
import re
import select
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import tty
import unittest

PI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PI / "app"))
from game_store import GameStore
from ui_service import UiCore
from scb_link import Frame
from ui_game import START_OCCUPANCY


class EmulatedMcu:
    def __init__(self):
        self.master, self.slave = pty.openpty()
        tty.setraw(self.slave)
        self.port = os.ttyname(self.slave)
        self.mask = 0xFFFF00000000FFFF
        self.commands = []
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def send(self, text):
        with self.lock:
            os.write(self.master, text.encode())

    def run(self):
        fragment = b""
        while not self.done.is_set():
            if not select.select([self.master], [], [], 0.02)[0]:
                continue
            try:
                fragment += os.read(self.master, 4096)
            except OSError:
                continue
            while b"\n" in fragment:
                line, _, fragment = fragment.partition(b"\n")
                match = re.fullmatch(rb"@(\d+) ([ -~]+)\r?", line.strip())
                if not match:
                    continue
                ident, command = match[1].decode(), match[2].decode()
                self.commands.append(command)
                if command == "SCAN":
                    self.send(f"BOARD {self.mask:016X}\nACK {ident} SCAN\n")
                elif command == "TIMING":
                    self.send(f"TIMING {ident} frames=500 frame_us=10000 max_us=11000 misses=0 debounce_us=10000\n")
                elif command == "STATUS":
                    self.send(f"STATUS {ident} armed=0 moving=0 magnet=0 origin=0 steps=0 polarity=HIGH fault=NONE\n")
                elif command == "SNAPSHOT":
                    self.send(f"SNAPSHOT {ident} occupy={self.mask:016X} frame=100 fault=NONE\n")
                else:
                    self.send(f"ACK {ident} {command}\n")

    def move_e2e4(self):
        self.mask = (self.mask & ~(1 << 12)) | (1 << 28)
        self.send(f"BOARD {self.mask:016X}\nEVENT MOVE e2e4\n")

    def close(self):
        self.done.set()
        self.thread.join(timeout=1)
        os.close(self.master)
        os.close(self.slave)


class ServiceTests(unittest.TestCase):
    def test_coaching_choices_are_independent_and_off_turn_cannot_request_advice(self):
        with tempfile.TemporaryDirectory() as temp:
            store = GameStore(Path(temp) / "players.sqlite3")
            store.db.execute("INSERT INTO players(name) VALUES('White player')")
            store.db.execute("INSERT INTO players(name) VALUES('Black player')")
            store.db.commit()
            core = UiCore(store)
            try:
                settings = {"cmd": "prepare", "mode": "coach", "white_id": 1, "black_id": 2, "minutes": 0}
                with self.assertRaises(ValueError): core.handle(settings)
                core.handle(dict(settings, coach_white=False, coach_black=False))
                core.session.connection(True)
                core.session.on_board(START_OCCUPANCY)
                core.session.check()
                core.handle({"cmd": "start", "verified": True})
                with self.assertRaises(ValueError): core.handle({"cmd": "hint"})
                core.handle({"cmd": "coaching", "side": "b", "enabled": True})
                self.assertFalse(core.state()["coach_white"])
                self.assertTrue(core.state()["coach_black"])
                self.assertIsNone(core.session.search)
                with self.assertRaises(ValueError): core.handle({"cmd": "guidance", "enabled": True})
                core.session.end()
                core.handle(dict(settings, mode="pvc", human="w"))
                core.session.on_board(START_OCCUPANCY)
                core.session.check()
                core.handle({"cmd": "start", "verified": True})
                with self.assertRaises(ValueError): core.handle({"cmd": "hint"})
                self.assertIsNone(core.session.search)
            finally:
                core.close()
                store.close()

    def test_diagnostics_empty_stale_timing_and_malformed_data(self):
        with tempfile.TemporaryDirectory() as temp:
            store = GameStore(Path(temp) / "players.sqlite3")
            class Link:
                _failure = None
                def __init__(self): self.events, self.commands = queue.Queue(), []
                def request(self, cmd, **kwargs):
                    self.commands.append(cmd)
                    if cmd == "TIMING": return Frame("TIMING", 1, "frames=12 frame_us=10000 max_us=11000 misses=0 debounce_us=10000")
                    if cmd == "STATUS": return Frame("STATUS", 1, "armed=0 moving=0 magnet=0")
                    if cmd == "SCAN": self.events.put(Frame("BOARD", None, "0000000000000000"))
                    return Frame("ACK", 1, cmd)
                def close(self): pass
            core = UiCore(store)
            core.link = Link()
            core.session.connection(True)
            core.last_poll = core.last_ports = core.now()
            try:
                core.handle({"cmd": "scan"})
                for _ in range(100):
                    core.update()
                    if not core.job: break
                    time.sleep(0.005)
                state = core.state()
                self.assertTrue(state["board_known"])
                self.assertEqual(state["board"], "0000000000000000")
                self.assertEqual(state["scan_timing"]["frame_us"], 10000)
                self.assertIsNotNone(state["scan_round_trip_ms"])
                self.assertEqual([c for c in core.link.commands if c != "LED_CLEAR"], ["SCAN", "STATUS", "TIMING"])
                self.assertEqual(store.history()["total"], 0)
                core.link.events.put(Frame("BOARD", None, "not-a-board"))
                core.update()
                self.assertFalse(core.state()["board_known"])
                self.assertIsNone(core.state()["board"])
                self.assertIn("Invalid", core.state()["error"])
            finally:
                core.close()
                store.close()

    def test_saved_rotation_is_ignored_and_raw_coordinates_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            store = GameStore(Path(temp) / "players.sqlite3")
            store.db.execute("UPDATE board_settings SET orientation=3")
            store.db.commit()
            class Link:
                _failure = None
                def __init__(self): self.events = queue.Queue()
                def close(self): pass
            core = UiCore(store)
            core.link = Link()
            core.last_poll = core.last_ports = core.now()
            core.session.connection(True)
            core.link.events.put(Frame("BOARD", None, "0000000000000001"))
            try:
                core.update()
                self.assertEqual(core.session.mask, 1)
                self.assertEqual(core.state()["board"], "0000000000000001")
                self.assertNotIn("orientation", core.state())
                with self.assertRaises(ValueError):
                    core.handle({"cmd": "orientation", "value": 2})
                store.save_board_port("/dev/test-port")
                self.assertEqual(store.db.execute("SELECT orientation FROM board_settings").fetchone()[0], 0)
            finally:
                core.close()
                store.close()

    def test_version_one_players_migrate_without_reset(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "players.sqlite3"
            db = sqlite3.connect(path)
            db.executescript("""CREATE TABLE players(id INTEGER PRIMARY KEY,name TEXT UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE ui_state(id INTEGER PRIMARY KEY,selected_player_id INTEGER REFERENCES players(id) ON DELETE SET NULL);
                INSERT INTO players(id,name) VALUES(37,'Existing player');
                INSERT INTO ui_state VALUES(1,37); PRAGMA user_version=1;""")
            db.close()
            store = GameStore(path)
            self.assertEqual(store.player(37)["name"], "Existing player")
            self.assertEqual(store.db.execute("SELECT selected_player_id FROM ui_state").fetchone()[0], 37)
            self.assertEqual(store.db.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(store.history()["total"], 0)
            store.close()

    def test_repeated_ui_commands_do_not_start_or_score_a_game_twice(self):
        with tempfile.TemporaryDirectory() as temp:
            store = GameStore(Path(temp) / "players.sqlite3")
            store.db.execute("INSERT INTO players(name) VALUES('Player one')")
            store.db.execute("INSERT INTO players(name) VALUES('Player two')")
            store.db.commit()
            core = UiCore(store)
            try:
                core.handle({"cmd": "prepare", "mode": "pvp", "white_id": 1, "black_id": 2, "human": "w", "minutes": 0})
                core.session.connection(True)
                core.session.on_board(START_OCCUPANCY)
                self.assertTrue(core.session.check())
                core.handle({"cmd": "start", "verified": True})
                core.handle({"cmd": "start", "verified": True})
                self.assertEqual(store.history()["total"], 1)
                core.handle({"cmd": "pause"})
                core.handle({"cmd": "pause"})
                class Link:
                    _failure = None
                    events = queue.Queue()
                    def request(self, cmd, **kwargs):
                        if cmd == "STATUS": return Frame("STATUS", 1, "armed=0 moving=0 magnet=0 fault=NONE")
                        if cmd == "SNAPSHOT": return Frame("SNAPSHOT", 1, f"occupy={START_OCCUPANCY:016X} frame=1 fault=NONE")
                        return Frame("ACK", 1, cmd)
                    def close(self): pass
                core.link = Link()
                core.last_ports = core.last_poll = core.now()
                core.handle({"cmd": "resume"})
                core.handle({"cmd": "resume"})
                for _ in range(100):
                    core.update()
                    if not core.job: break
                    time.sleep(.005)
                self.assertFalse(core.session.paused)
                core.handle({"cmd": "end", "result": "1/2-1/2"})
                core.handle({"cmd": "end", "result": "1-0"})
                self.assertEqual(store.review(core.session.game_id, 0)["result"], "1/2-1/2")
            finally:
                core.close()
                store.close()

    def test_native_ui_to_service_to_serial_and_saved_replay(self):
        binary = os.environ.get("SCB_TOUCH_UI_BINARY")
        if not binary:
            self.skipTest("Set SCB_TOUCH_UI_BINARY to the compiled native LVGL test host")
        try:
            import serial
        except ImportError:
            self.fail("Install pyserial to run the complete serial integration test")
        with tempfile.TemporaryDirectory(prefix="scb-ipc-") as temp:
            root = Path(temp)
            db = root / "players.sqlite3"
            sock = root / "ui.sock"
            mcu = EmulatedMcu()
            env = dict(os.environ, SCB_UI_SOCKET=str(sock), SCB_PLAYER_DB=str(db), SCB_SERIAL_PORT=mcu.port)
            env.pop("SCB_UI_TEST_MODE", None)
            service = None
            ui = None
            with (root / "service.log").open("w+") as log:
                try:
                    service = subprocess.Popen([sys.executable, "-B", str(PI / "app/ui_service.py"),
                                                "--socket", str(sock), "--database", str(db)],
                                               env=env, stdout=log, stderr=log)
                    deadline = time.monotonic() + 8
                    while not sock.exists() and time.monotonic() < deadline and service.poll() is None:
                        time.sleep(0.02)
                    self.assertIsNone(service.poll(), "Service exited during startup")
                    self.assertTrue(sock.exists())
                    ui = subprocess.Popen([binary, "--database", str(db), "--service-test"], env=env,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    injected = False
                    deadline = time.monotonic() + 35
                    while ui.poll() is None and time.monotonic() < deadline:
                        if not injected:
                            try:
                                connection = sqlite3.connect(db, timeout=0.1)
                                active = connection.execute("SELECT count(*) FROM games WHERE status='active'").fetchone()[0]
                                connection.close()
                            except sqlite3.Error:
                                active = 0
                            if active:
                                mcu.move_e2e4()
                                injected = True
                        time.sleep(0.02)
                    if ui.poll() is None:
                        ui.kill()
                    stdout, stderr = ui.communicate(timeout=3)
                    log.flush()
                    log.seek(0)
                    detail = stdout + stderr + log.read()
                    self.assertEqual(ui.returncode, 0, detail)
                    self.assertTrue(injected, detail)
                    self.assertIn("PASS: native UI", stdout)
                    connection = sqlite3.connect(db)
                    self.assertEqual(connection.execute("SELECT uci FROM game_moves").fetchall(), [("e2e4",)])
                    self.assertEqual(connection.execute("SELECT status FROM games").fetchone()[0], "completed")
                    self.assertEqual(connection.execute("SELECT count(*) FROM players").fetchone()[0], 2)
                    connection.close()
                    self.assertFalse(any(cmd.split()[0] in {"ARM", "MOVE", "GOTO", "JOG", "MAGNET"} for cmd in mcu.commands))
                    self.assertIn("LED_CLEAR", mcu.commands)
                    self.assertIn("TIMING", mcu.commands)
                finally:
                    if ui and ui.poll() is None:
                        ui.kill()
                        ui.wait()
                    if service and service.poll() is None:
                        service.terminate()
                        service.wait(timeout=12)
                    mcu.close()


if __name__ == "__main__": unittest.main()
