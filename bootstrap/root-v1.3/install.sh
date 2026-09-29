#!/data/data/com.termux/files/usr/bin/sh
set -eu

HOME_DIR=/data/data/com.termux/files/home
PREFIX=/data/data/com.termux/files/usr
GDIR="$HOME_DIR/.g-shaniu"
TMP="$GDIR/bootstrap-v1.3"
ROOT_BASE=/data/adb/g-shaniu

mkdir -p "$TMP" "$GDIR/device" "$GDIR/run" "$GDIR/logs" "$HOME_DIR/.hermes/logs"
touch "$GDIR/maintenance.enabled"

cat > "$GDIR/start-stack.sh" <<'STACK'
#!/data/data/com.termux/files/usr/bin/sh
set -u
HOME_DIR=/data/data/com.termux/files/home
PREFIX=/data/data/com.termux/files/usr
RUN_DIR="$HOME_DIR/.g-shaniu/run"
LOG_DIR="$HOME_DIR/.g-shaniu/logs"
HERMES_VENV="$HOME_DIR/.g-shaniu/hermes-0213-src/venv"

mkdir -p "$RUN_DIR" "$LOG_DIR" "$HOME_DIR/.hermes/logs" "$HOME_DIR/.g-shaniu/device"
export HOME="$HOME_DIR"
export PREFIX
export PATH="$HERMES_VENV/bin:$PREFIX/bin:/system/bin"
export PYTHONPATH="$HOME_DIR/.g-shaniu/hermes-0213-src"

if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock >/dev/null 2>&1 || true
fi

alive_pidfile() {
  PF="$1"
  [ -f "$PF" ] || return 1
  PID="$(cat "$PF" 2>/dev/null)"
  case "$PID" in *[!0-9]*|'') return 1 ;; esac
  kill -0 "$PID" 2>/dev/null
}

start_bg() {
  NAME="$1"
  PF="$RUN_DIR/$NAME.pid"
  shift
  if alive_pidfile "$PF"; then
    return 0
  fi
  rm -f "$PF"
  nohup "$@" >>"$LOG_DIR/$NAME.log" 2>&1 </dev/null &
  echo $! > "$PF"
}

start_bg device-worker "$PREFIX/bin/python3" "$HOME_DIR/.g-shaniu/device/device_worker.py" --loop
start_bg bridge-worker "$PREFIX/bin/python3" "$HOME_DIR/.hermes/scripts/bridge_worker.py" --loop

if [ -x "$HERMES_VENV/bin/hermes" ]; then
  start_bg gateway "$HERMES_VENV/bin/hermes" gateway run
fi

date '+%Y-%m-%d %H:%M:%S stack_start_requested' >> "$LOG_DIR/start-stack.log"
STACK
chmod 0700 "$GDIR/start-stack.sh"

# Maintenance gate for the current live Bridge Worker. Idempotent.
"$PREFIX/bin/python3" - <<'PY'
from pathlib import Path
p=Path.home()/".hermes/scripts/bridge_worker.py"
if not p.exists():
    print("bridge_worker_missing")
    raise SystemExit(0)
s=p.read_text()
if 'maintenance_flag = Path.home() / ".g-shaniu" / "maintenance.enabled"' in s:
    print("maintenance_gate_already_present")
    raise SystemExit(0)
old='''            else:
                try:
                    idle_mod = str(Path.home() / ".g-shaniu" / "shaniu")
                    if idle_mod not in sys.path:
                        sys.path.insert(0, idle_mod)
                    from xhs_idle_loop import run_idle_step
                    idle_result = run_idle_step(claim_was_empty=True)
                    if isinstance(idle_result, dict) and idle_result.get("decision") == "idle_run":
                        idle_sleep = 1.0
                        continue
                except Exception as idle_exc:'''
new='''            else:
                maintenance_flag = Path.home() / ".g-shaniu" / "maintenance.enabled"
                try:
                    if maintenance_flag.exists():
                        idle_result = {"decision": "maintenance_hold"}
                    else:
                        idle_mod = str(Path.home() / ".g-shaniu" / "shaniu")
                        if idle_mod not in sys.path:
                            sys.path.insert(0, idle_mod)
                        from xhs_idle_loop import run_idle_step
                        idle_result = run_idle_step(claim_was_empty=True)
                        if isinstance(idle_result, dict) and idle_result.get("decision") == "idle_run":
                            idle_sleep = 1.0
                            continue
                except Exception as idle_exc:'''
if old not in s:
    print("maintenance_gate_pattern_not_found")
else:
    p.write_text(s.replace(old,new,1))
    print("maintenance_gate_patched")
PY

cat > "$TMP/g-root-service.sh" <<'ROOTSERVICE'
#!/system/bin/sh
BASE=/data/adb/g-shaniu
TERMUX_HOME=/data/data/com.termux/files/home
PREFIX=/data/data/com.termux/files/usr
START_STACK="$TERMUX_HOME/.g-shaniu/start-stack.sh"
LOG="$BASE/logs/service.log"
PATH=/data/adb/magisk:/sbin:/system/bin:/system/xbin
export PATH

log() {
  mkdir -p "$BASE/logs"
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
}

process_alive() {
  NEEDLE="$1"
  for F in /proc/[0-9]*/cmdline; do
    [ -r "$F" ] || continue
    CMD="$(tr '\000' ' ' < "$F" 2>/dev/null)"
    case "$CMD" in *"$NEEDLE"*) return 0 ;; esac
  done
  return 1
}

