import argparse
import sys
import time
from pathlib import Path

from .log import log_info, log_ok, log_warn, log_error, log_section
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="setup.sh",  # Shows setup.sh in help since it's the entrypoint
        description=(
            "Frigate NVR Apple Silicon Setup Manager\n"
            "Automates Frigate deployment on macOS Apple Silicon (arm64)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--detector-tag", metavar="TAG", default=None, help="Specify a detector release tag (e.g. v1.1.1). Defaults to latest.")
    parser.add_argument("--skip-detector", action="store_true", help="Skip the FrigateDetector download step.")
    parser.add_argument("--skip-model", action="store_true", help="Skip the YOLOv9 model build step.")
    parser.add_argument("--skip-volume", action="store_true", help="Skip NFS Docker volume creation.")
    parser.add_argument("--skip-plist", action="store_true", help="Skip launchctl plist installation.")
    parser.add_argument("--skip-power", action="store_true", help="Skip macOS power settings configuration (requires sudo).")
    parser.add_argument("--dry-run", action="store_true", help="Print all actions without executing them.")
    parser.add_argument("--yes", "-y", action="store_true", help="Answer 'yes' to all prompts (non-interactive mode).")
    parser.add_argument("--status", action="store_true", help="Show the current deployment status and exit.")
    return parser.parse_args()

def show_status(project_dir: Path, env: dict[str, str]) -> None:
    from .runner import run, which
    import os
    
    log_section("Deployment Status")

    # OrbStack
    orb = which("orb")
    log_info(f"OrbStack: {'installed' if orb else 'NOT FOUND'}")

    # Docker
    docker = which("docker")
    if docker:
        result = run(["docker", "compose", "ps", "--format", "json"],
                     capture=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            log_ok("Frigate container: running")
        else:
            log_warn("Frigate container: not running")
    else:
        log_warn("Docker: NOT FOUND")

    # Detector
    detector = project_dir / "FrigateDetector.app"
    log_info(f"Detector app: {'present' if detector.exists() else 'NOT FOUND'}")

    # Model
    model_dir = project_dir / "config" / "model_cache"
    models = list(model_dir.glob("*.onnx")) if model_dir.exists() else []
    log_info(f"ONNX models: {len(models)} found")

    # launchd
    uid = os.getuid()
    result = run(
        ["launchctl", "print", f"gui/{uid}/com.frigate.nvr"],
        capture=True, check=False,
    )
    log_info(f"launchd service: {'registered' if result.returncode == 0 else 'NOT registered'}")

def main() -> int:
    from .env import load_env
    from .runner import SetupError, run, prompt_yes_no
    from .checks import check_apple_silicon, check_container_runtime
    from .detector import download_detector
    from .model import build_yolo_model
    from .storage import create_nfs_volume, configure_docker_compose
    from .launchd import install_launchd_service
    from .power import configure_power_settings, revert_power_settings

    args = parse_args()
    
    project_dir = Path.cwd()
    if not (project_dir / "lib").exists() and (Path(__file__).parent.parent / "lib").exists():
        project_dir = Path(__file__).parent.parent.resolve()
        
    env_path = project_dir / ".env"
    if args.dry_run:
        log_warn("DRY RUN mode: no changes will be made.")

    log_section("Frigate Apple Silicon Setup Manager")
    log_info(f"Project directory: {project_dir}")
    log_info(f"Dry run          : {args.dry_run}")
    log_info(f"Auto-yes         : {args.yes}")

    try:
        env = load_env(env_path)
        log_ok(f".env loaded from: {env_path}")
    except SetupError:
        return 1

    if args.status:
        show_status(project_dir, env)
        return 0

    steps = [
        ("Runtime checks", lambda: check_apple_silicon(args.dry_run)),
        ("Container runtime check", lambda: check_container_runtime(args.dry_run)),
    ]

    if not args.skip_detector:
        steps.append((
            "FrigateDetector download",
            lambda: download_detector(project_dir, args.detector_tag, args.dry_run, args.yes),
        ))

    if not args.skip_model:
        steps.append((
            "YOLOv9 model build",
            lambda: build_yolo_model(project_dir, args.dry_run, args.yes),
        ))

    if not args.skip_volume:
        if prompt_yes_no("\nDo you want to setup an NFS Docker volume for storage?", default=True, auto_yes=args.yes):
            steps.append((
                "NFS Docker volume",
                lambda: create_nfs_volume(env, args.dry_run),
            ))

    steps.append((
        "docker-compose.yaml configuration",
        lambda: configure_docker_compose(project_dir, env, args.dry_run),
    ))

    if not args.skip_plist:
        if prompt_yes_no("\nDo you want to setup a launchctl autostart service?", default=True, auto_yes=args.yes):
            steps.append((
                "launchctl autostart service",
                lambda: install_launchd_service(project_dir, args.dry_run),
            ))

    if not args.skip_power:
        steps.append((
            "macOS power settings",
            lambda: configure_power_settings(args.dry_run),
        ))

    failed = False
    for name, fn in steps:
        try:
            fn()
            log_ok(f"Step '{name}' completed.")
        except SetupError as exc:
            log_error(f"Setup failed at step '{name}': {exc}")
            failed = True
            break
        except KeyboardInterrupt:
            log_warn("Interrupted by user.")
            return 130

    if not failed:
        log_info("\nSetup completed successfully.")
        
        if prompt_yes_no("\nDo you want to start Frigate now?", default=True, auto_yes=args.yes):
            log_section("Starting Applications")
            
            import os
            import subprocess
            uid = os.getuid()
            startup_script = project_dir / "scripts" / "startup.sh"
            
            if not args.skip_plist:
                try:
                    run(["launchctl", "kickstart", "-k", f"gui/{uid}/com.frigate.nvr"], check=True, dry_run=args.dry_run)
                    log_ok(f"Restarted Frigate via launchctl service (gui/{uid}/com.frigate.nvr)")
                except SetupError:
                    log_warn("Failed to kickstart launchctl service.")
            else:
                if startup_script.exists():
                    try:
                        if not args.dry_run:
                            subprocess.Popen(
                                ["/bin/zsh", str(startup_script)],
                                cwd=str(project_dir),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                start_new_session=True
                            )
                        log_ok("Launched scripts/startup.sh in the background.")
                    except Exception as e:
                        log_warn(f"Failed to run startup.sh: {e}")
                else:
                    log_warn("scripts/startup.sh not found!")

        log_info(
            "\nNext steps:\n"
            "  1. Verify Frigate is running: docker compose ps\n"
            "  2. Open the Web UI: http://localhost:8971\n"
            "  3. Check boot log: tail -f boot.log\n"
            "  4. Check detector: tail -f detector.log\n"
        )
        return 0
    else:
        log_error("Setup did NOT complete. Fix the error above and re-run.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
