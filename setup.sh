#!/bin/zsh
# setup.sh — Frigate Apple Silicon Entrypoint
# ====================================================================

set -euo pipefail

_BOLD=$(tput bold 2>/dev/null || echo '')
_CYAN=$(tput setaf 6 2>/dev/null || echo '')
_GREEN=$(tput setaf 2 2>/dev/null || echo '')
_YELLOW=$(tput setaf 3 2>/dev/null || echo '')
_RESET=$(tput sgr0 2>/dev/null || echo '')

SCRIPT_DIR="${0:A:h}"

echo "\n${_BOLD}${_CYAN}============================================================${_RESET}"
echo "${_BOLD}  Frigate Apple Silicon Setup${_RESET}"
echo "${_BOLD}${_CYAN}============================================================${_RESET}\n"

# 1. Architecture Check
if [[ "$(uname -m)" != "arm64" ]]; then
    echo "${_YELLOW}[WARN] Expected arm64 (Apple Silicon) but detected $(uname -m).${_RESET}"
else
    echo "${_GREEN}[ OK ] Apple Silicon (arm64) confirmed.${_RESET}"
fi

# 2. Homebrew Check/Install
if [[ ! -x "/opt/homebrew/bin/brew" ]] && ! command -v brew >/dev/null 2>&1; then
    echo "${_YELLOW}[INFO] Homebrew not found. Installing...${_RESET}"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# add Homebrew bin to PATH
if [[ -x "/opt/homebrew/bin/brew" ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi
echo "${_GREEN}[ OK ] Homebrew loaded: $(command -v brew)${_RESET}"

# 3. Python Check/Install (strictly ensuring Homebrew Python)
if [[ ! -x "/opt/homebrew/bin/python3" ]]; then
    echo "${_YELLOW}[INFO] Homebrew Python3 not found. Installing...${_RESET}"
    brew install python
else
    echo "${_GREEN}[ OK ] Homebrew Python3 found at: /opt/homebrew/bin/python3${_RESET}"
fi

# 4. Docker Runtime Check/Install
if ! command -v docker >/dev/null 2>&1 && ! command -v orb >/dev/null 2>&1; then
    echo "${_YELLOW}[ERROR] Docker runtime missing. OrbStack or Docker is required.${_RESET}"
    echo "Please install OrbStack (https://orbstack.dev/) and try again."
    exit 1
else
    echo "${_GREEN}[ OK ] Docker runtime detected.${_RESET}"
fi

# Add OrbStack bin to PATH
export PATH="$HOME/.orbstack/bin:$PATH"

# 5. Launch Python setup using explicitly the Homebrew Python
cd "$SCRIPT_DIR"
exec /opt/homebrew/bin/python3 -m lib "$@"
