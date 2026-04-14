import sys
from .log import log_info, log_ok, log_warn, log_section
from .runner import run, prompt_yes_no

# Known macOS defaults (Apple Silicon / macOS 13+)
_APPLE_DEFAULTS = {
    "sleep":        ("1",  "System sleep (minutes, 0 = never)"),
    "disksleep":    ("10", "Disk sleep (minutes)"),
    "displaysleep": ("10", "Display sleep (minutes)"),
    "womp":         ("1",  "Wake on LAN"),
    "autorestart":  ("0",  "Auto-restart on power loss"),
}

def configure_power_settings(dry_run: bool) -> None:
    """Configure macOS for unattended server operation (requires sudo)."""
    log_section("Step F · macOS Server Power Settings")

    if not dry_run:
        log_warn("This step requires administrator privileges.")
        log_warn("You may be prompted for your password by 'sudo'.")
    else:
        log_info("[dry-run] Would execute sudo power configuration commands.")

    # List of tuples: (description, command)
    commands = [
        ("Prevent machine sleep", ["sudo", "pmset", "-a", "sleep", "0"]),
        ("Prevent disk sleep", ["sudo", "pmset", "-a", "disksleep", "0"]),
        ("Set display sleep to 10 min", ["sudo", "pmset", "-a", "displaysleep", "10"]),
        ("Enable Wake on LAN", ["sudo", "pmset", "-a", "womp", "1"]),
        ("Enable auto-restart on power loss", ["sudo", "pmset", "-a", "autorestart", "1"]),
        ("Enable restart on freeze", ["sudo", "systemsetup", "-setrestartfreeze", "on"]),
    ]

    for desc, cmd in commands:
        log_info(f"Applying: {desc}")
        try:
            result = run(cmd, capture=True, check=False, dry_run=dry_run, timeout=10)
            if not dry_run and result.returncode != 0:
                out = (result.stderr or result.stdout or "").strip()
                log_warn(f"Failed to apply {desc}: {out}")
        except Exception as exc:
            log_warn(f"Error applying {desc}: {exc}")

    log_info("Applying: Daily scheduled power-on (MTWRFSU at 06:00:00)")
    try:
        result = run(
            ["sudo", "pmset", "repeat", "wakeorpoweron", "MTWRFSU", "06:00:00"],
            capture=True, check=False, dry_run=dry_run, timeout=10
        )
        if not dry_run and result.returncode != 0:
            out = (result.stderr or result.stdout or "").strip()
            log_warn(f"Failed to set schedule: {out}")
    except Exception as exc:
        log_warn(f"Error setting schedule: {exc}")

    log_ok("Power settings applied.")
    if not dry_run:
        log_info("Current power configuration:")
        run(["pmset", "-g"], check=False, dry_run=False, timeout=10)


def revert_power_settings(dry_run: bool, force_yes: bool = False) -> None:
    """Revert macOS power settings to known Apple defaults with user confirmation."""
    log_section("Reverting macOS Power Settings to Defaults")

    log_info("The following settings will be restored to macOS defaults:")
    print()
    for key, (val, desc) in _APPLE_DEFAULTS.items():
        log_info(f"  {desc:<40s}  →  {key} = {val}")
    log_info(f"  {'Cancel scheduled power-on':<40s}  →  pmset repeat cancel")
    log_info(f"  {'Disable restart-on-freeze':<40s}  →  systemsetup -setrestartfreeze off")
    print()

    if not force_yes:
        if not prompt_yes_no("  Apply these defaults?", default=False, auto_yes=False):
            log_info("Skipped power settings revert.")
            return

    if not dry_run:
        log_warn("This step requires administrator privileges.")
        log_warn("You may be prompted for your password by 'sudo'.")
    else:
        log_info("[dry-run] Would execute sudo power revert commands.")

    # Restore each default
    for key, (val, desc) in _APPLE_DEFAULTS.items():
        log_info(f"Restoring: {desc}")
        try:
            result = run(
                ["sudo", "pmset", "-a", key, val],
                capture=True, check=False, dry_run=dry_run, timeout=10,
            )
            if not dry_run and result.returncode != 0:
                out = (result.stderr or result.stdout or "").strip()
                log_warn(f"Failed to restore {key}: {out}")
        except Exception as exc:
            log_warn(f"Error restoring {key}: {exc}")

    # Cancel repeat schedule
    log_info("Cancelling scheduled power-on")
    try:
        run(
            ["sudo", "pmset", "repeat", "cancel"],
            capture=True, check=False, dry_run=dry_run, timeout=10,
        )
    except Exception as exc:
        log_warn(f"Error cancelling schedule: {exc}")

    # Disable restart-on-freeze
    log_info("Disabling restart-on-freeze")
    try:
        run(
            ["sudo", "systemsetup", "-setrestartfreeze", "off"],
            capture=True, check=False, dry_run=dry_run, timeout=10,
        )
    except Exception as exc:
        log_warn(f"Error disabling restart-on-freeze: {exc}")

    log_ok("Power settings reverted to macOS defaults.")
    if not dry_run:
        log_info("Current power configuration:")
        run(["pmset", "-g"], check=False, dry_run=False, timeout=10)
