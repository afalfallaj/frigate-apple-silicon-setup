#!/usr/bin/env bash
# Storage- and stream-aware healthcheck for the frigate container.
#
# The NFS media share is not mounted on macOS -- it is mounted inside the OrbStack
# VM by Docker's local volume driver, and that mount is refcounted: it is torn down
# when the last container using it stops. A container restart is therefore also a
# remount, and a remount is the only thing that clears the stale NFSv4 handles an NFS
# server reboot leaves behind. This script decides when that restart is warranted; the
# autoheal sidecar in docker-compose.yaml is what performs it.
#
# Exit 0 = healthy. Exit 1 = restart me.

set -uo pipefail

MEDIA_DIR=/media/frigate
# State, log and API locations can be overridden so the script can be tested without
# touching the real restart budget or the live container.
STATE_FILE=${STATE_FILE:-/config/.healthcheck_state}      # local SSD, so it survives an NFS outage
FORCE_UNHEALTHY=${FORCE_UNHEALTHY:-/config/.force_unhealthy}   # test hook, see README
API=${API:-https://127.0.0.1:8971}
NFS_PORT=2049
DETECTOR_HOST=host.docker.internal
DETECTOR_PORT=5555
IO_TIMEOUT=10
# retries=3 in the compose healthcheck means ~3 verdicts per restart cycle,
# so this budget allows roughly 4 cycles per hour before we give up.
MAX_VERDICTS_PER_HOUR=12
# Must match start_period in docker-compose.yaml. Docker suppresses restarts for
# this long after a start, so verdicts inside the window are not actionable.
STARTUP_GRACE=180
# Last time any camera reported a completed inference (epoch seconds).
DETECT_OK_FILE=${DETECT_OK_FILE:-/config/.healthcheck_detect_ok}
# How long detection may sit at zero, with cameras live, before we call it wedged.
# Quiet scenes legitimately produce no detections for long stretches, so the limit is
# deliberately generous.
DETECT_STALL_LIMIT=${DETECT_STALL_LIMIT:-1800}
# Check 3b only runs once the container is this old. Camera processors need ~150 s to
# come up, and the cache backlog left by the previous run logs "Too many unprocessed
# segments" warnings and serves stale frames until they do.
PIPELINE_GRACE=${PIPELINE_GRACE:-300}
# Frigate's log, from the s6 logger (tmpfs, reset on every container start).
LOG_FILE=${LOG_FILE:-/dev/shm/logs/frigate/current}
# Why each unhealthy verdict was given. STATE_FILE only keeps timestamps, and the
# reason is otherwise lost when autoheal restarts the container.
VERDICT_LOG=${VERDICT_LOG:-/config/.healthcheck_verdicts.log}

log() { echo "$(date '+%F %T') $*"; }

# Pure-bash TCP probe -- the image has no nc.
tcp_ok() { timeout 3 bash -c "exec 3<>/dev/tcp/$1/$2" 2>/dev/null; }

# Age of this container in seconds: /proc/1/stat field 22 is PID 1's start time in
# clock ticks since VM boot, and /proc/uptime is that same VM's uptime.
container_age() {
  local ticks hz up
  ticks=$(awk '{print $22}' /proc/1/stat 2>/dev/null) || return 1
  hz=$(getconf CLK_TCK 2>/dev/null) || return 1
  up=$(awk '{print int($1)}' /proc/uptime 2>/dev/null) || return 1
  [ -n "$ticks" ] && [ -n "$hz" ] && [ -n "$up" ] || return 1
  echo $(( up - ticks / hz ))
}

starting_up() {
  local age
  age=$(container_age) || return 1   # unknown age: assume fully started
  [ "$age" -lt "$STARTUP_GRACE" ]
}

# Record an unhealthy verdict and return 1, unless the hourly budget is spent -- at
# that point restarting is demonstrably not fixing anything, so we stay up serving
# live view rather than crash-looping, and say so loudly.
unhealthy() {
  local now cutoff count=0
  # Docker ignores failures inside start_period, so a verdict there can never
  # cause a restart -- charging it against the budget would let a normal start
  # exhaust the allowance and suppress a genuine recovery later.
  if starting_up; then
    log "UNHEALTHY (within startup grace, not counted): $1"
    return 1
  fi
  now=$(date +%s)
  cutoff=$((now - 3600))
  if [ -f "$STATE_FILE" ]; then
    if awk -v c="$cutoff" '$1 > c' "$STATE_FILE" > "$STATE_FILE.tmp" 2>/dev/null; then
      mv -f "$STATE_FILE.tmp" "$STATE_FILE"
    fi
    count=$(wc -l < "$STATE_FILE" 2>/dev/null | tr -d ' ')
    [ -n "$count" ] || count=0
  fi
  echo "$now" >> "$STATE_FILE" 2>/dev/null
  echo "$(date '+%F %T') $1" >> "$VERDICT_LOG" 2>/dev/null
  if [ "$(wc -l < "$VERDICT_LOG" 2>/dev/null || echo 0)" -gt 500 ]; then
    tail -n 200 "$VERDICT_LOG" > "$VERDICT_LOG.tmp" 2>/dev/null && mv -f "$VERDICT_LOG.tmp" "$VERDICT_LOG"
  fi

  if [ "$count" -ge "$MAX_VERDICTS_PER_HOUR" ]; then
    log "CRITICAL: $1"
    log "CRITICAL: ${count} unhealthy verdicts in the past hour -- restarting is not resolving this. Staying up; manual attention needed."
    return 0
  fi
  log "UNHEALTHY: $1"
  return 1
}

# 0. Test hook: lets us verify the autoheal wiring without breaking anything real.
if [ -f "$FORCE_UNHEALTHY" ]; then
  unhealthy "$FORCE_UNHEALTHY is present (test hook)"; exit $?
fi

# 1. Is Frigate answering at all? Any HTTP status counts as alive -- with auth
#    enabled (the Frigate default) /api/version returns 401, and nginx returning
#    401 still proves the stack is up. Treating that as a failure would restart-
#    loop every default install. Only a connection failure/timeout ("000") is down.
http_code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 10 "$API/api/version" 2>/dev/null)
if [ -z "$http_code" ] || [ "$http_code" = "000" ]; then
  unhealthy "Frigate API not responding on $API"; exit $?
