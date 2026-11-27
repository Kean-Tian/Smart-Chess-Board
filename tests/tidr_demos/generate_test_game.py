"""Append an explicitly labeled legal game fixture using original rules/storage APIs.

No hardware, UI, service, serial port or network is opened. This is not a physical
TIDR result. Profile creation uses the public production C player_store API because
the Python GameStore provides player lookup but no player-create API.
"""
import argparse
import fcntl
import json
import shlex
import shutil
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
from common.runtime import (BASE, ROOT, Blocked, append, bootstrap, cli, create_run,
                            database_snapshot, game_record, load_run, no_symlinks,
                            run_argument)

MOVES = ("f2f3", "e7e5", "g2g4", "d8h4")
LABEL = "GENERATED TEST FIXTURE - no physical gameplay"


def build_player_helper(run):
    compiler = shutil.which("cc")
    if not compiler:
        raise Blocked("GameStore has no player-create API. Native player_store adapter needs cc; "
                      "or create test players in the existing UI and provide --white-id/--black-id.")
    build = no_symlinks(run / "fixture-build")
    build.mkdir(exist_ok=True, mode=0o700)
    build = build / uuid.uuid4().hex
    build.mkdir(mode=0o700)
    # Same immutable schema input used by the existing native UI's CMake build.
    # This is an include artifact for unchanged production player_store.c, not a schema change.
    schema = (ROOT / "pi5/storage/schema.sql").read_text()
    (build / "storage_schema.h").write_text("static const char scb_schema_sql[] = " +
                                           json.dumps(schema) + ";\n")
    binary = build / "fixture_players"
    command = [compiler, "-std=c17", "-D_POSIX_C_SOURCE=200809L", "-O2", "-Wall", "-Wextra", "-Werror",
               "-I", str(ROOT / "pi5/ui/src"), "-I", str(build),
               str(BASE / "common/fixture_players.c"), str(ROOT / "pi5/ui/src/player_store.c"),
               "-lsqlite3", "-o", str(binary)]
    if sys.platform == "darwin":
        command.insert(1, "-D_DARWIN_C_SOURCE=1")
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise Blocked("Native profile adapter build timed out; no game written") from exc
    if result.returncode:
        raise Blocked("Native profile API adapter build failed (requires C compiler and SQLite headers/library). "
                      "No game written. Alternatively supply existing test-profile IDs.\n" + result.stderr[-4000:])
    return binary


def validate_game():
    bootstrap()
    from scb_rules import Game
    try:
        rules = Game()
    except OSError as exc:
        raise Blocked(f"Existing native chess rules library unavailable: {exc}") from exc
    with rules:
        initial = rules.fen()
        positions = []
        for ply, move in enumerate(MOVES, 1):
            if move not in rules.legal_moves() or not rules.play(move):
                raise Blocked(f"Production rules reject fixture move {ply}: {move}; no game written")
            positions.append({"ply": ply, "uci": move, "fen": rules.fen(), "status": rules.status()})
        if not positions[-1]["status"].startswith("Checkmate"):
            raise Blocked("Production rules do not identify final position as checkmate; no game written")
        result = "0-1" if positions[-1]["fen"].split()[1] == "w" else "1-0"
        if result != "0-1" or any(p["status"].startswith("Checkmate") for p in positions[:-1]):
            raise Blocked("Unexpected production-rule outcome for Fool's Mate; no game written")
    return initial, positions, result


def verify(store, game_id, white, black, initial, positions, result):
    history = store.history(0)
    entry = next((g for g in history["games"] if g["id"] == game_id), None)
    if entry is None or any(entry[k] != value for k, value in
                            {"white": white["name"], "black": black["name"],
                             "result": result, "status": "completed", "mode": "pvp"}.items()):
        raise Blocked("Generated game not retrieved correctly through GameStore.history()")
    reviews = []
    for ply, fen, move in [(0, initial, "")] + [(p["ply"], p["fen"], p["uci"]) for p in positions]:
        review = store.review(game_id, ply)
        if (review["ply"] != ply or review["total"] != len(MOVES) or review["fen"] != fen
                or review["move"] != move or review["result"] != result
                or review["status"] != "completed" or LABEL not in review["reason"]):
            raise Blocked(f"GameStore.review() mismatch at ply {ply}")
        reviews.append(review)
    return {"history": entry, "reviews": reviews}


def generate(run, manifest, white_id=None, black_id=None):
    if manifest["purpose"] != "records":
        raise Blocked("Use a records-purpose run, not a write-failure database")
    # Same cooperative ownership lock as run_demo_service; never stops an owner.
    lock_path = no_symlinks(run / "service.lock")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Blocked("Demo service/generator owns this run. Close its UI/service manually first.") from exc
        # Guard the original Server's socket lock too, without opening any socket.
        socket_lock = no_symlinks(manifest["socket"] + ".lock")
        with context_socket_lock(socket_lock):
            return write_fixture(run, manifest, white_id, black_id)


