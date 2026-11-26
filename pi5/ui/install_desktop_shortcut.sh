#!/bin/sh
set -eu

task_ui=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
task_pi=$(CDPATH= cd -- "$task_ui/.." && pwd)
task_root=$(CDPATH= cd -- "$task_pi/.." && pwd)
task_desktop=$(xdg-user-dir DESKTOP 2>/dev/null || printf '%s/Desktop' "$HOME")
if [ -z "$task_desktop" ]; then task_desktop="$HOME/Desktop"; fi
test -f "$task_pi/start.sh"
test -f "$task_ui/assets/black-k.png"
mkdir -p "$task_desktop" "$HOME/.local/share/applications"

task_entry="$task_desktop/Smart Chess Board.desktop"
cat > "$task_entry" <<EOF
[Desktop Entry]
Type=Application
Name=Smart Chess Board
Comment=Launch the Smart Chess Board touchscreen interface
Exec=/bin/sh "$task_pi/start.sh" ui
Path=$task_root
Icon=$task_ui/assets/black-k.png
Terminal=false
Categories=Game;
StartupNotify=false
EOF
chmod +x "$task_entry"
cp "$task_entry" "$HOME/.local/share/applications/smart-chess-board.desktop"
if command -v gio >/dev/null 2>&1; then
    gio set "$task_entry" metadata::trusted true 2>/dev/null || true
fi
printf 'Created desktop shortcut: %s\n' "$task_entry"
