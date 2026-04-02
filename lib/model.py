import sys
from pathlib import Path

from .log import log_info, log_ok, log_warn, log_section
from .runner import run, SetupError

# Available YOLOv9 model variants (weight → description)
_MODEL_SIZES = {
    "t": "Tiny   — fastest, lowest accuracy (~2 MB)",
    "s": "Small  — balanced speed/accuracy   (~7 MB)",
    "m": "Medium — good accuracy, slower     (~20 MB)",
    "c": "Compact — high accuracy            (~25 MB)",
    "e": "Extended — highest accuracy, slowest (~57 MB)",
}

# Common image input resolutions
_IMG_SIZES = [320, 416, 512, 640]


def _prompt_model_config(force_yes: bool) -> tuple[str, int]:
    """
    Prompt the user to choose a YOLOv9 model size and image resolution.
    Returns (model_size, img_size).
    """
    # Defaults
    default_model = "t"
    default_img = 320

    if force_yes or not sys.stdin.isatty():
        log_info(f"Using default model config: MODEL_SIZE={default_model}, IMG_SIZE={default_img}")
        return default_model, default_img

    # ── Model size ────────────────────────────────────────────────────────────
    print()
    log_info("Available YOLOv9 model sizes:")
    for key, desc in _MODEL_SIZES.items():
        marker = " (default)" if key == default_model else ""
        log_info(f"  [{key}]  {desc}{marker}")

    print()
    choice = input(f"  Select model size [{default_model}]: ").strip().lower()
    model_size = choice if choice in _MODEL_SIZES else default_model
    if choice and choice not in _MODEL_SIZES:
        log_warn(f"Unknown model '{choice}', falling back to '{default_model}'.")

    # ── Image resolution ──────────────────────────────────────────────────────
    print()
    log_info("Available image input sizes (pixels):")
    for size in _IMG_SIZES:
        marker = " (default)" if size == default_img else ""
        log_info(f"  [{size}]{marker}")

    print()
    raw = input(f"  Select image size [{default_img}]: ").strip()
    try:
        img_size = int(raw) if raw else default_img
        if img_size not in _IMG_SIZES:
            log_warn(f"Non-standard image size {img_size}. Supported: {_IMG_SIZES}.")
            confirm = input(f"  Use {img_size} anyway? [y/N] ").strip().lower()
            if confirm != "y":
                img_size = default_img
                log_info(f"Falling back to {default_img}.")
    except ValueError:
        log_warn(f"Invalid input '{raw}', falling back to {default_img}.")
        img_size = default_img

    print()
    log_ok(f"Model config: MODEL_SIZE={model_size}, IMG_SIZE={img_size}")
    return model_size, img_size


def build_yolo_model(
    project_dir: Path,
    dry_run: bool,
    force_yes: bool = False,
) -> None:
    """Build the YOLOv9 ONNX model."""
    log_section("Step C · YOLOv9 Model Build")

    dockerfile_path = project_dir / "docker" / "yolov9" / "Dockerfile"
    if not dockerfile_path.exists():
        raise SetupError(
            f"YOLOv9 Dockerfile not found at '{dockerfile_path}'. "
            "Ensure docker/yolov9/Dockerfile exists before running this step."
        )

    out_dir = project_dir / "config" / "model_cache"
    onnx_files = list(out_dir.glob("*.onnx")) if out_dir.exists() else []

    if onnx_files and not force_yes:
        if not sys.stdin.isatty():
            log_info("Non-interactive mode: ONNX model already exists. Skipping build.")
            return

        log_info(
            f"Existing ONNX model(s) found in '{out_dir}':\n"
            + "\n".join(f"    - {f.name}" for f in onnx_files)
        )
        answer = input("  Rebuild model? (this can take 5–15 min) [y/N] ").strip().lower()
        if answer != "y":
            log_info("Skipping model build.")
            return
    elif onnx_files:
        log_info("Forcing rebuild of YOLOv9 ONNX model.")

    # Ask user for model configuration
    model_size, img_size = _prompt_model_config(force_yes)

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    log_info(f"Building YOLOv9 ONNX model (MODEL_SIZE={model_size}, IMG_SIZE={img_size})…")
    log_warn("This step pulls several GB of layers and may take 5–15 minutes.")

    # 30 minute timeout for docker build
    run(
        [
            "docker", "build",
            "-t", "yolov9-onnx",
            "--build-arg", f"MODEL_SIZE={model_size}",
            "--build-arg", f"IMG_SIZE={img_size}",
            "-o", str(out_dir),
            "-f", str(dockerfile_path),
            str(project_dir / "docker" / "yolov9"),
        ],
        dry_run=dry_run,
        timeout=1800,
    )
    log_ok(f"Model artifacts written to: {out_dir}")
