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

    app_dest = project_dir / "FrigateDetector.app"
    if app_dest.exists() and not force_yes:
        if not sys.stdin.isatty():
            log_info("Non-interactive mode: FrigateDetector.app already exists. Skipping download.")
            return
            
        log_info(f"FrigateDetector.app already exists at '{app_dest}'.")
        answer = input(
            "  Re-download / update detector? [y/N] "
        ).strip().lower()
        if answer != "y":
            log_info("Skipping detector download.")
            return
    elif app_dest.exists():
        log_info("Forcing re-download of detector.")

    if not dry_run and app_dest.exists():
        shutil.rmtree(app_dest)

    if dry_run:
        log_info(f"[dry-run] Would download detector tag '{tag}' to '{app_dest}'.")
        return

    # Build the release API URL
    if tag == "latest":
        release_api = (
            f"https://api.github.com/repos/{DETECTOR_GITHUB_REPO}/releases/latest"
        )
    else:
        release_api = (
            f"https://api.github.com/repos/{DETECTOR_GITHUB_REPO}/releases/tags/{tag}"
        )

    try:
        log_info(f"Fetching release metadata: {release_api}")
        release_data = _fetch_json(release_api)
    except Exception as exc:
        raise SetupError(f"Failed to fetch detector release metadata: {exc}")

    # Find the first .tar.gz or .zip asset
    asset_url: str | None = None
    for asset in release_data.get("assets", []):
        name: str = asset.get("name", "")
        if name.endswith(".tar.gz") or name.endswith(".zip"):
            asset_url = asset["browser_download_url"]
            log_ok(f"Found asset: {name}")
            break

    if not asset_url:
        raise SetupError(
            f"No downloadable asset found in release '{tag}'. "
            f"Check: https://github.com/{DETECTOR_GITHUB_REPO}/releases"
        )

    # Stream download
    with tempfile.NamedTemporaryFile(suffix=".download", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    log_info(f"Downloading: {asset_url}")
    try:
        urllib.request.urlretrieve(asset_url, tmp_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise SetupError(f"Download failed: {exc}")

    # Extract
    log_info(f"Extracting to: {project_dir}")
    try:
        if asset_url.endswith(".tar.gz"):
            run(["tar", "-xzf", str(tmp_path), "-C", str(project_dir)], dry_run=dry_run, timeout=120)
        else:
            run(["unzip", "-q", str(tmp_path), "-d", str(project_dir)], dry_run=dry_run, timeout=120)
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
    else:
        log_warn(
            "Archive extracted but 'FrigateDetector.app' directory was not found. "
            "The archive may have a different layout — please inspect manually."
        )