class context_socket_lock:
    def __init__(self, path):
        self.path, self.file = path, None

    def __enter__(self):
        if self.path.exists():
            self.file = self.path.open("r")
            try:
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                self.file.close()
                raise Blocked("Existing production Server owns this test socket; close it manually first") from exc
        return self

    def __exit__(self, *_):
        if self.file:
            self.file.close()


def write_fixture(run, manifest, white_id, black_id):
    initial, positions, result = validate_game()  # Validate all moves before writing anything.
    helper = build_player_helper(run) if white_id is None else None
    bootstrap()
    from game_store import GameStore
    db_path = manifest["database"]
    store = GameStore(db_path)  # Original schema initialization and transaction implementation.
    game_id = None
    token = uuid.uuid4().hex
    try:
        before = database_snapshot(db_path)
        if any(g["status"] in {"active", "paused"} for g in before["games"]):
            raise Blocked("An active/paused test game exists; finish/close it in the real app before generating")
        if helper:
            try:
                built = subprocess.run([str(helper), db_path, "TIDR Fixture White", "TIDR Fixture Black"],
                                       capture_output=True, text=True, timeout=10)
            except subprocess.TimeoutExpired as exc:
                raise Blocked("Native profile API adapter timed out; no game started") from exc
            if built.returncode:
                raise Blocked("Production player_store API failed: " + built.stderr.strip())
            white_id, black_id = (int(value) for value in built.stdout.split())
        white, black = store.player(white_id), store.player(black_id)
        if white["id"] == black["id"]:
            raise Blocked("Test profiles must be distinct")
        game_id = store.start(white, black, "pvp", 0, initial, (None, None))
        # Record provenance before moves; a failed/partial attempt is never deleted or disguised.
        append(run / "generated_games.jsonl", {"kind": "started", "fixture": token,
               "game_id": game_id, "label": LABEL, "physical_gameplay_verified": False})
        for position in positions:
            terminal = position["ply"] == len(positions)
            store.move(game_id, position["ply"], position["uci"], position["fen"], (None, None),
                       result if terminal else "*", LABEL + "; " + position["status"])
        verified = verify(store, game_id, white, black, initial, positions, result)
        after = database_snapshot(db_path)
        if any(game_record(after, old["id"]) != game_record(before, old["id"]) for old in before["games"]):
            raise Blocked("Existing test records changed unexpectedly; inspect retained DB and provenance")
    except Exception as exc:
        append(run / "generated_games.jsonl", {"kind": "incomplete", "fixture": token,
               "game_id": game_id, "label": LABEL, "error": str(exc), "physical_gameplay_verified": False})
        raise
    finally:
        store.close()
    # Reopen through the original implementation and verify committed history and every review.
    store = GameStore(db_path)
    try:
        verify(store, game_id, white, black, initial, positions, result)
    finally:
        store.close()
    append(run / "generated_games.jsonl", {"kind": "verified", "fixture": token,
           "game_id": game_id, "label": LABEL, "result": result, "moves": list(MOVES),
           "physical_gameplay_verified": False, "verification": verified})
    return game_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    run_argument(parser)
    parser.add_argument("--init", action="store_true", help="Create a fresh records-purpose run first")
    parser.add_argument("--operator-confirms-demo-closed", action="store_true", required=True,
                        help="No application/service is using this isolated test database")
    parser.add_argument("--white-id", type=int, help="Existing test-profile ID; avoids native adapter build")
    parser.add_argument("--black-id", type=int, help="Existing test-profile ID; requires --white-id")
    args = parser.parse_args()
    if (args.white_id is None) != (args.black_id is None):
        parser.error("Supply both --white-id and --black-id, or neither")
    if args.init:
        create_run(args.run, "records")
    run, manifest = load_run(args.run)
    game_id = generate(run, manifest, args.white_id, args.black_id)
    print(f"FIXTURE VERIFIED (software/data only): game ID {game_id}; Black wins 0-1; 4 legal plies")
    print("Verified initial position and every move/position via production history()/review(), including reopen.")
    print(f"Test database: {manifest['database']}\nProvenance: {run / 'generated_games.jsonl'}")
    print("NOT a sensor-to-gameplay or complete TIDR #19 hardware PASS.")
    print("On final Pi, manually launch the isolated real application:")
    print(f"{shlex.quote(sys.executable)} -B {shlex.quote(str(BASE / 'run_demo_service.py'))} "
          f"--run {shlex.quote(str(run))} --port /dev/ttyACM0 --operator-confirms-controller-stopped")
    print(f"Paste its printed native UI command, then History -> game {game_id} -> Next/Previous.")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli(main))
