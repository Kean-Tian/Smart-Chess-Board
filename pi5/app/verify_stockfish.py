"""Verify bundled binary against the checksum recorded during official download."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "engines/stockfish/UPSTREAM_RELEASE.json").read_text())
binary = root / "engines/stockfish" / manifest["binary"]
actual = hashlib.sha256(binary.read_bytes()).hexdigest()
if actual != manifest["binary_sha256"]:
    raise SystemExit("Stockfish SHA-256 mismatch. Do not use the modified/incomplete binary.")
print(f"Verified {manifest['release']}: Linux ARM64 binary SHA-256 matches.")
