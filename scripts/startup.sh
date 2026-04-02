#!/bin/zsh
# startup.sh — Frigate NVR Boot Wrapper
# ======================================
# NOTE: This file is the *template* kept in the repository.
# During setup.sh execution (Step E), a fully-configured 'start_frigate.sh'
# is generated in this same directory and registered with launchctl instead.
# You can also invoke this script manually for testing.
#
# All paths are resolved dynamically — no hardcoded usernames or directories.

set -euo pipefail

# ── Resolve the project directory (the folder containing this script's parent) ────────
SCRIPT_DIR="${0:A:h}"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_DIR="$HOME/Library/Logs/FrigateNVR"
mkdir -p "$LOG_DIR"

# Rotate the previous log
[ -f "$LOG_DIR/boot.log" ] && mv -f "$LOG_DIR/boot.log" "$LOG_DIR/boot.old.log" 2>/dev/null

LOG_FILE="$LOG_DIR/boot.log"
exec > "$LOG_FILE" 2>&1
echo "--- Boot sequence started at $(date) ---"
echo "Project directory: $PROJECT_DIR"

# ── Environment (launchd provides a minimal environment; set essentials here) ─
# We derive HOME from the running user rather than hardcoding a username.
export USER="${USER:-$(id -un)}"
export HOME="${HOME:-$(eval echo ~$USER)}"
export PATH="$HOME/.orbstack/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

echo "Running as user: $USER (HOME=$HOME)"

# ── OrbStack ─────────────────────────────────────────────────────────────────
echo "Initialising OrbStack..."
# Try both Homebrew (Apple Silicon) and legacy Intel prefixes
ORB_BIN="$(command -v orb 2>/dev/null || echo '')"
if [[ -z "$ORB_BIN" ]]; then
    echo "ERROR: 'orb' not found on PATH. Is OrbStack installed?"
    echo "Install: brew install orbstack"
    exit 1
fi

"$ORB_BIN" start || {
    echo "ERROR: OrbStack failed to start."
    exit 1
}

# ── Wait for Docker daemon ────────────────────────────────────────────────────
echo "Waiting for Docker to become available..."
DOCKER_BIN="$(command -v docker 2>/dev/null || echo /usr/local/bin/docker)"

# Poll up to 120 seconds (60 × 2s) before giving up
for i in $(seq 1 60); do
    "$DOCKER_BIN" info > /dev/null 2>&1 && break
    sleep 2
done

"$DOCKER_BIN" info > /dev/null 2>&1 || {
    echo "ERROR: Docker daemon did not become ready within 120 seconds."
    exit 1
}
echo "Docker is ready."

# ── Frigate Compose ───────────────────────────────────────────────────────────
echo "Starting Frigate containers..."
cd "$PROJECT_DIR"
"$DOCKER_BIN" compose up -d

# ── FrigateDetector ───────────────────────────────────────────────────────────
DETECTOR_SCRIPT="$SCRIPT_DIR/headless_detector.sh"
if [[ -f "$DETECTOR_SCRIPT" ]]; then
    echo "Launching FrigateDetector..."
    # Rotate detector log
    [ -f "$LOG_DIR/detector.log" ] && mv -f "$LOG_DIR/detector.log" "$LOG_DIR/detector.old.log" 2>/dev/null

    # exec replaces this shell — launchd will track the detector's PID directly
    exec /bin/zsh "$DETECTOR_SCRIPT" > "$LOG_DIR/detector.log" 2>&1
else
    echo "WARNING: headless_detector.sh not found at '$DETECTOR_SCRIPT'."
    echo "Run './setup.sh' to generate it."
fi