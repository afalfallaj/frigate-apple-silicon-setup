import json
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from .log import log_info, log_ok, log_warn, log_section
from .runner import run, SetupError

DETECTOR_GITHUB_REPO = "frigate-nvr/apple-silicon-detector"
DETECTOR_API_URL = (
    "https://api.github.com/repos/frigate-nvr/apple-silicon-detector/releases"
)

def _fetch_json(url: str) -> Any:
    """Fetch JSON from a URL, returning parsed Python objects."""
    req = urllib.request.Request(url, headers={"User-Agent": "frigate-setup/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def _resolve_detector_tag(requested_tag: str | None, dry_run: bool) -> str:
    """Resolve the detector release tag to use."""
    if requested_tag:
        log_info(f"Using requested detector tag: {requested_tag}")
        return requested_tag

    if dry_run:
        log_info("Dry-run: skipping GitHub API call — returning 'latest'.")
        return "latest"

    log_info(f"Fetching latest release from GitHub: {DETECTOR_API_URL}")
    try:
        releases = _fetch_json(DETECTOR_API_URL)
        if isinstance(releases, list) and releases:
            tag = releases[0]["tag_name"]
            log_ok(f"Latest detector release: {tag}")
            return tag
    except Exception as exc:
        log_warn(f"Could not determine latest tag ({exc}). Falling back to env var.")

    # Fall back to FRIGATE_DETECTOR_TAG env var if set
    tag = os.environ.get("FRIGATE_DETECTOR_TAG", "latest")
    log_info(f"Using fallback tag: {tag}")
    return tag

def download_detector(
    project_dir: Path,
    requested_tag: str | None,
    dry_run: bool,
    force_yes: bool = False,
) -> None:
    """Download (or update) the FrigateDetector.app bundle."""
    log_section("Step B · Apple Silicon Detector")

    tag = _resolve_detector_tag(requested_tag, dry_run)
    app_dest = Path("/Applications/FrigateDetector.app")
    old_app_path = project_dir / "FrigateDetector.app"

    # 1. Warning for old project-level install
    if old_app_path.exists():
        log_warn("Legacy FrigateDetector.app found in project directory.")
        log_warn(f"Path: {old_app_path}")
        log_warn("The detector should now be installed to /Applications/FrigateDetector.app.")

    # 2. Check if already installed in /Applications
    if app_dest.exists() and not force_yes:
        if not sys.stdin.isatty():
            log_info("Non-interactive mode: FrigateDetector.app already exists in /Applications. Skipping.")
            return

        log_info(f"FrigateDetector.app already exists at '{app_dest}'.")
        answer = input("  Re-download / update detector? [y/N] ").strip().lower()
        if answer != "y":
            log_info("Skipping detector update.")
            return
    
    # 3. New Prompt: Ask if user wants auto-install
    if not force_yes:
        log_info("\nThe Apple Silicon Detector is now a standalone macOS app.")
        answer = input("  Do you want us to download and install it to /Applications for you? [Y/n] ").strip().lower()
        if answer == "n":
            log_info("Skipping automatic installation.")
            log_info(f"Please install it manually from: https://github.com/{DETECTOR_GITHUB_REPO}/releases")
            return

    if not dry_run and app_dest.exists():
        # Requires sudo? Usually /Applications is writable by the primary user on Mac if it's not a restricted folder,
        # but let's assume we might need to handle perms. However, shutil.rmtree usually works if owned by user.
        try:
            shutil.rmtree(app_dest)
        except PermissionError:
            log_warn(f"Permission denied removing {app_dest}. Try running with sudo or check permissions.")
            raise SetupError(f"Failed to remove existing app at {app_dest}")

    if dry_run:
        log_info(f"[dry-run] Would download detector tag '{tag}' and install to '{app_dest}'.")
        return

    # Build the release API URL
    if tag == "latest":
        release_api = f"https://api.github.com/repos/{DETECTOR_GITHUB_REPO}/releases/latest"
    else:
        release_api = f"https://api.github.com/repos/{DETECTOR_GITHUB_REPO}/releases/tags/{tag}"

    try:
        log_info(f"Fetching release metadata: {release_api}")
        release_data = _fetch_json(release_api)
    except Exception as exc:
        raise SetupError(f"Failed to fetch detector release metadata: {exc}")

    # Find the best asset (.dmg > .zip > .tar.gz)
    asset_url: str | None = None
    asset_name: str = ""
    assets = release_data.get("assets", [])
    
    for ext in [".dmg", ".zip", ".tar.gz"]:
        for asset in assets:
            name: str = asset.get("name", "")
            if name.endswith(ext):
                asset_url = asset["browser_download_url"]
                asset_name = name
                break
        if asset_url:
            break

    if not asset_url:
        raise SetupError(
            f"No downloadable asset found in release '{tag}'. "
            f"Check: https://github.com/{DETECTOR_GITHUB_REPO}/releases"
        )

    log_ok(f"Found asset: {asset_name}")

    # Stream download
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(asset_name)[1], delete=False) as tmp:
        tmp_path = Path(tmp.name)

    log_info(f"Downloading: {asset_url}")
    try:
        urllib.request.urlretrieve(asset_url, tmp_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise SetupError(f"Download failed: {exc}")

    # Install
    try:
        if asset_name.endswith(".dmg"):
            log_info("Mounting DMG and installing app...")
            mount_res = run(["hdiutil", "attach", str(tmp_path), "-nobrowse", "-plist"], capture=True)
            # Find the mount point
            import plistlib
            plist = plistlib.loads(mount_res.stdout.encode())
            mount_point = None
            for part in plist.get("system-entities", []):
                if "mount-point" in part:
                    mount_point = part["mount-point"]
                    break
            
            if mount_point:
                src_app = list(Path(mount_point).glob("*.app"))
                if src_app:
                    run(["cp", "-R", str(src_app[0]), str(app_dest)])
                    log_ok(f"Copied {src_app[0].name} to /Applications")
                run(["hdiutil", "detach", mount_point])
            else:
                raise SetupError("Could not find mount point for DMG.")
        
        elif asset_name.endswith(".zip"):
            log_info(f"Extracting ZIP to: /Applications")
            run(["unzip", "-q", str(tmp_path), "-d", "/Applications"], timeout=120)
        
        elif asset_name.endswith(".tar.gz"):
            log_info(f"Extracting TAR to: /Applications")
            run(["tar", "-xzf", str(tmp_path), "-C", "/Applications"], timeout=120)

    except Exception as e:
        raise SetupError(f"Installation failed: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    if app_dest.exists():
        log_ok(f"FrigateDetector.app installed at: {app_dest}")
        if not dry_run:
            log_info("Applying Gatekeeper exception to FrigateDetector.app...")
            # Remove quarantine flag if present
            run(["xattr", "-rd", "com.apple.quarantine", str(app_dest)], check=False)
            # Add to spctl (Gatekeeper assessment) as an allowed app
            run(["spctl", "--add", str(app_dest)], check=False)
            
            # Offer to install CLI tool
            detector_bin = app_dest / "Contents" / "MacOS" / "detector"
            if detector_bin.exists():
                log_info("Installing 'detector' CLI symlink to ~/.local/bin/detector...")
                local_bin = Path.home() / ".local" / "bin"
                local_bin.mkdir(parents=True, exist_ok=True)
                cli_link = local_bin / "detector"
                if cli_link.exists() or cli_link.is_symlink():
                    cli_link.unlink()
                cli_link.symlink_to(detector_bin)
                log_ok(f"CLI tool installed: {cli_link}")
    else:
        log_warn(
            "Installation finished but 'FrigateDetector.app' was not found in /Applications. "
            "Please check the download/extraction manually."
        )