fi

# 2. Storage: prove the media mount can be written and read back. This is what
#    catches ESTALE/EIO/a hung mount -- none of which the API notices, which is
#    exactly why the old curl-only healthcheck reported healthy through an outage.
if ! timeout "$IO_TIMEOUT" bash -c \
     "date +%s > '$MEDIA_DIR/.healthz' && cat '$MEDIA_DIR/.healthz' >/dev/null && { [ ! -d '$MEDIA_DIR/recordings' ] || ls '$MEDIA_DIR/recordings' >/dev/null; }" 2>/dev/null; then
  # Only a restart-remount fixes a stale mount, and only once the NFS server is
  # actually back. While it is down a restart cannot help, so report healthy and
  # wait -- otherwise we would restart-loop for the entire outage. When the server
  # returns, this check flips to unhealthy on the next pass and recovery is automatic.
  if [ -n "${NFS_IP:-}" ] && ! tcp_ok "$NFS_IP" "$NFS_PORT"; then
    log "WAITING: $MEDIA_DIR unwritable and NFS server $NFS_IP:$NFS_PORT is unreachable -- server is down, a restart would not help."
    exit 0
  fi
  unhealthy "$MEDIA_DIR unwritable while the NFS server is reachable -- stale NFS mount; a restart will remount it"
  exit $?
fi

