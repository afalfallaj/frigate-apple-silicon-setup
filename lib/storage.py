import shutil
from pathlib import Path

from .log import log_info, log_ok, log_warn, log_error, log_section
from .runner import run, SetupError

def create_nfs_volume(env: dict[str, str], dry_run: bool) -> None:
    """Create (or recreate) the Docker NFS volume for NFS storage."""
    log_section("Step D1 · NFS Docker Volume")

    nfs_ip = env.get("NFS_IP")
    nfs_share = env.get("NFS_SHARE_PATH")

    if not nfs_ip or not nfs_share:
        log_info("NFS_IP not set in .env. Skipping NFS volume creation (using local storage).")
        return

    log_info(f"NFS target: nfs://{nfs_ip}{nfs_share}")

    # Idempotent: forcefully detach any hung test containers from previous timeouts
    log_info("Cleaning up any hung processes holding the NFS volume...")
    if not dry_run:
        res = run(
            ["docker", "ps", "-a", "--filter", "volume=nfs_storage_volume", "-q"],
            capture=True, check=False
        )
        if res.returncode == 0 and res.stdout.strip():
            for cid in res.stdout.strip().split():
                run(["docker", "rm", "-f", cid], check=False, timeout=10)

    log_info("Removing existing 'nfs_storage_volume' (if present)…")
    run(
        ["docker", "volume", "rm", "nfs_storage_volume"],
        check=False,
        dry_run=dry_run,
        timeout=30,
    )

    # Create the volume with NFS options
    nfs_opts = f"addr={nfs_ip},nfsvers=3,rw,nolock,soft,noatime,noacl"
    run(
        [
            "docker", "volume", "create",
            "--driver", "local",
            "--opt", "type=nfs",
            "--opt", f"o={nfs_opts}",
            "--opt", f"device=:{nfs_share}",
            "nfs_storage_volume",
        ],
        dry_run=dry_run,
        timeout=30,
    )

    # Smoke-test the mount
    log_info("Smoke-testing the NFS mount (pulling alpine image if missing)…")
    try:
        # Increased timeout to 90s to account for potential alpine image pulling on slow networks
        result = run(
            [
                "docker", "run", "--rm",
                "-v", "nfs_storage_volume:/mnt:nocopy",
                "alpine", "touch", "/mnt/.setup_test",
            ],
            capture=True,
            check=False,
            dry_run=dry_run,
            timeout=90,
        )
    except SetupError as e:
        if "timed out" in str(e).lower():
            log_warn("=" * 60)
            log_warn("NFS SERVER CONNECTION TIMEOUT:")
            log_warn(f"  OrbStack could not reach your NFS server at {nfs_ip}.")
            log_warn("  1. Verify the NAS IP address is correct.")
            log_warn("  2. Ensure your NAS allows NFSv3 connections (we use nfsvers=3).")
            log_warn("  3. Check if a firewall is blocking port 2049.")
            log_warn("=" * 60)
        raise e

    if result.returncode == 0:
        log_ok("NFS volume mounted and writable.")
    else:
        output = (result.stderr or result.stdout or "").lower()
        log_error("NFS volume smoke-test failed.")
        if "operation not permitted" in output or "error" in output:
            log_warn("=" * 60)
            log_warn("NFS SERVER PERMISSIONS FIX:")
            log_warn("  Ensure your NFS server maps the Docker user correctly.")
            log_warn("  Configure 'no_root_squash' or map users equivalently.")
            log_warn("=" * 60)
        raise SetupError("NFS volume is misconfigured. See warnings above.")

def configure_docker_compose(
    project_dir: Path,
    env: dict[str, str],
    dry_run: bool,
) -> None:
    """
    Configure docker-compose.yaml for the current environment.
    Copies either docker/template.local.yaml or docker/template.nfs.yaml to
    docker-compose.yaml based on whether an NFS IP is configured.
    """
    log_section("Step D2 · Setup docker-compose.yaml")

    compose_path = project_dir / "docker-compose.yaml"
    nfs_ip = env.get("NFS_IP")

    if nfs_ip:
        source_name = "docker/template.nfs.yaml"
        log_info("  storage mode : NFS Storage")
    else:
        source_name = "docker/template.local.yaml"
        log_info("  storage mode : Local Storage")

    source_path = project_dir / source_name
    if not source_path.exists():
        raise SetupError(f"Docker Compose source file missing: {source_path}")

    if dry_run:
        log_info(f"[dry-run] Would copy {source_name} to docker-compose.yaml")
        return

    shutil.copy2(source_path, compose_path)
    log_ok(f"docker-compose.yaml configured using {source_name}")
