"""Read-only checks; never opens a serial device, socket, UI or database."""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from common.runtime import ROOT, bootstrap, cli, create_run, load_run


def inspect(port=None):
    bootstrap()
    checks = []
    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    model = Path("/proc/device-tree/model")
    identity = model.read_text().strip("\x00\n") if model.exists() else "not a Pi device-tree host"
    add("final Pi 5 host", "Raspberry Pi 5" in identity, identity)
    binary = ROOT / "pi5/ui/build/native/scb_touch_ui"
    add("existing native UI", binary.is_file() and os.access(binary, os.X_OK), binary)
    from scb_rules import LIBRARY
    add("existing native rules library", LIBRARY.is_file(), LIBRARY)
    add("pyserial installed", importlib.util.find_spec("serial") is not None, "import discovery only")
    add("desktop session", bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
        "DISPLAY/WAYLAND_DISPLAY; physical touchscreen still needs operator verification")
    try:
        ps = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True, timeout=5, check=True)
        relevant = [line for line in ps.stdout.splitlines() if any(s in line for s in
                    ("ui_service.py", "ui_launcher.py", "scb_touch_ui", "app/play.py", "app/scb_link.py",
                     "run_demo_service.py")) and str(os.getpid()) != line.strip().split()[0]]
        add("controller process inventory", not relevant, "\n".join(relevant) or "no known controller found")
    except (OSError, subprocess.SubprocessError) as exc:
        add("controller process inventory", False, exc)
    if port:
        add("serial device present", Path(port).exists() and port.startswith("/dev/"), port)
        try:
            owned = subprocess.run(["fuser", port], capture_output=True, text=True, timeout=5)
            add("device-owner inspection", owned.returncode == 1 and not owned.stderr.strip(),
                (owned.stdout + owned.stderr).strip() or f"fuser exit {owned.returncode}")
        except (OSError, subprocess.SubprocessError) as exc:
            add("device-owner inspection", False, f"ownership unknown: {exc}")
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init", help="Explicitly create a fresh isolated run (no database/service is opened)")
    parser.add_argument("--purpose", choices=["records", "failure"], default="records")
    parser.add_argument("--port", help="Final device path; read-only fuser check")
    parser.add_argument("--run", help="Inspect an existing run's paths")
    args = parser.parse_args()
    if args.init and args.run:
        parser.error("Choose --init or --run")
    if args.init:
        run = create_run(args.init, args.purpose)
        print(f"Created isolated {args.purpose} run: {run}")
    elif args.run:
        run, manifest = load_run(args.run)
        print(f"Database: {manifest['database']}\nSocket: {manifest['socket']}")
    checks = inspect(args.port)
    for item in checks:
        print(f"{'READY' if item['ok'] else 'BLOCKED'}: {item['name']}: {item['detail']}")
    print("Read-only checks are not physical verification or proof that every controller is absent.")
    return 0 if all(c["ok"] for c in checks) else 2


if __name__ == "__main__":
    raise SystemExit(cli(main))
