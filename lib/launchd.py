import os
import plistlib
from pathlib import Path

from .log import log_info, log_ok, log_warn, log_section
from .runner import run

def install_launchd_service(
    project_dir: Path,
    dry_run: bool,
) -> None:
    """Install a launchd user agent (.plist) to start Frigate and check detector status."""
    log_section("Step E · launchctl Autostart Service")

    home_dir   = Path.home()
    username   = os.environ.get("USER") or Path.home().name
    uid        = os.getuid()

    launch_agents_dir = home_dir / "Library" / "LaunchAgents"
    if not dry_run:
        launch_agents_dir.mkdir(parents=True, exist_ok=True)

    plist_label = "com.frigate.nvr"
    plist_path  = launch_agents_dir / f"{plist_label}.plist"
    script_path = project_dir / "scripts" / "startup.sh"

    if dry_run:
        log_info(f"[dry-run] Would write plist:\n  {plist_path}")
        log_info(f"[dry-run] Would register: gui/{uid} → {plist_label}")
        return

    plist_data: dict = {
        "Label": plist_label,
        "ProgramArguments": ["/bin/zsh", str(script_path)],
        "RunAtLoad": True,
        "KeepAlive": {
            "SuccessfulExit": False,
        },
        "ThrottleInterval": 30,
        "WorkingDirectory": str(project_dir),
        "EnvironmentVariables": {
            "HOME": str(home_dir),
            "USER": username,
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
    }

    with plist_path.open("wb") as fp:
        plistlib.dump(plist_data, fp, fmt=plistlib.FMT_XML)
    log_ok(f"LaunchAgent plist written: {plist_path}")

    log_info("Unloading any existing service instance…")
    run(
        ["launchctl", "bootout", f"gui/{uid}", str(plist_path)],
        check=False,
        dry_run=dry_run,
        timeout=10,
    )

    log_info(f"Bootstrapping service for gui/{uid}…")
    run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],
        dry_run=dry_run,
        timeout=10,
    )

    result = run(
        ["launchctl", "print", f"gui/{uid}/{plist_label}"],
        capture=True,
        check=False,
        dry_run=dry_run,
        timeout=10,
    )
    if result.returncode == 0:
        log_ok(f"Service '{plist_label}' is registered with launchctl.")
        log_info(
            "The service will start automatically on next login.\n"
            f"  Manual start : launchctl kickstart -k gui/{uid}/{plist_label}\n"
            f"  Manual stop  : launchctl kill TERM gui/{uid}/{plist_label}\n"
            f"  View status  : launchctl print gui/{uid}/{plist_label}"
        )
    else:
        log_warn(
            "Service bootstrapped but 'launchctl print' returned non-zero. "
            "This can be normal — verify with:\n"
            f"  launchctl print gui/{uid}/{plist_label}"
        )