wait_termux_storage() {
  N=0
  while [ ! -x "$PREFIX/bin/python3" ] || [ ! -x "$START_STACK" ]; do
    N=$((N+1))
    [ "$N" -lt 60 ] || return 1
    sleep 2
  done
  return 0
}

launch_termux_stack() {
  wait_termux_storage || {
    log "termux_storage_not_ready"
    return 1
  }
  URI="com.termux.file://$START_STACK"
  /system/bin/am start-foreground-service \
    -n com.termux/.app.TermuxService \
    -a com.termux.service_execute \
    -d "$URI" \
    --es com.termux.execute.runner app-shell \
    --es com.termux.execute.cwd "$TERMUX_HOME" \
    >/dev/null 2>&1 \
  || /system/bin/am startservice \
    -n com.termux/.app.TermuxService \
    -a com.termux.service_execute \
    -d "$URI" \
    --es com.termux.execute.runner app-shell \
    --es com.termux.execute.cwd "$TERMUX_HOME" \
    >/dev/null 2>&1 \
  || {
    log "termux_service_launch_failed"
    return 1
  }
  log "termux_service_launch_requested"
}

ensure_broker() {
  process_alive 'g-root-broker.sh daemon' && return 0
  "$BASE/bin/g-root-broker.sh" daemon >/dev/null 2>&1 &
  log "broker_started"
}

ensure_shizuku() {
  pidof shizuku_server >/dev/null 2>&1 && return 0
  "$BASE/bin/g-root-broker.sh" --action shizuku.ensure >/dev/null 2>&1 || true
}

ensure_stack() {
  if process_alive 'device_worker.py --loop' && process_alive 'bridge_worker.py --loop'; then
    return 0
  fi
  launch_termux_stack
}

boot_unlock_if_needed() {
  [ -f "$BASE/secrets/unlock_pin" ] || return 1
  log "boot_unlock_attempt"
  "$BASE/bin/g-root-broker.sh" --action unlock >/dev/null 2>&1 || return 1
  log "boot_unlock_ok"
  return 0
}

boot_sequence() {
  until [ "$(getprop sys.boot_completed)" = "1" ]; do sleep 2; done
  sleep 4
  log "root_service_start_v1.3"
  BOOT_UNLOCKED=0
  if boot_unlock_if_needed; then
    BOOT_UNLOCKED=1
    sleep 3
  fi
  ensure_broker
  ensure_shizuku
  ensure_stack
  if [ "$BOOT_UNLOCKED" -eq 1 ]; then
    for _i in 1 2 3 4 5 6 7 8 9 10; do
      if process_alive 'device_worker.py --loop' && process_alive 'bridge_worker.py --loop'; then break; fi
      sleep 2
    done
    input keyevent KEYCODE_HOME >/dev/null 2>&1 || true
    "$BASE/bin/g-root-broker.sh" --action lock >/dev/null 2>&1 || true
    log "boot_relocked"
  fi
}

daemon() {
  boot_sequence
  while true; do
    ensure_broker
    ensure_shizuku
    ensure_stack
    sleep 15
  done
}

case "$1" in
  daemon) daemon ;;
  ensure-stack) ensure_stack ;;
  boot-sequence) boot_sequence ;;
  *) echo "usage: $0 daemon|ensure-stack|boot-sequence" >&2; exit 64 ;;
esac
ROOTSERVICE
chmod 0700 "$TMP/g-root-service.sh"

cat > "$TMP/99-g-shaniu-root-service.sh" <<'ENTRY'
#!/system/bin/sh
/data/adb/g-shaniu/bin/g-root-service.sh daemon >>/data/adb/g-shaniu/logs/service.log 2>&1
ENTRY
chmod 0755 "$TMP/99-g-shaniu-root-service.sh"

echo "[1/4] Checking root..."
su -c id | grep 'uid=0(root)' >/dev/null || { echo "ROOT_CHECK_FAILED"; exit 1; }

echo "[2/4] Installing Root Service v1.3..."
su -c "cp '$TMP/g-root-service.sh' '$ROOT_BASE/bin/g-root-service.sh' && chown 0:0 '$ROOT_BASE/bin/g-root-service.sh' && chmod 0700 '$ROOT_BASE/bin/g-root-service.sh'"
su -c "cp '$TMP/99-g-shaniu-root-service.sh' '/data/adb/service.d/99-g-shaniu-root-service.sh' && chown 0:0 '/data/adb/service.d/99-g-shaniu-root-service.sh' && chmod 0755 '/data/adb/service.d/99-g-shaniu-root-service.sh'"

echo "[3/4] Testing TermuxService bootstrap..."
su -c "$ROOT_BASE/bin/g-root-service.sh ensure-stack" || true
sleep 5

echo "[4/4] Local stack state..."
for PF in "$GDIR/run/device-worker.pid" "$GDIR/run/bridge-worker.pid" "$GDIR/run/gateway.pid"; do
  if [ -f "$PF" ]; then
    P="$(cat "$PF" 2>/dev/null || true)"
    if [ -n "$P" ] && kill -0 "$P" 2>/dev/null; then
      echo "$(basename "$PF" .pid)=RUNNING pid=$P"
    else
      echo "$(basename "$PF" .pid)=NOT_RUNNING"
    fi
  else
    echo "$(basename "$PF" .pid)=NO_PIDFILE"
  fi
done

echo "ROOT_SERVICE_V1_3_INSTALLED"
echo "MAINTENANCE_MODE=ON"
