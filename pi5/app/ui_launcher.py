"""Run one native UI with its local service; retain SQLite history on exit."""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from game_store import database_path
from ui_service import socket_path


def main():
    # 启动入口：保证 C 界面和 Python 后台使用同一数据库及 socket。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    arguments = args.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if any(arg in {"--smoke-test", "--input-test", "--snapshots", "--service-test"} for arg in arguments):
        return subprocess.call([args.binary, *arguments])
    database = None
    if "--database" in arguments:
        index = arguments.index("--database")
        if index + 1 >= len(arguments):
            raise ValueError("--database requires a path")
        database = arguments[index+1]
    path = database_path(database)
    sock = socket_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    sock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = path.parent / "ui_service.log"
    env = dict(os.environ, SCB_PLAYER_DB=str(path), SCB_UI_SOCKET=str(sock))
    service = None
    ui = None
    try:
        with log_path.open("a") as log:
            # 先启动后台并等待可连接，再打开图形界面。
            service = subprocess.Popen([sys.executable, "-B", str(Path(__file__).with_name("ui_service.py")),
                                        "--socket", str(sock), "--database", str(path)],
                                       env=env, stdout=log, stderr=log)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if service.poll() is not None:
                    raise RuntimeError(f"Game service could not start. Close any other SCB UI. See {log_path}")
                if sock.exists():
                    # Connect only to the newly started service; its process lock prevents duplicates.
                    try:
                        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                            probe.settimeout(0.1)
                            probe.connect(str(sock))
                            if probe.recv(64):
                                break
                    except OSError:
                        pass
                time.sleep(0.05)
            else:
                raise RuntimeError(f"Timed out starting the game service. See {log_path}")
            ui = subprocess.Popen([args.binary, *arguments], env=env)
            return ui.wait()
    except KeyboardInterrupt:
        return 130
    finally:
        # 界面退出后收尾后台，让未结束对局和串口得到正常处理。
        if ui and ui.poll() is None:
            ui.terminate()
            try:
                ui.wait(timeout=3)
            except subprocess.TimeoutExpired:
                ui.kill()
                ui.wait()
        if service and service.poll() is None:
            service.terminate()
            try:
                service.wait(timeout=10)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
