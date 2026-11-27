"""Paths, immutable observations and reports. No production services are controlled."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[1]
RUNS = BASE / "runs"
SOCKET_BASE = Path("/tmp").resolve()


class Blocked(RuntimeError):
    pass


def bootstrap():
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "pi5/app"))
    sys.path.insert(0, str(ROOT / "pi5/rules/python"))


def stamp():
    return {"monotonic_ns": time.monotonic_ns(), "wall_ns": time.time_ns()}


def boot_id():
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def no_symlinks(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Blocked(f"Symlink path refused: {path}")
    return path


def run_path(value):
    path = no_symlinks(Path(value).expanduser())
    if path.parent != RUNS or path == RUNS:
        raise Blocked(f"Run must be a direct child of {RUNS}")
    return path


def create_run(value, purpose):
    path = run_path(value)
    no_symlinks(RUNS)
    RUNS.mkdir(exist_ok=True)
    path.mkdir(mode=0o700)  # Never reuse an existing directory/database.
    (path / "evidence").mkdir(mode=0o700)
    token = uuid.uuid4().hex
    manifest = {"version": 1, "token": token, "purpose": purpose,
                "database": str(path / "players.sqlite3"),
                "socket": str(SOCKET_BASE / f"scb-tidr-{os.getuid()}-{token[:12]}" / "ui.sock"),
                "created": stamp(), "root": str(ROOT)}
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def load_run(value):
    path = run_path(value)
    no_symlinks(path / "manifest.json")
    manifest = json.loads((path / "manifest.json").read_text())
    if uuid.UUID(manifest["token"]).hex != manifest["token"]:
        raise Blocked("Invalid run token")
    no_symlinks(path / "evidence")
    db = no_symlinks(path / "players.sqlite3")
    expected_socket = str(SOCKET_BASE / f"scb-tidr-{os.getuid()}-{manifest['token'][:12]}" / "ui.sock")
    if (manifest.get("version") != 1 or manifest.get("database") != str(db)
            or manifest.get("socket") != expected_socket
            or manifest.get("purpose") not in {"records", "failure"}):
        raise Blocked("Invalid isolated-run manifest")
    if db.exists() and db.stat().st_nlink != 1:
        raise Blocked("Hard-linked database refused")
    # Refuse aliases to any current/default production location.
    candidates = [Path.home() / ".local/share/scb/players.sqlite3"]
    if os.environ.get("XDG_DATA_HOME"):
        candidates.append(Path(os.environ["XDG_DATA_HOME"]) / "scb/players.sqlite3")
    if os.environ.get("SCB_PLAYER_DB"):
        candidates.append(Path(os.environ["SCB_PLAYER_DB"]).expanduser())
    for candidate in candidates:
        if candidate.resolve() == db.resolve() or (candidate.exists() and db.exists()
                                                   and os.path.samefile(candidate, db)):
            raise Blocked("Demo database aliases a production/configured database")
    return path, manifest


def connect_ro(path):
    no_symlinks(path)
    connection = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True, timeout=0.5)
    connection.row_factory = sqlite3.Row
    return connection


def stopped_observer_check(report, trace, label="service"):
    starts = {e["session"] for e in trace if e["kind"] == "observer_start"}
    stops = {e["session"] for e in trace if e["kind"] == "observer_stop" and e.get("errors") == 0}
    report.check(f"{label} sessions closed with complete evidence", bool(starts) and starts <= stops,
                 f"started={len(starts)}, cleanly stopped={len(stops)}; evaluate after normal cleanup", missing=True)
    report.check(f"{label} contains no synthetic fixture observations",
                 not any(e.get("synthetic") for e in trace),
                 "software selftest traces are never physical checkoff evidence", missing=True)


def database_snapshot(path):
    with connect_ro(path) as db:
        db.execute("BEGIN")
        games = [dict(r) for r in db.execute("SELECT * FROM games ORDER BY id")]
        moves = [dict(r) for r in db.execute("SELECT * FROM game_moves ORDER BY game_id,ply")]
        integrity = db.execute("PRAGMA quick_check").fetchone()[0]
    return {"games": games, "moves": moves, "integrity": integrity}


def game_record(snapshot, game_id):
    game = next((g for g in snapshot["games"] if g["id"] == game_id), None)
    return {"game": game, "moves": [m for m in snapshot["moves"] if m["game_id"] == game_id]}


def append(path, record):
    no_symlinks(path)
    line = json.dumps({**stamp(), **record}, separators=(",", ":")) + "\n"
    with Path(path).open("a") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path):
    if not Path(path).exists():
        return []
    no_symlinks(path)
    lines = Path(path).read_text().splitlines(keepends=True)
    result = []
    for index, line in enumerate(lines):
        if not line.endswith("\n") and index == len(lines) - 1:
            break  # A concurrently appended final line is not a complete observation.
        result.append(json.loads(line))
    return result


def events(run):
    return read_jsonl(run / "events.jsonl")


def attachments(run, kind, label=None):
    found = []
    for item in read_jsonl(run / "attachments.jsonl"):
        if item["kind"] != kind or (label is not None and item["label"] != label):
            continue
        path = no_symlinks(run / item["path"])
        if not path.is_relative_to(run / "evidence") or digest(path) != item["sha256"]:
            raise Blocked("Evidence file missing, changed or outside the evidence directory")
        found.append(item)
    return found


class Report:
    def __init__(self, tidr):
        self.tidr, self.checks = tidr, []

    def check(self, name, condition, detail="", missing=False):
        self.checks.append({"name": name, "status": "PASS" if condition else
                            "BLOCKED" if missing else "FAIL", "detail": detail})

    def finish(self, run):
        status = ("FAIL" if any(c["status"] == "FAIL" for c in self.checks) else
                  "BLOCKED" if not self.checks or any(c["status"] == "BLOCKED" for c in self.checks)
                  else "PASS")
        result = {"tidr": self.tidr, "status": status, "checks": self.checks, **stamp()}
        print(f"TIDR #{self.tidr}: {status}")
        for check in self.checks:
            print(f"  {check['status']}: {check['name']} — {check['detail']}")
        # Versioned results preserve previous evaluations rather than overwriting them.
        target = run / f"result-{self.tidr}-{time.time_ns()}.json"
        target.write_text(json.dumps(result, indent=2) + "\n")
        print(f"Evidence report: {target}")
        return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[status]


def cli(main):
    try:
        return main()
    except KeyboardInterrupt:
        print("BLOCKED: interrupted; no successful hardware result")
        return 130
    except (Blocked, OSError, ValueError, KeyError, sqlite3.Error) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


def run_argument(parser):
    parser.add_argument("--run", required=True, help="Absolute isolated run directory")
