import os
import shutil
import subprocess
from typing import Optional

from .log import log_info

class SetupError(RuntimeError):
    """Raised when a fatal, unrecoverable setup step fails."""

def run(
    cmd: list[str],
    *,
    capture: bool = False,
    check: bool = True,
    dry_run: bool = False,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """
    Thin wrapper around subprocess.run with consistent logging.
    """
    display = " ".join(str(a) for a in cmd)
    log_info(f"$ {display}")
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, "", "")

    try:
        if capture:
            # When capturing, we grab stdout and stderr
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={**os.environ, **(env or {})},
                timeout=timeout,
            )
        else:
            # If not capturing, let stdout/stderr go to terminal, but we can't save it.
            # To support verbose logging, we might want to pipe and log conditionally,
            # but for now, we just pass through.
            result = subprocess.run(
                cmd,
                text=True,
                env={**os.environ, **(env or {})},
                timeout=timeout,
            )
    except subprocess.TimeoutExpired as exc:
        raise SetupError(f"Command timed out after {timeout}s: {display}") from exc

    if check and result.returncode != 0:
        err_msg = ""
        if capture:
            err_msg = f"\n{result.stderr or result.stdout or ''}"
        raise SetupError(
            f"Command failed (exit {result.returncode}): {display}{err_msg}"
        )
    return result

def which(binary: str) -> str | None:
    """Return the full path to a binary if it exists on PATH, else None."""
    return shutil.which(binary)

def prompt_yes_no(question: str, default: bool = True, auto_yes: bool = False) -> bool:
    """Prompt the user with a yes/no question. Returns True for yes, False for no."""
    import sys
    if auto_yes:
        return default
    
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    prompt = " [Y/n] " if default else " [y/N] "
    
    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower().strip()
        if default is not None and choice == "":
            return default
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' (or 'y' or 'n').\n")

