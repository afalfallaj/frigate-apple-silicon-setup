import sys
from pathlib import Path

from .log import log_info, log_ok, log_warn, log_section
from .runner import run, SetupError

# Model families that can be built. YOLOv9 is the default because its build is
# fully self-contained; YOLO26 exports an Ultralytics checkpoint, which for a
# custom model has to be supplied (see docker/yolo26s/weights/).
_FAMILIES = {
    "yolov9": "YOLOv9  — self-contained, downloads its own weights",
    "yolo26s": "YOLO26  — Ultralytics export, supports custom checkpoints",
}
_DEFAULT_FAMILY = "yolov9"

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

_DEFAULT_YOLO26_MODEL = "yolo26s-objv1-150"


def _prompt_img_size(default_img: int) -> int:
    """Prompt for an input resolution, falling back to default_img."""
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
    return img_size


def _prompt_family(force_yes: bool, preselected: str | None) -> str:
    """Resolve which model family to build."""
    if preselected:
        if preselected not in _FAMILIES:
            raise SetupError(
                f"Unknown model family '{preselected}'. Choose one of: {', '.join(_FAMILIES)}."
            )
        return preselected

    if force_yes or not sys.stdin.isatty():
        log_info(f"Using default model family: {_DEFAULT_FAMILY}")
        return _DEFAULT_FAMILY

    print()
    log_info("Available model families:")
    for key, desc in _FAMILIES.items():
        marker = " (default)" if key == _DEFAULT_FAMILY else ""
        log_info(f"  [{key}]  {desc}{marker}")

    print()
    choice = input(f"  Select model family [{_DEFAULT_FAMILY}]: ").strip().lower()
    if choice and choice not in _FAMILIES:
        log_warn(f"Unknown family '{choice}', falling back to '{_DEFAULT_FAMILY}'.")
    return choice if choice in _FAMILIES else _DEFAULT_FAMILY


def _prompt_yolov9_config(force_yes: bool) -> tuple[str, int]:
    """
    Prompt the user to choose a YOLOv9 model size and image resolution.
    Returns (model_size, img_size).
    """
    default_model = "t"
    default_img = 320

    if force_yes or not sys.stdin.isatty():
        log_info(f"Using default model config: MODEL_SIZE={default_model}, IMG_SIZE={default_img}")
        return default_model, default_img

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

    img_size = _prompt_img_size(default_img)

    print()
    log_ok(f"Model config: MODEL_SIZE={model_size}, IMG_SIZE={img_size}")
    return model_size, img_size


def _prompt_yolo26s_config(force_yes: bool) -> tuple[str, int]:
    """
    Prompt the user to choose a YOLO26 checkpoint name and image resolution.
    Returns (model_name, img_size).
    """
    default_img = 640

    if force_yes or not sys.stdin.isatty():
        log_info(
            f"Using default model config: MODEL_NAME={_DEFAULT_YOLO26_MODEL}, IMG_SIZE={default_img}"
        )
        return _DEFAULT_YOLO26_MODEL, default_img

    print()
    log_info("YOLO26 exports an Ultralytics checkpoint by name (without the .pt suffix).")
    raw = input(f"  Checkpoint name [{_DEFAULT_YOLO26_MODEL}]: ").strip()
    model_name = raw or _DEFAULT_YOLO26_MODEL

    img_size = _prompt_img_size(default_img)

    print()
    log_ok(f"Model config: MODEL_NAME={model_name}, IMG_SIZE={img_size}")
    return model_name, img_size


def build_yolo_model(
    project_dir: Path,
    dry_run: bool,
    force_yes: bool = False,
    family: str | None = None,
) -> None:
    """Build the YOLO ONNX model for the selected family."""
    log_section("Step C · Model Build")

    family = _prompt_family(force_yes, family)
    build_dir = project_dir / "docker" / family
    dockerfile_path = build_dir / "Dockerfile"
    if not dockerfile_path.exists():
        raise SetupError(
            f"Dockerfile not found at '{dockerfile_path}'. "
            f"Ensure docker/{family}/Dockerfile exists before running this step."
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
        log_info(f"Forcing rebuild of {family} ONNX model.")

    # Ask user for model configuration
    if family == "yolov9":
        model_size, img_size = _prompt_yolov9_config(force_yes)
        build_args = ["--build-arg", f"MODEL_SIZE={model_size}"]
        described = f"MODEL_SIZE={model_size}"
    else:
        model_name, img_size = _prompt_yolo26s_config(force_yes)
        build_args = ["--build-arg", f"MODEL_NAME={model_name}"]
        described = f"MODEL_NAME={model_name}"

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    log_info(f"Building {family} ONNX model ({described}, IMG_SIZE={img_size})…")
    log_warn("This step pulls several GB of layers and may take 5–15 minutes.")

    # 30 minute timeout for docker build
    run(
        [
            "docker", "build",
            "-t", f"{family}-onnx",
            *build_args,
            "--build-arg", f"IMG_SIZE={img_size}",
            "-o", str(out_dir),
            "-f", str(dockerfile_path),
            str(build_dir),
        ],
        dry_run=dry_run,
        timeout=1800,
    )
    log_ok(f"Model artifacts written to: {out_dir}")
