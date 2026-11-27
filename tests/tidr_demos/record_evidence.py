"""Attach operator-supplied physical evidence; never controls the application."""
import argparse
from pathlib import Path
import shutil
import sys
import uuid

sys.dont_write_bytecode = True
from common.runtime import append, cli, digest, load_run, run_argument


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    run_argument(parser)
    parser.add_argument("--kind", required=True, choices=["hardware", "power-cycle", "replay-visible"])
    parser.add_argument("--label", required=True, help="Game ID for power-cycle; window name for replay")
    parser.add_argument("--file", type=Path, required=True, help="Actual photo/video/instrument evidence")
    parser.add_argument("--operator", required=True)
    parser.add_argument("--note", required=True, help="Observed final hardware, actions and evidence interpretation")
    args = parser.parse_args()
    run, _ = load_run(args.run)
    if not args.file.is_file() or args.file.stat().st_size == 0:
        parser.error("Evidence must be an existing nonempty file")
    target = run / "evidence" / (uuid.uuid4().hex + args.file.suffix)
    shutil.copyfile(args.file, target)
    append(run / "attachments.jsonl", {"kind": args.kind, "label": args.label,
           "path": str(target.relative_to(run)), "sha256": digest(target),
           "operator": args.operator, "note": args.note,
           "provenance": "operator supplied physical observation; not automatically verified"})
    print(f"Attached {args.kind} evidence: {target}; attachment alone is not a PASS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli(main))
