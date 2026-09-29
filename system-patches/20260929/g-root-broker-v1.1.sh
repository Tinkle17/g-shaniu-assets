#!/system/bin/sh
# G Root Broker v1.1
# Root-only broker with a fixed action allowlist. No arbitrary shell execution.

BASE=/data/adb/g-shaniu
TERMUX_HOME=/data/data/com.termux/files/home
QUEUE="$TERMUX_HOME/.g-shaniu/root-broker"
REQ="$QUEUE/requests"
RESP="$QUEUE/responses"
SECRET="$BASE/secrets/unlock_pin"
STATE="$BASE/state"
LOG="$BASE/logs/broker.log"

PATH=/data/adb/magisk:/sbin:/system/bin:/system/xbin
export PATH

log() {
  mkdir -p "$BASE/logs"
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
}

termux_ids() {
  TUID="$(stat -c %u /data/data/com.termux 2>/dev/null)"
  TGID="$(stat -c %g /data/data/com.termux 2>/dev/null)"
  [ -n "$TUID" ] && [ -n "$TGID" ]
}

prepare_queue() {
  termux_ids || return 1
  mkdir -p "$REQ" "$RESP" "$STATE"
  chown "$TUID:$TGID" "$QUEUE" "$REQ" "$RESP" 2>/dev/null || true
  chmod 0700 "$QUEUE" "$REQ" "$RESP" 2>/dev/null || true
  chmod 0700 "$BASE" "$BASE/secrets" "$STATE" "$BASE/logs" 2>/dev/null || true
}

keyguard_locked() {
  OUT="$(dumpsys window policy 2>/dev/null; dumpsys window windows 2>/dev/null | grep -E 'mDreamingLockscreen|mShowingLockscreen|isStatusBarKeyguard|showing=' 2>/dev/null)"
  echo "$OUT" | grep -qiE 'mDreamingLockscreen=true|mShowingLockscreen=true|isStatusBarKeyguard=true|showing=true'
}

screen_on() {
  dumpsys power 2>/dev/null | grep -qiE 'mWakefulness=Awake|Display Power: state=ON|mScreenOn=true'
}

unlock_rate_ok() {
  NOW="$(date +%s)"
  FILE="$STATE/unlock_rate"
  START=0
  COUNT=0
  if [ -f "$FILE" ]; then
    read START COUNT < "$FILE" 2>/dev/null || true
  fi
  case "$START:$COUNT" in
    *[!0-9:]*|'') START=0; COUNT=0 ;;
  esac
  if [ "$START" -eq 0 ] || [ $((NOW-START)) -gt 600 ]; then
    START="$NOW"; COUNT=0
  fi
  [ "$COUNT" -lt 5 ] || return 1
  COUNT=$((COUNT+1))
  printf '%s %s\n' "$START" "$COUNT" > "$FILE"
  chmod 0600 "$FILE"
  return 0
}

unlock_rate_reset() {
  printf '%s 0\n' "$(date +%s)" > "$STATE/unlock_rate"
  chmod 0600 "$STATE/unlock_rate"
}

action_status() {
  SPID="$(pidof shizuku_server 2>/dev/null | awk '{print $1}')"
  [ -n "$SPID" ] || SPID=null
  if screen_on; then SCREEN=on; else SCREEN=off; fi
  if keyguard_locked; then LOCKED=true; else LOCKED=false; fi
  if [ -f "$SECRET" ]; then PIN=true; else PIN=false; fi
  printf '{"ok":true,"action":"status","uid":0,"screen":"%s","locked":%s,"pin_configured":%s,"shizuku_pid":%s}\n' "$SCREEN" "$LOCKED" "$PIN" "$SPID"
}

action_wake() {
  input keyevent KEYCODE_WAKEUP >/dev/null 2>&1 || input keyevent 224 >/dev/null 2>&1
  sleep 1
  printf '{"ok":true,"action":"wake"}\n'
}

action_lock() {
  # Prefer an actual policy lock when available; fall back to Android sleep.
  if command -v dpm >/dev/null 2>&1 && dpm help 2>&1 | grep -q 'lock-now'; then
    dpm lock-now >/dev/null 2>&1 || input keyevent KEYCODE_SLEEP >/dev/null 2>&1
  else
    input keyevent KEYCODE_SLEEP >/dev/null 2>&1 || input keyevent 223 >/dev/null 2>&1
  fi
  sleep 1
  if keyguard_locked; then L=true; else L=false; fi
  printf '{"ok":true,"action":"lock","locked":%s}\n' "$L"
}