# 3. Streams: every camera at zero fps means go2rtc/ffmpeg is wedged. A single
#    camera at zero is nearly always camera-side, so it is logged, not acted on.
stream_state=$(timeout 15 python3 - "$API" <<'PY' 2>/dev/null
import json, subprocess, sys

out = subprocess.run(["curl", "-sk", "-w", "\n%{http_code}", "--max-time", "10",
                      sys.argv[1] + "/api/stats"], capture_output=True, text=True)
if out.returncode != 0:
    print("UNKNOWN stats request failed"); raise SystemExit(0)
body, _, code = out.stdout.rpartition("\n")
if code != "200":
    # 401 here just means auth is enabled; it is not a health signal.
    print("UNKNOWN stats returned HTTP %s -- stream check unavailable" % code)
    raise SystemExit(0)
try:
    cameras = json.loads(body).get("cameras") or {}
except ValueError:
    print("UNKNOWN stats response was not JSON"); raise SystemExit(0)
if not cameras:
    print("UNKNOWN no cameras reported"); raise SystemExit(0)

dead = sorted(name for name, c in cameras.items() if not (c.get("camera_fps") or 0))
if len(dead) == len(cameras):
    print("ALL_DEAD all %d cameras at 0 fps" % len(cameras))
elif dead:
    print("SOME_DEAD " + ", ".join(dead))
else:
    print("OK")

# Second line, consumed by check 5: total inferences/sec, and how many cameras are
# both producing frames and have detection enabled (i.e. could be feeding the detector).
live = {n: c for n, c in cameras.items() if (c.get("camera_fps") or 0) and c.get("detection_enabled")}
print("DETECT %.1f %d" % (sum(c.get("detection_fps") or 0 for c in cameras.values()), len(live)))
# Third line, consumed by check 3b: the same live cameras, by name.
print("LIVE " + " ".join(sorted(live)))
PY
)
live_cams=$(printf '%s\n' "$stream_state" | sed -n '3p')
detect_state=$(printf '%s\n' "$stream_state" | sed -n '2p')
stream_state=$(printf '%s\n' "$stream_state" | sed -n '1p')
case "$stream_state" in
  ALL_DEAD*)
    # Frigate answers the API before the cameras produce their first frames, so
    # this is normal for the first minute or so of a cold start.
    if starting_up; then
      log "STARTING: ${stream_state#ALL_DEAD } -- cameras still coming up"
      exit 0
    fi
    unhealthy "${stream_state#ALL_DEAD } -- go2rtc/ffmpeg wedged"; exit $? ;;
  SOME_DEAD*) log "WARN: camera(s) at 0 fps: ${stream_state#SOME_DEAD } -- likely camera-side, not restarting" ;;
  UNKNOWN*)   log "WARN: stream check inconclusive (${stream_state#UNKNOWN })" ;;
esac

