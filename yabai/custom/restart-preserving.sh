#!/bin/sh
# The official command is unchanged; notifications belong to this custom wrapper.
set -eu
umask 077
BASE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DIR="$HOME/.local/state/yabai-preserving-restart"
mkdir -p "$DIR"
TMP="$(mktemp "$DIR/output.XXXXXX")"
trap 'rm -f "$TMP"' EXIT HUP INT TERM
ACTION="${1:-restart}"
EVENT_ACTION="$ACTION"
[ "$ACTION" != restore ] || EVENT_ACTION=recover
notify() {
    /opt/homebrew/bin/python3 "$BASE/notify.py" "$EVENT_ACTION" "$1" "$TMP" >> "$DIR/run.log" 2>&1 || true
}
printf '\n--- %s ---\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$DIR/run.log"
case "$ACTION" in restart|restore|capture) notify start ;; esac
if /opt/homebrew/bin/python3 "$BASE/restart_preserving.py" "$ACTION" > "$TMP" 2>&1; then
    cat "$TMP"
    cat "$TMP" >> "$DIR/run.log"
    case "$ACTION" in restart|restore|capture) notify success ;; esac
else
    cat "$TMP" >&2
    cat "$TMP" >> "$DIR/run.log"
    notify error
    exit 1
fi
