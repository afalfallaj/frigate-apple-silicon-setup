#!/bin/zsh
# uninstall.sh — Frigate NVR Apple Silicon Uninstaller
# ====================================================================

set -euo pipefail

_BOLD=$(tput bold 2>/dev/null || echo '')
_CYAN=$(tput setaf 6 2>/dev/null || echo '')
_GREEN=$(tput setaf 2 2>/dev/null || echo '')
_YELLOW=$(tput setaf 3 2>/dev/null || echo '')
_RESET=$(tput sgr0 2>/dev/null || echo '')

echo "\n${_BOLD}${_CYAN}============================================================${_RESET}"
echo "${_BOLD}  Frigate Apple Silicon Uninstaller${_RESET}"
echo "${_BOLD}${_CYAN}============================================================${_RESET}\n"

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

echo "${_BOLD}[1/4] Stopping and removing Docker containers...${_RESET}"
if command -v docker >/dev/null 2>&1; then
    docker compose down -v 2>/dev/null || true
    echo "${_GREEN}Containers and network volumes removed.${_RESET}\n"
else
    echo "${_YELLOW}Docker not found, skipping container removal.${_RESET}\n"
fi

echo "${_BOLD}[2/4] Unloading macOS launchctl service...${_RESET}"
PLIST_PATH="$HOME/Library/LaunchAgents/com.frigate.nvr.plist"
if [ -f "$PLIST_PATH" ]; then
    launchctl bootout gui/$(id -u) "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "${_GREEN}LaunchAgent service (com.frigate.nvr) removed.${_RESET}\n"
else
    echo "${_YELLOW}No launchctl service found.${_RESET}\n"
fi

echo "${_BOLD}[3/4] Reverting macOS power settings...${_RESET}"
if [ -x "/opt/homebrew/bin/python3" ]; then
    echo "You may be prompted for your password via 'sudo' to revert pmset defaults."
    /opt/homebrew/bin/python3 -c "import sys; sys.path.append('$SCRIPT_DIR'); from lib.power import revert_power_settings; revert_power_settings(False, True)" 2>/dev/null || true
    echo "${_GREEN}Power settings reverted.${_RESET}\n"
else
    echo "${_YELLOW}Python3 not found, skipping power revert.${_RESET}\n"
fi

echo "${_BOLD}[4/4] Removing downloaded FrigateDetector.app...${_RESET}"
if [ -d "FrigateDetector.app" ]; then
    rm -rf "FrigateDetector.app"
    echo "${_GREEN}FrigateDetector.app removed from project directory.${_RESET}\n"
else
    echo "${_YELLOW}FrigateDetector.app not found.${_RESET}\n"
fi

echo "${_BOLD}${_CYAN}============================================================${_RESET}"
echo "${_GREEN}Uninstallation logic finished!${_RESET}"
echo "To completely erase everything, safely delete this folder:"
echo "  rm -rf \"$SCRIPT_DIR\""
echo "============================================================\n"