# 3b. Frigate's event pipeline. One thread (detected_frames_processor) turns camera
#     frames into every recording, event, review item and alert, and nothing restarts
#     it when an uncaught exception kills it. Frigate 0.18.x has an upstream race that
#     does exactly that when a browser socket closes in the middle of a websocket
#     broadcast (ws4py raises RuntimeError or OSError out of comms/ws.py): the container
#     stays up, cameras keep their fps, the detector keeps answering, and the record
#     maintainer discards every cached segment. Only a restart revives the thread. This
#     check detects the dead thread and restarts; it cannot prevent the race itself.
#     Two independent signals, neither of which needs a recording to exist:
#       - the "Exception in thread" line Python logs when a thread dies, and
#       - stale frames: /latest.webp sets X-Frigate-Offline once a camera's newest
#         processed frame is older than its retry_interval, which a dead thread makes
#         true for every camera at once. Cameras that are really offline are at 0 fps
#         and are not probed.
#     Runs before check 4 so it is not skipped while the host detector is down.
if age=$(container_age) && [ "$age" -ge "$PIPELINE_GRACE" ]; then
  dead_thread=$(grep -m1 -o 'Exception in thread [^:]*' "$LOG_FILE" 2>/dev/null)
  if [ -n "$dead_thread" ]; then
    unhealthy "Frigate thread died (${dead_thread#Exception in thread }) -- nothing restarts it, so recording, events and alerts are down; a restart will clear it"
    exit $?
  fi
  read -ra probe_cams <<< "${live_cams#LIVE}"
  if [ "${#probe_cams[@]}" -gt 0 ]; then
    fresh_state=$(timeout 20 python3 - "$API" "${probe_cams[@]}" <<'PY' 2>/dev/null
import concurrent.futures as cf, ssl, sys, urllib.request

api, cams = sys.argv[1], sys.argv[2:]
ctx = ssl._create_unverified_context()

def probe(cam):
    try:
        r = urllib.request.urlopen("%s/api/%s/latest.webp?height=10" % (api, cam), timeout=5, context=ctx)
        r.read()
        return cam, str(r.headers.get("X-Frigate-Offline", "")).lower() == "true"
    except Exception:
        return cam, None            # the request failed: no evidence either way

with cf.ThreadPoolExecutor(max_workers=8) as ex:
    results = list(ex.map(probe, cams))
answered = [(c, off) for c, off in results if off is not None]
stale = sorted(c for c, off in answered if off)
if not cams or len(answered) < min(3, len(cams)):
    print("UNKNOWN only %d of %d probes answered" % (len(answered), len(cams)))
elif len(stale) * 10 >= len(answered) * 7:
    print("STALE %d of %d" % (len(stale), len(answered)))
elif stale:
    print("SOME_STALE " + ", ".join(stale))
else:
    print("OK %d" % len(answered))
PY
)
    case "$fresh_state" in
      STALE*)      unhealthy "frames stale on ${fresh_state#STALE } live cameras (X-Frigate-Offline) -- event pipeline wedged, so recording, events and alerts are down; a restart will clear it"; exit $? ;;
      SOME_STALE*) log "WARN: stale frames on ${fresh_state#SOME_STALE } -- likely camera-side, not restarting" ;;
      UNKNOWN*)    log "WARN: frame freshness check inconclusive (${fresh_state#UNKNOWN })" ;;
    esac
    [ -z "${HEALTHCHECK_DEBUG:-}" ] || log "DEBUG: pipeline ${fresh_state:-no result}"
  fi
fi

# 4. The detector runs on the macOS host under launchd. Nothing in Docker can
#    restart it, and recording continues without it -- so this is reported, never
#    acted on. Restarting frigate here would only cost recordings for no gain.
if ! tcp_ok "$DETECTOR_HOST" "$DETECTOR_PORT"; then
  log "WARN: detector endpoint $DETECTOR_HOST:$DETECTOR_PORT unreachable -- object detection is stopped (recording unaffected). Restart FrigateDetector.app on the host."
  exit 0
fi

# 5. Detection wedged inside Frigate. When Frigate's watchdog force-kills a stuck
#    detection process while the queue is empty, the kill leaks the queue's read
#    lock and the replacement process never receives a frame: cameras keep their
#    fps, the detector port stays open, and nothing is ever detected again. Only a
#    Frigate restart clears it. detection_fps counts real detector replies only, so
#    a sustained zero across every live camera is the signature. (With the detector
#    app down the plugin answers with empty results, which still count -- so this
#    never fires for a problem a restart cannot fix.)
if [ -n "$detect_state" ]; then
  read -r _ detect_fps detect_live <<< "$detect_state"
  now=$(date +%s)
  if [ "${detect_live:-0}" -eq 0 ] || [ "${detect_fps%.*}" -gt 0 ] || [ "${detect_fps#*.}" != "0" ]; then
    # Detecting, or no camera is feeding the detector: (re)start the clock.
    echo "$now" > "$DETECT_OK_FILE" 2>/dev/null
  else
    last_ok=$(cat "$DETECT_OK_FILE" 2>/dev/null)
    case "$last_ok" in ''|*[!0-9]*) last_ok=$now; echo "$now" > "$DETECT_OK_FILE" 2>/dev/null ;; esac
    # Never count time from before this container started.
    if age=$(container_age) && [ "$last_ok" -lt $(( now - age )) ]; then
      last_ok=$(( now - age ))
    fi
    stalled=$(( now - last_ok ))
    if [ "$stalled" -ge "$DETECT_STALL_LIMIT" ]; then
      unhealthy "no detections for $((stalled / 60)) min while $detect_live camera(s) are live -- detection process wedged; a restart will clear it"
      exit $?
    fi
  fi
fi

exit 0
