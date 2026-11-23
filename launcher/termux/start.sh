#!/data/data/com.termux/files/usr/bin/bash
# Starts the launcher backend in Termux: `start.sh <port>`.
# Keeps the CPU awake while the backend runs and releases the wake lock when it ends.
# Logs, so a failure can be read later without adb:
#   $HOME/launcher-backend.log             backend and app output (rotated by the backend) plus this
#                                          script's own lines (rotated here)
#   $HOME/launcher-backend.start-error.log python's stderr from before logging is set up (missing
#                                          python, import error); truncated at every start
# This file must keep LF line endings: CRLF breaks the shebang and every command.

LOG="$HOME/launcher-backend.log"
START_ERROR_LOG="$HOME/launcher-backend.start-error.log"
LOG_MAX_BYTES=1000000   # same as launcher/backend/logs.py LOG_MAX_BYTES
LOG_BACKUP_COUNT=3      # same as launcher/backend/logs.py LOG_BACKUP_COUNT
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
backend_pid=""

# Plain mv rotation (.1 newest ... .3 oldest, which is dropped) before this script appends.
rotate_log() {
    [ -f "$LOG" ] || return 0
    [ "$(( $(wc -c < "$LOG") ))" -gt "$LOG_MAX_BYTES" ] || return 0
    rm -f "$LOG.$LOG_BACKUP_COUNT"
    i=$((LOG_BACKUP_COUNT - 1))
    while [ "$i" -ge 1 ]; do
        [ -f "$LOG.$i" ] && mv "$LOG.$i" "$LOG.$((i + 1))"
        i=$((i - 1))
    done
    mv "$LOG" "$LOG.1"
}

log() {
    rotate_log
    printf '%s start.sh: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
}

case "$1" in
    '' | *[!0-9]*)
        log "port must be a number, got '$1'"
        exit 2
        ;;
esac

cd "$REPO_ROOT" || exit 1

cleanup() {
    trap - EXIT
    if [ -n "$backend_pid" ] && kill -0 "$backend_pid" 2>/dev/null; then
        kill "$backend_pid" 2>/dev/null
        wait "$backend_pid" 2>/dev/null
    fi
    termux-wake-unlock
    log "wake lock released"
}
# Set before the lock is taken, so no exit path can leave it held. A signal only runs a trap
# after the foreground command ends, hence the backend runs in the background and is waited on;
# the signal traps exit, which fires the EXIT trap.
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

termux-wake-lock

export PYTHONPATH="$REPO_ROOT"
log "starting backend on port $1"
python -m launcher.backend --port "$1" --watchdog --log-file "$LOG" 2>"$START_ERROR_LOG" &
backend_pid=$!
wait "$backend_pid"
status=$?
backend_pid=""
log "backend exited with code $status"
exit "$status"
