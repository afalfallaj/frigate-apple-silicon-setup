import platform
from .log import log_info, log_ok, log_warn, log_section
from .runner import run, which, SetupError

def check_apple_silicon(dry_run: bool) -> None:
    """Assert that we are running on macOS arm64 and have Rosetta 2."""
    log_section("Step A · Runtime Checks")
    system = platform.system()
    machine = platform.machine()
    log_info(f"Detected: {system} / {machine}")

    if system != "Darwin":
        raise SetupError(f"This script targets macOS only (detected: {system})")

    if machine != "arm64" and not dry_run:
        log_warn(
            "Expected arm64 (Apple Silicon) but detected '%s'. "
            "Some features (NPU detector, arm64 image) may not work." % machine
        )
    else:
        log_ok("Apple Silicon (arm64) confirmed.")
        
        # Check Rosetta 2 (OrbStack needs it for x86 container support)
        if not dry_run:
            try:
                run(["arch", "-x86_64", "/usr/bin/true"], capture=True, check=True)
            except SetupError:
                log_warn("Rosetta 2 missing. It's required by OrbStack to run x86 layer containers.")
                log_info("Installing Rosetta 2 (you may be prompted for sudo password)...")
                run(["sudo", "softwareupdate", "--install-rosetta", "--agree-to-license"], check=False)

def check_container_runtime(dry_run: bool) -> str:
    """
    Detect Docker / OrbStack.

    Returns:
        'orbstack' | 'docker-desktop' | 'docker-unknown' | 'none'
    """
    docker_bin = which("docker")
    orb_bin = which("orb")

    if not docker_bin and not orb_bin:
        log_warn("No container runtime found.")
        log_warn(
            "OrbStack is strongly recommended on Apple Silicon for performance:\n"
            "  brew install orbstack\n"
            "  open -a OrbStack\n"
            "  orb start"
        )
        if not dry_run:
            raise SetupError(
                "Install OrbStack (or Docker) and re-run setup.sh."
            )
        return "none"

    import time
    if orb_bin:
        log_info("Disabling OrbStack admin GUI prompts for headless compatibility...")
        run([orb_bin, "config", "set", "setup.use_admin", "false"], check=False, dry_run=dry_run)
        
        log_info("Ensuring OrbStack daemon is running...")
        res_orb = run([orb_bin, "start"], check=False, dry_run=dry_run, timeout=30)
        
        if not dry_run and res_orb.returncode != 0:
            msg = (
                "OrbStack 'orb start' failed!\n"
                "Please launch OrbStack manually to ensure it is installed correctly and accept any permissions."
            )
            raise SetupError(msg)
        
        if not dry_run:
            log_info("Waiting for Docker daemon to become available...")
            docker_ready = False
            # Re-resolve docker_bin inside the loop because 'orb start' might have just symlinked it
            for _ in range(60):
                d_bin = which("docker")
                if not d_bin:
                    # Fallback to the binary nestled directly inside the app bundle if symlinks failed
                    fallback = "/Applications/OrbStack.app/Contents/MacOS/bin/docker"
                    if __import__("os").path.exists(fallback):
                        d_bin = fallback

                if d_bin:
                    docker_bin = d_bin  # Update the outer scope variable
                    res = run([d_bin, "info"], capture=True, check=False, timeout=5)
                    if res.returncode == 0:
                        docker_ready = True
                        break
                time.sleep(2)
            
            if not docker_ready:
                raise SetupError("Docker daemon did not become ready within 120 seconds. Is OrbStack stuck?")

    # Probe Docker context to determine the backend
    if docker_bin:
        try:
            ctx = run(
                ["docker", "context", "show"],
                capture=True, check=False, dry_run=dry_run, timeout=10
            )
            context_name = ctx.stdout.strip().lower()
        except Exception:
            context_name = ""

        if orb_bin or "orbstack" in context_name or "orb" in context_name:
            log_ok("Container runtime: OrbStack ✓")
            return "orbstack"

        # Docker Desktop is present but OrbStack is not
        log_warn("Docker Desktop detected.")
        log_warn(
            "⚠️  Recommendation: Switch to OrbStack for better Apple Silicon "
            "performance (lower CPU/RAM, native arm64 virtualisation):\n"
            "  brew install orbstack"
        )
        return "docker-desktop"

    # orb binary exists but docker might not yet be symlinked
    log_ok("OrbStack detected via 'orb' binary.")
    return "orbstack"
