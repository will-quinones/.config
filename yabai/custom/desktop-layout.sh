#!/bin/sh
set -eu
umask 077
BASE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DATA="$HOME/.local/state/yabai-desktop-layout"
mkdir -p "$DATA"
TMP="$(mktemp "$DATA/output.XXXXXX")"
trap 'rm -f "$TMP"' EXIT HUP INT TERM
notify() {
    /opt/homebrew/bin/python3 "$BASE/notify.py" "${1:-unknown}" "$2" "$TMP" >> "$DATA/run.log" 2>&1 || true
}
case "${1:-}" in
    save|restore|restore-open|preview) notify "$1" start ;;
esac
if /opt/homebrew/bin/python3 "$BASE/desktop-layout.py" "$@" > "$TMP" 2>&1; then
    cat "$TMP"
    { date; cat "$TMP"; } >> "$DATA/run.log"
    case "${1:-}" in
        save|restore|restore-open|preview) notify "$1" success ;;
    esac
else
    cat "$TMP" >&2
    { date; cat "$TMP"; } >> "$DATA/run.log"
    notify "${1:-unknown}" error
    exit 1
fi
