#!/usr/bin/env bash
#
# Raspberry Pi camera environment diagnostics for the photobooth.
#
# Verifies, independently of the Flask application, that the operating-system
# camera stack (rpicam-apps / libcamera) can control the connected camera:
# executable discovery, camera detection, one still capture and one bounded
# headless MJPEG video run.
#
# Safety: runs as a normal user, never uses sudo, never installs software and
# never changes system configuration. Temporary images are written to a private
# mktemp directory (never the photobooth gallery) and removed on exit. Every
# rpicam process is bounded by both its own -t option and `timeout`, so none is
# left running.
#
# Exit status: 0 when all mandatory camera checks pass, 1 otherwise.
#
# Usage: scripts/pi-diagnostics.sh

set -u

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this script as a normal user, not root." >&2
    exit 2
fi

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
MANDATORY_FAILED=0

TMP_DIR="$(mktemp -d -t photobooth-pi-diag.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

pass() { echo "PASS  $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
skip() { echo "SKIP  $1"; SKIP_COUNT=$((SKIP_COUNT + 1)); }
# fail <message> [mandatory]
fail() {
    echo "FAIL  $1"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    if [ "${2:-}" = "mandatory" ]; then
        MANDATORY_FAILED=1
    fi
}
info() { echo "      $1"; }

# Print the last lines of a log file indented, for failure context.
show_log() {
    if [ -s "$1" ]; then
        tail -n 5 "$1" | sed 's/^/      | /'
    fi
}

echo "== Environment"
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    info "OS:         $(. /etc/os-release && echo "${PRETTY_NAME:-unknown}")"
fi
if [ -r /etc/rpi-issue ]; then
    info "Pi image:   $(head -n 1 /etc/rpi-issue)"
fi
info "Arch:       $(uname -m)"
info "Kernel:     $(uname -r)"
if [ -r /proc/device-tree/model ]; then
    info "Model:      $(tr -d '\0' < /proc/device-tree/model)"
else
    info "Model:      unknown (/proc/device-tree/model not readable)"
fi
info "Python:     $(command -v python3 >/dev/null && python3 --version 2>&1 || echo 'python3 not found')"
info "uv:         $(command -v uv >/dev/null && uv --version 2>&1 || echo 'uv not found')"
info "Disk (cwd): $(df -h . | awk 'NR==2 {print $4 " free of " $2}')"

echo
echo "== Permissions"
info "User:       $(id -un) ($(id))"
if id -nG | tr ' ' '\n' | grep -qx video; then
    pass "user is in the 'video' group"
else
    # Desktop sessions may still grant access via ACLs, so this is not fatal.
    fail "user is not in the 'video' group (manual fix: sudo usermod -aG video $(id -un), then log in again)"
fi
media_nodes=$(ls /dev/media* 2>/dev/null | wc -l)
if [ "$media_nodes" -gt 0 ]; then
    pass "$media_nodes /dev/media* device node(s) present"
else
    fail "no /dev/media* device nodes present"
fi

echo
echo "== rpicam executables"
for cmd in rpicam-hello rpicam-still rpicam-vid; do
    path="$(command -v "$cmd" 2>/dev/null || true)"
    if [ -n "$path" ]; then
        pass "$cmd available at $path"
        info "$("$path" --version 2>&1 | head -n 1)"
    else
        fail "$cmd not found on PATH (manual fix: sudo apt install rpicam-apps)" mandatory
    fi
done
if command -v rpicam-hello >/dev/null; then
    info "$(rpicam-hello --version 2>&1 | grep -i '^libcamera' | head -n 1)"
fi

echo
echo "== Camera detection"
CAMERA_OK=0
if command -v rpicam-hello >/dev/null; then
    if timeout 20 rpicam-hello --list-cameras > "$TMP_DIR/cameras.txt" 2>&1 \
        && grep -qE '^[0-9]+ : ' "$TMP_DIR/cameras.txt"; then
        CAMERA_OK=1
        pass "camera detected"
        sed -n '/^[0-9]* : /,$p' "$TMP_DIR/cameras.txt" | sed 's/^/      /'
    else
        fail "no camera detected by rpicam-hello --list-cameras" mandatory
        show_log "$TMP_DIR/cameras.txt"
    fi
else
    skip "camera detection (rpicam-hello missing)"
fi

echo
echo "== Still capture"
if [ "$CAMERA_OK" -eq 1 ] && command -v rpicam-still >/dev/null; then
    still="$TMP_DIR/still.jpg"
    if timeout 30 rpicam-still --nopreview --immediate -t 1 -o "$still" \
        > "$TMP_DIR/still.log" 2>&1; then
        if [ -s "$still" ]; then
            if command -v file >/dev/null; then
                description="$(file -b "$still")"
                case "$description" in
                    JPEG*) pass "still capture: $(echo "$description" | grep -oE '[0-9]+x[0-9]+' | tail -n 1) JPEG, $(stat -c %s "$still") bytes" ;;
                    *) fail "still capture output is not a JPEG: $description" mandatory ;;
                esac
            else
                pass "still capture: non-empty file, $(stat -c %s "$still") bytes (format not checked: 'file' missing)"
            fi
        else
            fail "rpicam-still exited successfully but produced no image" mandatory
        fi
    else
        fail "rpicam-still failed or timed out" mandatory
        show_log "$TMP_DIR/still.log"
    fi
else
    skip "still capture (camera or rpicam-still unavailable)"
fi

echo
echo "== Bounded headless video (MJPEG to stdout)"
if [ "$CAMERA_OK" -eq 1 ] && command -v rpicam-vid >/dev/null; then
    video="$TMP_DIR/video.mjpeg"
    # Same transport the future browser preview is expected to use: MJPEG on stdout.
    if timeout 15 rpicam-vid --nopreview -t 2000 --codec mjpeg \
        --width 1280 --height 720 -o - > "$video" 2> "$TMP_DIR/video.log"; then
        if [ -s "$video" ] && head -c 2 "$video" | od -An -tx1 | grep -q 'ff d8'; then
            pass "rpicam-vid streamed $(stat -c %s "$video") bytes of MJPEG and exited normally"
        else
            fail "rpicam-vid exited successfully but produced no MJPEG data" mandatory
        fi
    else
        fail "rpicam-vid failed or timed out" mandatory
        show_log "$TMP_DIR/video.log"
    fi

    # An indefinite preview (-t 0) must stop promptly on SIGINT; timeout sends
    # the signal after 3 s and reports 124 when it had to do so.
    timeout -s INT -k 5 3 rpicam-vid --nopreview -t 0 --codec mjpeg -o /dev/null \
        > "$TMP_DIR/sigint.log" 2>&1
    status=$?
    if [ "$status" -eq 124 ]; then
        pass "indefinite rpicam-vid stopped on SIGINT"
    else
        fail "indefinite rpicam-vid did not stop cleanly on SIGINT (status $status)"
        show_log "$TMP_DIR/sigint.log"
    fi
else
    skip "video (camera or rpicam-vid unavailable)"
fi

if pgrep -u "$(id -u)" -x 'rpicam-(hello|still|vid)' >/dev/null 2>&1; then
    fail "rpicam process still running after diagnostics"
fi

echo
echo "== Summary: $PASS_COUNT passed, $FAIL_COUNT failed, $SKIP_COUNT skipped"
if [ "$MANDATORY_FAILED" -ne 0 ]; then
    echo "Mandatory camera prerequisites FAILED (system/hardware level, below the application)."
    exit 1
fi
echo "Mandatory camera prerequisites passed."
exit 0
