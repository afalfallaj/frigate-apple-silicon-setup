#!/bin/zsh
# headless_detector.sh — FrigateDetector Headless Launcher (template)
# ====================================================================
# NOTE: This is the template file stored in the repository.
# './setup.sh' will overwrite it with a version that has
# fully-resolved absolute paths for the current machine.

set -euo pipefail
#
# You can also run this manually after cloning, but you must ensure
# FrigateDetector.app is present in the same directory.

# ── Logging ──────────────────────────────────────────────────────────────────
echo "--- Detector Script Started at $(date) ---"

# ── Path resolution (no hardcoded usernames) ─────────────────────────────────
# Resolve the directory containing this script regardless of how it was invoked.
SCRIPT_DIR="${0:A:h}"   # zsh idiom: absolute path to the script's parent dir
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
APP_DIR="$PROJECT_DIR/FrigateDetector.app/Contents/Resources/app"

if [ ! -d "$APP_DIR" ]; then
    echo "ERROR: FrigateDetector.app not found at:"
    echo "  $APP_DIR"
    echo ""
    echo "Download/install the detector first:"
    echo "  python3 -m lib --skip-model --skip-volume --skip-plist"
    exit 1
fi

cd "$APP_DIR"

# ── Minimal headless environment ─────────────────────────────────────────────
# When invoked from launchd, PATH and HOME may be minimal.
# We explicitly set them here so the venv Python can locate its libs.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="${HOME:-$(eval echo ~$(id -un))}"
export USER="${USER:-$(id -un)}"

# ── Virtual environment Python ────────────────────────────────────────────────
PY="./venv/bin/python3"

if [ ! -f "$PY" ]; then
    echo "ERROR: Detector virtual environment not found at:"
    echo "  $APP_DIR/$PY"
    echo ""
    echo "Re-run setup to reinstall the detector:"
    echo "  python3 -m lib --skip-model --skip-volume --skip-plist"
    exit 1
fi

echo "Using Python: $(realpath $PY)"
echo "Launching Python detector core..."

# 'exec' replaces this shell with the Python process.
# launchd/the parent shell then tracks the Python PID directly.
exec "$PY" detector/zmq_onnx_client.py --model AUTO