action_unlock() {
  unlock_rate_ok || {
    printf '{"ok":false,"action":"unlock","error":"rate_limited"}\n'
    return 23
  }

  input keyevent KEYCODE_WAKEUP >/dev/null 2>&1 || input keyevent 224 >/dev/null 2>&1
  sleep 1
  wm dismiss-keyguard >/dev/null 2>&1 || true
  sleep 1

  if ! keyguard_locked; then
    unlock_rate_reset
    printf '{"ok":true,"action":"unlock","method":"dismiss_keyguard"}\n'
    return 0
  fi

  [ -f "$SECRET" ] || {
    printf '{"ok":false,"action":"unlock","error":"pin_not_configured"}\n'
    return 20
  }
  [ ! -L "$SECRET" ] || {
    printf '{"ok":false,"action":"unlock","error":"invalid_secret_file"}\n'
    return 21
  }

  IFS= read -r PIN < "$SECRET"
  case "$PIN" in
    *[!0-9]*|'') unset PIN; printf '{"ok":false,"action":"unlock","error":"invalid_pin_secret"}\n'; return 22 ;;
  esac
  LEN=${#PIN}
  [ "$LEN" -ge 4 ] && [ "$LEN" -le 16 ] || {
    unset PIN
    printf '{"ok":false,"action":"unlock","error":"invalid_pin_length"}\n'
    return 22
  }

  SIZE="$(wm size 2>/dev/null | tail -n 1 | grep -oE '[0-9]+x[0-9]+' | tail -n 1)"
  W="${SIZE%x*}"; H="${SIZE#*x}"
  case "$W:$H" in *[!0-9:]*|:*) W=1080; H=1920 ;; esac
  X=$((W/2)); Y1=$((H*4/5)); Y2=$((H/3))
  input swipe "$X" "$Y1" "$X" "$Y2" 220 >/dev/null 2>&1 || true
  sleep 1

  REST="$PIN"
  while [ -n "$REST" ]; do
    D="${REST%"${REST#?}"}"
    REST="${REST#?}"
    case "$D" in
      0) K=KEYCODE_0;; 1) K=KEYCODE_1;; 2) K=KEYCODE_2;; 3) K=KEYCODE_3;; 4) K=KEYCODE_4;;
      5) K=KEYCODE_5;; 6) K=KEYCODE_6;; 7) K=KEYCODE_7;; 8) K=KEYCODE_8;; 9) K=KEYCODE_9;;
      *) unset PIN REST D; printf '{"ok":false,"action":"unlock","error":"invalid_pin_digit"}\n'; return 22;;
    esac
    input keyevent "$K" >/dev/null 2>&1
  done
  unset PIN REST D K
  input keyevent KEYCODE_ENTER >/dev/null 2>&1
  sleep 2

  if keyguard_locked; then
    printf '{"ok":false,"action":"unlock","error":"keyguard_still_locked"}\n'
    return 24
  fi
  unlock_rate_reset
  printf '{"ok":true,"action":"unlock","method":"local_pin_keyevents"}\n'
}

action_shizuku_ensure() {
  PID="$(pidof shizuku_server 2>/dev/null | awk '{print $1}')"
  if [ -n "$PID" ]; then
    printf '{"ok":true,"action":"shizuku.ensure","already_running":true,"pid":%s}\n' "$PID"
    return 0
  fi

  # This is the same root flow used by Shizuku's own "Start via root" UI.
  # It was verified on this MI6 and avoids depending on APK native-lib layout.
  am start -W \
    -n moe.shizuku.privileged.api/moe.shizuku.manager.starter.StarterActivity \
    --ez moe.shizuku.manager.extra.IS_ROOT true >/dev/null 2>&1 || true

  for _i in 1 2 3 4 5; do
    sleep 1
    PID="$(pidof shizuku_server 2>/dev/null | awk '{print $1}')"
    [ -n "$PID" ] && break
  done

  [ -n "$PID" ] || {
    printf '{"ok":false,"action":"shizuku.ensure","error":"root_activity_start_failed"}\n'
    return 32
  }
  printf '{"ok":true,"action":"shizuku.ensure","mode":"root_activity","already_running":false,"pid":%s}\n' "$PID"
}

action_stack_ensure() {
  "$BASE/bin/g-root-service.sh" ensure-stack >/dev/null 2>&1 || true
  printf '{"ok":true,"action":"stack.ensure"}\n'
}

run_action() {
  case "$1" in
    status) action_status ;;
    wake) action_wake ;;
    lock) action_lock ;;
    unlock) action_unlock ;;
    shizuku.ensure) action_shizuku_ensure ;;
    stack.ensure) action_stack_ensure ;;
    *) printf '{"ok":false,"error":"action_not_allowed"}\n'; return 64 ;;
  esac
}

daemon() {
  prepare_queue || exit 1
  log "broker_start"
  while true; do
    for F in "$REQ"/*; do
      [ -e "$F" ] || break
      [ -f "$F" ] || { rm -f "$F"; continue; }
      [ ! -L "$F" ] || { rm -f "$F"; continue; }

      ID="${F##*/}"
      case "$ID" in *[!A-Za-z0-9._-]*|'') rm -f "$F"; continue ;; esac
      ACTION="$(head -n 1 "$F" 2>/dev/null | tr -d '\r\n')"
      rm -f "$F"

      termux_ids || continue
      DEST="$RESP/$ID"
      TMP="$RESP/.tmp.$.$ID"
      rm -f "$TMP" "$DEST"
      run_action "$ACTION" > "$TMP" 2>/dev/null
      RC=$?
      if [ ! -s "$TMP" ]; then
        printf '{"ok":false,"error":"empty_response","code":%s}\n' "$RC" > "$TMP"
      fi
      chown "$TUID:$TGID" "$TMP" 2>/dev/null || true
      chmod 0600 "$TMP" 2>/dev/null || true
      mv "$TMP" "$DEST"
      chown "$TUID:$TGID" "$DEST" 2>/dev/null || true
      chmod 0600 "$DEST" 2>/dev/null || true
    done
    sleep 0.25
  done
}

case "$1" in
  daemon) daemon ;;
  --action) run_action "$2" ;;
  *) echo "usage: $0 daemon | --action {status|wake|lock|unlock|shizuku.ensure|stack.ensure}" >&2; exit 64 ;;
esac
