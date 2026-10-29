#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$task_root"
if [ "$(uname -s)" != Linux ]; then
    echo "Run setup.sh on the Pi running 64-bit Raspberry Pi OS." >&2
    exit 1
fi
case "$(uname -m)" in aarch64|arm64) ;; *) echo "64-bit ARM64 OS is required." >&2; exit 1 ;; esac
if ! command -v cmake >/dev/null 2>&1 || ! command -v c++ >/dev/null 2>&1 || ! command -v make >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y cmake build-essential
fi
if [ ! -x .venv/bin/python ]; then
    if ! python3 -m venv .venv; then
        sudo apt-get update
        sudo apt-get install -y python3-venv
        python3 -m venv .venv
    fi
fi
.venv/bin/python -m pip install --no-index --find-links vendor/python-wheels -r requirements.txt
chmod +x engines/stockfish/stockfish-linux-arm64-universal
.venv/bin/python app/verify_stockfish.py
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE="$task_root/.venv/bin/python"
cmake --build build -j 2
ctest --test-dir build --output-on-failure
mkdir -p runtime
.venv/bin/python app/stockfish_engine.py --self-test --report runtime/Stockfish_Runtime.json
echo "Setup verified on this Pi. Start console play with: sh start.sh"
