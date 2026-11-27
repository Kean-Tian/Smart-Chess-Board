"""Manually launch one observed production service with an isolated DB/socket."""
import argparse
import fcntl
import os
from pathlib import Path
import shlex
import signal
import stat
import sys

sys.dont_write_bytecode = True
from common.runtime import Blocked, ROOT, bootstrap, cli, load_run, no_symlinks, run_argument
from preflight import inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    run_argument(parser)
    parser.add_argument("--port", required=True, help="Actual final-board serial device (checked, not opened here)")
    parser.add_argument("--operator-confirms-controller-stopped", action="store_true", required=True,
                        help="Operator has safely exited the normal app and all serial controllers")
    args = parser.parse_args()
    run, manifest = load_run(args.run)
    checks = inspect(args.port)
    failed = [f"{c['name']}: {c['detail']}" for c in checks if not c["ok"]]
    if failed:
        raise Blocked("Preflight failed:\n" + "\n".join(failed))
    if not stat.S_ISCHR(Path(args.port).stat().st_mode):
        raise Blocked("Serial path is not a character device")
    no_symlinks(run / "service.lock")
    lock = (run / "service.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    socket = no_symlinks(manifest["socket"])
    no_symlinks(str(socket) + ".lock")
    socket.parent.mkdir(mode=0o700, exist_ok=True)
    if socket.parent.stat().st_uid != os.getuid() or stat.S_IMODE(socket.parent.stat().st_mode) != 0o700:
        raise Blocked("Socket directory must be private and owned by this user")
    if socket.exists():
        raise Blocked("Socket already exists; do not overwrite or probe an existing service")
    # Explicit values for this demo process only; no persistent configuration changes.
    os.environ.pop("SCB_PLAYER_DB", None)
    os.environ.pop("SCB_SERIAL_PORT", None)  # Operator connects through the native UI.
    os.environ["SCB_UI_SOCKET"] = str(socket)
    os.environ["SCB_AUTOMATIC_MOTION"] = "0"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    bootstrap()
    from common.observe import Observer
    import ui_service
    observer = Observer(run, manifest)
    binary = ROOT / "pi5/ui/build/native/scb_touch_ui"
    print("Service is demo-owned. In a second desktop terminal launch the existing UI:", flush=True)
    print(f"SCB_UI_SOCKET={shlex.quote(str(socket))} SCB_AUTOMATIC_MOTION=0 "
          f"{shlex.quote(str(binary))} --fullscreen --database {shlex.quote(manifest['database'])}", flush=True)
    print(f"Then use Connect board with {args.port}. No second serial client is launched.", flush=True)
    print("Finish: Quit the UI normally, then Ctrl-C in this service terminal. Never kill normal services.", flush=True)
    server = None
    cleanup_ok = True
    previous_handlers = {}
    try:
        observer.install()
        server = ui_service.Server(socket, manifest["database"])
        def stop(*_):
            server.running = False
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, stop)
        server.run()  # Original event loop, serial owner, rules, transactions and UI protocol.
    finally:
        try:
            if server is not None:
                try:
                    # The original loop has stopped. Finish any queued LED operation,
                    # then clear through the same owner before original close releases it.
                    if server.core.led_job:
                        server.core.led_job.result(timeout=2)
                    if server.core.link:
                        link = server.core.link
                        link.request("LED_CLEAR", timeout=0.6)
                        link.request("STOP", timeout=0.6)
                        from ui_hardware import values
                        status = values(link.request("STATUS", timeout=0.6))
                        cleanup_ok = all(status.get(k) == "0" for k in ("armed", "moving", "magnet"))
                        observer.emit("cleanup", acknowledged_safe=cleanup_ok, status=status,
                                      optical_led_clear_verified=False)
                    else:
                        observer.emit("cleanup", acknowledged_safe=None,
                                      note="no owned connection; verify outputs manually")
                except Exception as exc:
                    cleanup_ok = False
                    observer.emit("cleanup", acknowledged_safe=False, error=str(exc))
                    print(f"BLOCKED: cleanup not acknowledged: {exc}. Verify physical safety manually.", flush=True)
                finally:
                    server.close()  # Original cleanup releases workers, link, store and socket.
        finally:
            for signum, previous in previous_handlers.items():
                signal.signal(signum, previous)
            observer.close()
            lock.close()
    return 0 if cleanup_ok else 2


if __name__ == "__main__":
    raise SystemExit(cli(main))
