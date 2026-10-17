#!/bin/zsh
# migrate_detector.sh — Migrate from old venv-based FrigateDetector to new architecture
set -euo pipefail

_BOLD=$(tput bold 2>/dev/null || echo '')
_CYAN=$(tput setaf 6 2>/dev/null || echo '')
_GREEN=$(tput setaf 2 2>/dev/null || echo '')
_YELLOW=$(tput setaf 3 2>/dev/null || echo '')
_RESET=$(tput sgr0 2>/dev/null || echo '')

SCRIPT_DIR="${0:A:h}"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "${_BOLD}${_CYAN}============================================================${_RESET}"
echo "${_BOLD}  FrigateDetector Migration Utility${_RESET}"
echo "${_BOLD}${_CYAN}============================================================${_RESET}\n"

# 1. Handle Startup Changes (Service Migration)
echo "${_BOLD}[1/5] Checking for legacy launchctl services...${_RESET}"
UID_G=$(id -u)
for LABEL in "com.frigate.nvr" "com.google.frigate-nvr.detector"; do
    if launchctl print "gui/$UID_G/$LABEL" >/dev/null 2>&1; then
        echo "Found active service: $LABEL. Unloading..."
        # Try to locate the plist to unload it cleanly
        PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
        if [[ -f "$PLIST" ]]; then
            launchctl bootout "gui/$UID_G" "$PLIST" 2>/dev/null || true
            rm -f "$PLIST"
        else
            launchctl bootout "gui/$UID_G/$LABEL" 2>/dev/null || true
        fi
        echo "${_GREEN}✓ Unloaded and removed service: $LABEL${_RESET}"
    fi
done

# 2. Remove old app and scripts from project directory
echo "\n${_BOLD}[2/5] Cleaning up legacy files from project root...${_RESET}"
OLD_APP="$PROJECT_DIR/FrigateDetector.app"
if [[ -d "$OLD_APP" ]]; then
    echo "Removing old local FrigateDetector.app..."
    rm -rf "$OLD_APP"
    echo "${_GREEN}✓ Removed: $OLD_APP${_RESET}"
fi

OLD_SCRIPT="$SCRIPT_DIR/headless_detector.sh"
if [[ -f "$OLD_SCRIPT" ]]; then
    echo "Removing obsolete headless_detector.sh..."
    rm -f "$OLD_SCRIPT"
    echo "${_GREEN}✓ Removed: $OLD_SCRIPT${_RESET}"
fi

# 3. Clean up legacy Python environments
echo "\n${_BOLD}[3/5] Checking for legacy Python virtual environments...${_RESET}"
for VENV in "venv" ".venv"; do
    if [[ -d "$PROJECT_DIR/$VENV" ]]; then
        echo "Removing legacy environment: $VENV..."
        rm -rf "$PROJECT_DIR/$VENV"
        echo "${_GREEN}✓ Removed: $VENV${_RESET}"
    fi
done

# 4. Clean up legacy CLI symlinks
echo "\n${_BOLD}[4/5] Checking for legacy CLI symlinks...${_RESET}"
CLI_LINK="$HOME/.local/bin/detector"
if [[ -L "$CLI_LINK" ]]; then
    # Only remove if it's pointing to the project directory (legacy)
    TARGET=$(readlink "$CLI_LINK" || echo "")
    if [[ "$TARGET" == "$PROJECT_DIR"* ]]; then
        echo "Removing legacy CLI symlink: $CLI_LINK"
        rm -f "$CLI_LINK"
        echo "${_GREEN}✓ Removed legacy symlink${_RESET}"
    fi
fi

# 5. Clean up old detector logs
echo "\n${_BOLD}[5/5] Cleaning up legacy log files...${_RESET}"
OLD_LOG="$HOME/Library/Logs/FrigateNVR/detector.log"
OLD_LOG_BAK="$HOME/Library/Logs/FrigateNVR/detector.old.log"
for f in "$OLD_LOG" "$OLD_LOG_BAK"; do
    if [[ -f "$f" ]]; then
        rm -f "$f"
        echo "${_GREEN}✓ Removed old log: $f${_RESET}"
    fi
done

echo "\n${_BOLD}${_CYAN}============================================================${_RESET}"
echo "${_GREEN}Migration cleanup completed!${_RESET}"
echo "${_CYAN}============================================================${_RESET}\n"

echo "The Frigate Apple Silicon setup has moved to a standalone architecture:"
echo "  • Detector App : Now resides in ${_BOLD}/Applications/FrigateDetector.app${_RESET}"
echo "  • Boot Service : Managed via the project's ${_BOLD}scripts/startup.sh${_RESET}"
echo "  • CLI Tool     : New location at ${_BOLD}/Applications/FrigateDetector.app/Contents/MacOS/detector${_RESET}"
echo ""

# Interactive Setup Trigger
if [[ -t 0 ]]; then
    read -q "REPLY?Do you want to run ./setup.sh now to install the new version? [y/N] "
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        exec "$PROJECT_DIR/setup.sh"
    fi
fi

echo "To finish manually:"
echo "  1. Run ${_BOLD}./setup.sh${_RESET} to download the app and register the new boot service."
echo "  2. Or download the .dmg manually from GitHub releases."
echo ""
