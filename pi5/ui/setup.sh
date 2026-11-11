#!/bin/sh
set -eu
task_ui=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$(uname -s)" != Linux ]; then
    echo "On macOS install SDL2, then run build.sh. Run this installer on Raspberry Pi OS." >&2
    exit 1
fi
sudo apt-get update
sudo apt-get install -y build-essential cmake libsdl2-dev libsqlite3-dev sqlite3 python3-venv ca-certificates
# Prepare the existing native rules, Python serial environment and local engine.
sh "$task_ui/../setup.sh"
# Remove obsolete generated example screens when upgrading the first UI package.
for task_old in setup-computer setup-coach board-setup board-ready game paused review; do
    rm -f "$task_ui/preview/$task_old.png"
done
# A source update must replace cached UI objects even if an archive had old times.
touch "$task_ui/CMakeLists.txt" "$task_ui"/src/*.c "$task_ui"/src/*.h
sh "$task_ui/build.sh"
echo "UI build and checks finished. Start it with: sh pi5/start.sh ui"
