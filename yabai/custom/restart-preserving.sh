#!/bin/sh
# Keep the normal yabai --restart-service available; this wrapper adds recovery.
set -eu
umask 077
DIR="$HOME/.local/state/yabai-preserving-restart"
mkdir -p "$DIR"
printf '\n--- %s ---\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$DIR/run.log"
if /opt/homebrew/bin/python3 "$HOME/.config/yabai/custom/restart_preserving.py" "${1:-restart}" >> "$DIR/run.log" 2>&1; then
    exit 0
else
    /usr/bin/osascript -e 'display notification "No se completó la restauración. Conservé el archivo de recuperación; revisa el registro antes de reiniciar otra vez." with title "yabai"' >/dev/null 2>&1 || true
    exit 1
fi
