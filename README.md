# Frigate NVR — Apple Silicon Setup

> **Headless-compatible, one-command deployment of [Frigate NVR](https://frigate.video/) on macOS Apple Silicon (M1/M2/M3/M4).**

---

## Overview

This repository provides an automated `setup.sh` script that wires together:

| Component | Role |
|---|---|
| **OrbStack** | Docker runtime optimised for Apple Silicon |
| **FrigateDetector** | NPU-accelerated object detection (Apple Neural Engine) |
| **YOLOv9 ONNX** | Custom model built for Frigate |
| **NFS Server** | NFS-mounted media storage volume |
| **launchctl** | macOS service manager — starts Frigate on boot |

---

## Why this project?

Setting up a highly performant NVR like Frigate natively on macOS Apple Silicon is traditionally complex. It requires navigating headless NPU acceleration, exporting YOLO models to CoreML configurations, isolating Python virtual environments, dealing with Docker's filesystem performance on macOS, and properly persisting network storage mounts.

This project was built to completely eliminate that complexity. 

By wrapping the entire deployment into a reliable, idempotent Python backend, you get a **seamless, plug-and-play setup experience**. Run one command, and the script handles the Docker runtime, builds the specific ONNX ML models optimized for your chip, attaches the Apple Neural Engine detector, and automatically hooks it into the native macOS boot sequence (`launchctl`). It's designed so you can forget about the underlying infrastructure and just enjoy a robust Frigate instance.

---

## Prerequisites

Before running the setup script, ensure you have a container runtime installed:
- **OrbStack** (Container runtime, highly recommended over Docker Desktop for native Apple Silicon virtualization). 
  - Download and install from [orbstack.dev](https://orbstack.dev/).
  - **Important:** Launch the app once and complete any macOS Gatekeeper/permissions prompts before running the script.

`setup.sh` will automatically download these system dependencies if missing:
- **Homebrew**
- **Python 3.11+**

> **Docker Desktop users:** OrbStack uses significantly less CPU/RAM and its arm64 virtualisation is native — it is strongly recommended on Apple Silicon.

---

## Quick Start

> [!WARNING]
> **Protected Folders & macOS TCC**
> Do **not** install this setup inside `~/Desktop`, `~/Documents`, or `~/Downloads`. macOS Transparency, Consent, and Control (TCC) gatekeeper will silently block the background `launchd` service from reading configurations in these directories.
> 
> **Recommended Installation Paths:** Keep the setup inside your home folder but outside of protected directories. For example: `~/frigate` or `~/services/frigate`. Do not use system root paths (`/opt` or `/services`) as macOS Read-Only system volumes strictly forbid it without overriding SIP.

```bash
# 1. Clone the repo to a safe user directory (e.g. ~/services/frigate)
mkdir -p ~/services
cd ~/services
git clone https://github.com/afalfallaj/frigate-apple-silicon-setup.git frigate
cd frigate

# 2. Configure your environment
cp .env.example .env
$EDITOR .env          # Fill in NFS_IP, NFS_SHARE_PATH, etc.

# 3. Run the setup (interactive prompts for rebuild/re-download)
./setup.sh
```

That's it. Frigate will now start automatically on every login/boot.

---

## Setup Script Reference

```
./setup.sh [OPTIONS]

Options:
  --detector-tag TAG   Pin a specific detector release (e.g. v1.1.1).
                       Defaults to the latest GitHub release.
  --skip-detector      Skip FrigateDetector download.
  --skip-model         Skip YOLOv9 ONNX model build (slow, ~5–15 min).
  --skip-volume        Skip NFS Docker volume creation.
  --skip-plist         Skip launchctl service installation.
  --skip-power         Skip macOS power settings configuration (requires sudo).
  --dry-run            Print all actions without executing them.
  --yes, -y            Answer 'yes' to all prompts (non-interactive mode).
  --verbose, -v        Show verbose output.
  --status             Show the current deployment status and exit.
```

### What `setup.sh` does — step by step

| Step | Action |
|---|---|
| **A · Runtime Checks** | Validates macOS arm64, Homebrew, Homebrew Python, and detects Docker runtime (recommends OrbStack). |
| **B · Detector** | Downloads `FrigateDetector.app` from GitHub Releases (latest or pinned tag). Skips if already present (prompts to update). |
| **C · YOLOv9 Model** | Runs `docker build` on `docker/yolov9/Dockerfile` to produce a YOLOv9-t ONNX model at `config/model_cache/`. Skips if outputs exist (prompts to rebuild). |
| **D1 · NFS Volume** | Creates (or recreates) the `nfs_storage_volume` Docker volume from `.env` values. Smoke-tests the mount. |
| **D2 · Compose** | Regenerates `docker-compose.yaml` with dynamic paths sourced from `.env` using `docker/template.*.yaml`. |
| **E · launchctl** | Writes `start_frigate.sh`, installs `~/Library/LaunchAgents/com.frigate.nvr.plist`, and bootstraps the service for the current user. |
| **F · Power Config** | Configures macOS server power settings (prevent sleep, wake on LAN, auto-restart). |

The script is **idempotent** — safe to re-run at any time.

---

## Configuration (`.env`)

Copy `.env.example` to `.env` and set all values. The `.env` file is **git-ignored** and never committed.

```dotenv
# Media Storage (Leave NFS_IP blank for local SSD storage)
LOCAL_MEDIA_DIR=./media
NFS_IP=192.168.1.x
NFS_SHARE_PATH=/volume1/frigate_media

# Frigate image tag
FRIGATE_VERSION_TAG=stable-standard-arm64

# Local path for Frigate config files
LOCAL_CONFIG_DIR=./config

# RTSP credentials (consumed by Frigate internally)
FRIGATE_RTSP_USER=viewer
FRIGATE_RTSP_PASSWORD=changeme
```

---

## Repository Structure

```
.
├── setup.sh                  ← Main entrypoint script (start here)
├── lib/                      ← Python backend logic
├── .env.example              ← Template — copy to .env
├── .gitignore
│
├── docker-compose.yaml       ← Auto-patched by setup.sh (Step D2)
├── docker/
│   ├── yolov9/
│   │   └── Dockerfile        ← Multi-stage build → YOLOv9 ONNX + labelmap
│   ├── template.local.yaml   ← Local Storage template
│   └── template.nfs.yaml     ← NFS Storage template
├── scripts/
│   ├── startup.sh            ← Boot script
│   └── headless_detector.sh  ← Detector launcher
│
├── config/
│   ├── config.yaml           ← Your Frigate configuration (16-camera setup)
│   └── config-example.yaml   ← Reference config
```

> **`FrigateDetector.app/`** is downloaded by `setup.sh` and excluded from git.

---

## Managing the Service

After `setup.sh` completes, use standard `launchctl` commands:

```bash
# Check status
launchctl print gui/$(id -u)/com.frigate.nvr

# Start immediately (without waiting for reboot)
launchctl kickstart -k gui/$(id -u)/com.frigate.nvr

# Stop
launchctl kill TERM gui/$(id -u)/com.frigate.nvr

# Remove from autostart
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.frigate.nvr.plist
```

---

## Logs

| File | Contents |
|---|---|
| `~/Library/Logs/FrigateNVR/boot.log` | OrbStack + Docker Compose startup output |
| `~/Library/Logs/FrigateNVR/detector.log` | FrigateDetector Python core output |

```bash
tail -f ~/Library/Logs/FrigateNVR/boot.log        # Watch the boot sequence
tail -f ~/Library/Logs/FrigateNVR/detector.log    # Watch the NPU detector
```

---

## NFS — Permissions Note

If the NFS volume smoke-test fails with "operation not permitted", ensure your NFS server is configured to map users correctly (e.g. `no_root_squash` or `all_squash` mapped to a valid ID).
Then re-run: `./setup.sh --skip-detector --skip-model --skip-plist`

---

## Troubleshooting

### Frigate UI unreachable after boot
Check `boot.log` — OrbStack may not have finished starting before Docker was polled.
The start script retries for 120 seconds; if that's insufficient on your machine,
increase the loop count in `startup.sh`.

### Detector not detecting
Check `detector.log`. Ensure `FrigateDetector.app` is present and that the inner
`venv/` was created successfully during the app's first launch.

### Re-running individual steps
```bash
./setup.sh --skip-model --skip-volume   # Re-download detector only
./setup.sh --skip-detector --skip-model # Re-create volume + patch compose
./setup.sh --skip-detector --skip-model --skip-volume  # Re-install plist only
```

---

## Acknowledgments

Special thanks to [NickM-27/apple-silicon-detector](https://github.com/frigate-nvr/apple-silicon-detector) for providing the underlying NPU-accelerated CoreML detector implementation that this setup manager orchestrates.

---

## License

MIT — see `LICENSE`.
