#!/bin/zsh
# migrate_detector.sh — Migrate from old venv-based FrigateDetector to new bundled app
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== FrigateDetector Migration ==="

# 1. Remove old app from project directory
OLD_APP="$PROJECT_DIR/FrigateDetector.app"
if [[ -d "$OLD_APP" ]]; then
    echo "Removing old FrigateDetector.app from project directory..."
    rm -rf "$OLD_APP"
    echo "✓ Removed: $OLD_APP"
else
    echo "  No old FrigateDetector.app found in project directory."
fi

# 2. Remove old headless_detector.sh
OLD_SCRIPT="$SCRIPT_DIR/headless_detector.sh"
if [[ -f "$OLD_SCRIPT" ]]; then
    echo "Removing obsolete headless_detector.sh..."
    rm -f "$OLD_SCRIPT"
    echo "✓ Removed: $OLD_SCRIPT"
fi

# 3. Clean up old detector logs
OLD_LOG="$HOME/Library/Logs/FrigateNVR/detector.log"
OLD_LOG_BAK="$HOME/Library/Logs/FrigateNVR/detector.old.log"
for f in "$OLD_LOG" "$OLD_LOG_BAK"; do
    if [[ -f "$f" ]]; then
        rm -f "$f"
        echo "✓ Removed old log: $f"
    fi
done

echo ""
echo "Migration complete."
echo ""
echo "Next steps:"
echo "  1. Download FrigateDetector.dmg from:"
echo "     https://github.com/frigate-nvr/apple-silicon-detector/releases"
echo "  2. Drag FrigateDetector.app to /Applications/"
echo "  3. Or re-run ./setup.sh to download it automatically."
