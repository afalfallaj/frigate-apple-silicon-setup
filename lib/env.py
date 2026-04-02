from pathlib import Path
from .log import log_info, log_error, log_warn
from .runner import SetupError

REQUIRED_ENV_KEYS = ["LOCAL_CONFIG_DIR", "LOCAL_DB_DIR", "FRIGATE_VERSION_TAG"]

def load_env(env_path: Path) -> dict[str, str]:
    """
    Parse a KEY=VALUE .env file.
    Ignores blank lines and lines starting with '#'.
    Strips surrounding quotes from values.
    """
    env: dict[str, str] = {}
    if not env_path.exists():
        log_error(f".env file not found at '{env_path}'.")
        log_error("Copy .env.example to .env and fill in your values:")
        log_error("  cp .env.example .env && $EDITOR .env")
        raise SetupError(".env missing")

    _check_env_permissions(env_path)

    for line_num, line in enumerate(env_path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            log_warn(f".env line {line_num}: no '=' found, skipping: {line!r}")
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes (single or double)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key] = value
        
    validate_env(env)
    return env

def _check_env_permissions(env_path: Path) -> None:
    """Warn if .env has overly permissive file permissions."""
    try:
        mode = env_path.stat().st_mode
        if mode & 0o077:  # group or other has any access
            log_warn(
                f".env has permissive mode {oct(mode)[-3:]}. "
                f"Consider: chmod 600 {env_path}"
            )
            try:
                env_path.chmod(0o600)
                log_info(f".env permissions automatically set to 600 (owner read/write only)")
            except Exception as exc:
                log_warn(f"Failed to automatically chmod .env: {exc}")
    except Exception as exc:
        log_warn(f"Could not check .env permissions: {exc}")

def validate_env(env: dict[str, str]) -> list[str]:
    missing = [k for k in REQUIRED_ENV_KEYS if k not in env]
    if missing:
        msg = f"Missing required .env keys: {', '.join(missing)}"
        log_error(msg)
        log_error("Ensure you copied all keys from .env.example and filled them in.")
        raise SetupError(msg)
    return missing
