#!/usr/bin/env bash
# Copyright 2026 Nebius BV. SPDX-License-Identifier: Apache-2.0
# Adapted from nebius/nebius-ps-services, commit a1d6ef7a0192072cf541891c78d3460a1b86a5e7.
# Child-only auth sanitization intentionally does not change parent state.
# shellcheck disable=SC2030,SC2031
set -euo pipefail

umask 077
# Default failure also covers fatal parameter expansion on the system Bash.
exit_status=1
script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
deadline_pid=""
deadline_process_started_at=""
loaded_observed_at=""
refresh_after_seconds=""

active_tmp_file=""
refresh_lock_dir=""
refresh_lock_inode=""
refresh_lock_owner_pid=""
refresh_lock_process_started_at=""
mcp_pid=""
mcp_process_started_at=""
mcp_group_id=""
refresher_pid=""
refresher_process_started_at=""
worker_timer_pid=""
refresh_worker_stop_status=""
refresh_worker_stopped_mcp="false"
refresh_reason_file=""
generation_file=""

usage() {
  cat <<'USAGE'
Run Grafana MCP for Nebius-managed Grafana with a pinned human Nebius profile.

The profile and identity binding must be created by the bundled setup helper.
Every token mint revalidates that the pinned profile still resolves to the
expected human user. Ambient agent credentials and competing Grafana
credentials are ignored.

Required environment:
  NEBIUS_GRAFANA_AGENT
      Client binding created by setup: codex or claude.
  NEBIUS_GRAFANA_USER_PROFILE
      Pinned human Nebius CLI profile.
  NEBIUS_GRAFANA_IDENTITY_FILE
      Private mode-0600 profile/user binding created by the setup helper.
  GRAFANA_TOKEN_FILE
      Private profile-scoped token file in the same mode-0700 state directory.
  GRAFANA_URL
      Must equal the origin.json binding created by bundled setup.
  NEBIUS_GRAFANA_MCP_BINARY
      Verified physical path of the official Grafana MCP executable.
  NEBIUS_GRAFANA_BINARY_RECEIPT
      Private binary provenance receipt created by setup.

Optional environment:
  NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS
      Maximum delay before background renewal. Defaults to 36000 seconds and
      must not exceed 36000; renewal is capped at ten hours after observation.
  NEBIUS_GRAFANA_TOKEN_REFRESH_RETRY_SECONDS
      Three retry delays. Defaults to "60 300 900".
  NEBIUS_GRAFANA_LOCK_WAIT_SECONDS
      Maximum wait for another live refresh during MCP startup or background
      renewal. Defaults to 90 seconds; allowed range is 1-120.
  NEBIUS_GRAFANA_STARTUP_LOCK_WAIT_SECONDS
      Maximum wait for another live refresh during bundled setup
      (--refresh-token-only). Defaults to 210 seconds; allowed range is 1-240.
Usage:
  run-nebius-grafana-mcp.sh [canonical mcp-grafana args]
  run-nebius-grafana-mcp.sh --refresh-token-only
USAGE
}

finish() {
  exit_status="$1"
  exit "$1"
}

die() {
  printf 'error: %s\n' "$*" >&2
  finish 1
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'error: required command not found on PATH: %s\n' "$1" >&2
    finish 127
  fi
}

cleanup_refresh_artifacts() {
  if [ -n "$active_tmp_file" ]; then
    rm -f -- "$active_tmp_file"
    active_tmp_file=""
  fi
  if [ -n "$refresh_lock_dir" ]; then
    if [ "$(file_inode "$refresh_lock_dir" 2>/dev/null || true)" = "$refresh_lock_inode" ] \
      && [ "$(sed -n 's/^pid=//p' "${refresh_lock_dir}/owner" 2>/dev/null | head -n 1 || true)" = "$refresh_lock_owner_pid" ] \
      && [ "$(sed -n 's/^process_started_at=//p' "${refresh_lock_dir}/owner" 2>/dev/null | head -n 1 || true)" = "$refresh_lock_process_started_at" ]; then
      rm -f -- "${refresh_lock_dir}/owner"
      rmdir -- "$refresh_lock_dir" 2>/dev/null || true
    fi
    refresh_lock_dir=""
    refresh_lock_inode=""
    refresh_lock_owner_pid=""
    refresh_lock_process_started_at=""
  fi
}

write_refresh_exit_reason() {
  local reason="$1"

  case "$reason" in
    rotation-required | refresh-exhausted | refresh-worker-failed | credential-deadline | deadline-worker-failed) ;;
    *) return 1 ;;
  esac
  [ -n "$refresh_reason_file" ] || return 1
  printf '%s\n' "$reason" >"$refresh_reason_file"
}

process_state() {
  ps -o stat= -p "$1" 2>/dev/null \
    | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//'
}

process_is_live_instance() {
  local pid="$1"
  local expected_started_at="$2"
  local current_started_at=""
  local state=""

  [ -n "$pid" ] && [ -n "$expected_started_at" ] || return 1
  current_started_at="$(process_started_at "$pid" 2>/dev/null || true)"
  [ "$current_started_at" = "$expected_started_at" ] || return 1
  state="$(process_state "$pid" || true)"
  case "$state" in
    '' | Z*) return 1 ;;
  esac
}

process_is_stopped_instance() {
  local pid="$1"
  local expected_started_at="$2"
  local current_started_at=""
  local state=""

  [ -n "$pid" ] && [ -n "$expected_started_at" ] || return 1
  current_started_at="$(process_started_at "$pid" 2>/dev/null || true)"
  [ "$current_started_at" = "$expected_started_at" ] || return 1
  state="$(process_state "$pid" || true)"
  case "$state" in
    T*) return 0 ;;
    *) return 1 ;;
  esac
}

kill_owned_mcp_group() {
  # Captured only after the bridge creates a private session. Group cleanup
  # also reaches the stock MCP if the bridge has already exited unexpectedly.
  if [ -n "$mcp_group_id" ] && [ "$mcp_group_id" = "$mcp_pid" ]; then
    kill -KILL -- "-$mcp_group_id" >/dev/null 2>&1 || true
  fi
}

stop_owned_mcp_from_parent() {
  local waited=0
  local stopped_group=""

  process_is_live_instance "$mcp_pid" "$mcp_process_started_at" || return 1

  # A successful TERM is ambiguous when the child exits naturally just before
  # delivery: an unreaped zombie can still accept kill(2) without receiving the
  # signal. STOP cannot be handled or ignored, so first observe this exact child
  # in the stopped state. Once acknowledged, it cannot exit naturally before
  # the parent sends KILL. Because this is an unreaped direct child, its PID
  # cannot be reused before wait; after STOP succeeds, every path can safely
  # issue KILL without another fallible process-table lookup.
  kill -STOP "$mcp_pid" >/dev/null 2>&1 || return 1
  while [ "$waited" -lt 50 ]; do
    if process_is_stopped_instance "$mcp_pid" "$mcp_process_started_at"; then
      # If startup timed out, capture a group created just before STOP. The
      # stopped bridge cannot launch a child or change groups during cleanup.
      stopped_group="$(ps -o pgid= -p "$mcp_pid" 2>/dev/null | tr -d '[:space:]' || true)"
      if [ "$stopped_group" = "$mcp_pid" ]; then
        mcp_group_id="$stopped_group"
      fi
      kill_owned_mcp_group
      kill -KILL "$mcp_pid" >/dev/null 2>&1 || {
        kill -CONT "$mcp_pid" >/dev/null 2>&1 || true
        return 1
      }
      return 0
    fi

    if ! process_is_live_instance "$mcp_pid" "$mcp_process_started_at"; then
      kill -KILL "$mcp_pid" >/dev/null 2>&1 || true
      return 1
    fi
    sleep 0.1
    waited=$((waited + 1))
  done

  # A hidden or unsupported stopped-state report must not strand the child.
  # KILL is safe here because the direct child remains unreaped and therefore
  # retains the PID whose identity was checked before STOP.
  kill -KILL "$mcp_pid" >/dev/null 2>&1 || {
    kill -CONT "$mcp_pid" >/dev/null 2>&1 || true
  }
  return 1
}

# shellcheck disable=SC2329  # Invoked by worker EXIT/INT/TERM traps.
cleanup_worker_timer() {
  if [ -n "$worker_timer_pid" ]; then
    kill "$worker_timer_pid" >/dev/null 2>&1 || true
    wait "$worker_timer_pid" >/dev/null 2>&1 || true
    worker_timer_pid=""
  fi
}

# shellcheck disable=SC2329  # Invoked by refresh worker INT/TERM traps.
request_refresh_worker_stop() {
  refresh_worker_stop_status="$1"
  cleanup_worker_timer
}

exit_if_refresh_worker_stop_requested() {
  if [ -n "$refresh_worker_stop_status" ]; then
    exit "$refresh_worker_stop_status"
  fi
}

# shellcheck disable=SC2329  # Invoked by the refresh worker EXIT trap.
cleanup_refresh_worker() {
  local status="$?"

  trap - EXIT INT TERM
  cleanup_worker_timer
  cleanup_refresh_artifacts
  if [ "$status" -ne 0 ] \
    && [ "$status" -ne 130 ] \
    && [ "$status" -ne 143 ] \
    && [ "$refresh_worker_stopped_mcp" != "true" ]; then
    printf 'error: token refresh worker failed unexpectedly; stopping MCP at the operational limit\n' >&2
    write_refresh_exit_reason "refresh-worker-failed" || true
  fi
  return "$status"
}

wait_for_worker_timer() {
  local seconds="$1"
  local status=0

  sleep "$seconds" &
  worker_timer_pid="$!"
  wait "$worker_timer_pid" || status="$?"
  worker_timer_pid=""
  return "$status"
}

# shellcheck disable=SC2329  # Invoked by EXIT/INT/TERM traps.
cleanup() {
  trap - EXIT INT TERM
  # Signal every owned child before waiting for either one. In particular, the
  # MCP child may already be stopped and must be killed before a delayed or
  # stopped refresher can block its own reap path.
  if [ -n "$mcp_pid" ]; then
    # Cancellation can arrive before startup records the group. Kill the
    # bridge first so it cannot spawn again, then its private group (if it
    # exists). This is still our unreaped direct child's PID, so it cannot
    # name an unrelated process group through PID reuse.
    kill -KILL "$mcp_pid" >/dev/null 2>&1 || true
    kill -KILL -- "-$mcp_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$refresher_pid" ]; then
    # A stopped worker cannot handle TERM until continued. Its timer trap and
    # every foreground Nebius CLI call are already bounded, so cooperative
    # shutdown reaches the EXIT trap that owns exact lock/temp cleanup.
    kill -CONT "$refresher_pid" >/dev/null 2>&1 || true
    kill "$refresher_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$mcp_pid" ]; then
    wait "$mcp_pid" >/dev/null 2>&1 || true
    mcp_pid=""
  fi
  if [ -n "$refresher_pid" ]; then
    wait "$refresher_pid" >/dev/null 2>&1 || true
    refresher_pid=""
  fi
  if [ -n "$deadline_pid" ]; then
    # This is an unreaped direct child; KILL also handles a stopped watchdog.
    kill -KILL "$deadline_pid" >/dev/null 2>&1 || true
    wait "$deadline_pid" >/dev/null 2>&1 || true
    deadline_pid=""
  fi
  cleanup_refresh_artifacts
  if [ -n "$generation_file" ]; then
    rm -f -- "$generation_file"
    generation_file=""
  fi
  if [ -n "$refresh_reason_file" ]; then
    rm -f -- "$refresh_reason_file"
    refresh_reason_file=""
  fi
  exit "$exit_status"
}

trap cleanup EXIT
trap 'finish 130' INT
trap 'finish 143' TERM

file_stat() {
  local value
  # GNU stat can emit filesystem data before rejecting BSD format arguments.
  # Only forward stdout from a successful dialect invocation.
  if value="$(stat -f "$1" "$3" 2>/dev/null)"; then
    printf '%s\n' "$value"
  else
    stat -c "$2" "$3"
  fi
}

file_mode() {
  file_stat '%OLp' '%a' "$1"
}

file_uid() {
  file_stat '%u' '%u' "$1"
}

file_inode() {
  file_stat '%i' '%i' "$1"
}

file_mtime_epoch() {
  file_stat '%m' '%Y' "$1"
}

process_started_at() {
  ps -o lstart= -p "$1" 2>/dev/null \
    | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//'
}

validate_profile_name() {
  local profile="$1"

  case "$profile" in
    codex-agent-*)
      die "NEBIUS_GRAFANA_USER_PROFILE must be a human profile, not an agent profile"
      ;;
  esac
  if [[ ! "$profile" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$ ]]; then
    die "NEBIUS_GRAFANA_USER_PROFILE contains unsupported characters"
  fi
}

validate_positive_integer() {
  local name="$1"
  local value="$2"
  local maximum="$3"

  case "$value" in
    '' | *[!0-9]*)
      die "$name must be a positive integer no greater than $maximum"
      ;;
  esac
  if [ "$value" -le 0 ] || [ "$value" -gt "$maximum" ]; then
    die "$name must be a positive integer no greater than $maximum"
  fi
}

validate_retry_delays() {
  local count=0
  local delay
  local total=0

  for delay in $NEBIUS_GRAFANA_TOKEN_REFRESH_RETRY_SECONDS; do
    case "$delay" in
      '' | *[!0-9]*)
        die "NEBIUS_GRAFANA_TOKEN_REFRESH_RETRY_SECONDS must contain three non-negative integers"
        ;;
    esac
    if [ "$delay" -gt 3600 ]; then
      die "each token refresh retry delay must be no greater than 3600 seconds"
    fi
    total=$((total + 10#$delay))
    count=$((count + 1))
  done
  if [ "$count" -ne 3 ]; then
    die "NEBIUS_GRAFANA_TOKEN_REFRESH_RETRY_SECONDS must contain exactly three delays"
  fi
  if [ "$total" -gt 3600 ]; then
    die "token refresh retry delays must total no more than 3600 seconds"
  fi
}

validate_nebius_grafana_url() {
  python3 -B "$script_dir/runtime_check.py" \
    || die "runtime origin, paths or provenance failed validation"
}

validate_normalized_absolute_path() {
  local label="$1"
  local path="$2"
  local normalized

  case "$path" in
    /*) ;;
    *) die "$label must be an absolute path" ;;
  esac
  if [[ "$path" =~ [[:cntrl:]] ]]; then
    die "$label contains control characters"
  fi
  normalized="$(
    python3 -B -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$path"
  )"
  [ "$path" = "$normalized" ] \
    || die "$label must be lexically normalized without dot segments"
}

validate_private_state_dir() {
  local state_dir="$1"

  python3 -B - "$state_dir" "${HOME:?HOME is required}" <<'PY'
import os
import stat
import sys

state_dir = os.path.abspath(sys.argv[1])
home = os.path.abspath(sys.argv[2])
try:
    if os.path.commonpath((state_dir, home)) != home or state_dir == home:
        raise ValueError
except ValueError:
    raise SystemExit(2)

relative = os.path.relpath(state_dir, home)
current = home
for part in relative.split(os.sep):
    current = os.path.join(current, part)
    try:
        info = os.lstat(current)
    except OSError:
        raise SystemExit(6)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise SystemExit(3)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise SystemExit(4)

try:
    leaf_mode = stat.S_IMODE(os.lstat(state_dir).st_mode)
except OSError:
    raise SystemExit(6)
if leaf_mode != 0o700:
    raise SystemExit(5)
PY
}

validate_private_file() {
  local path="$1"

  [ -L "$path" ] && die "private state file must not be a symlink: $path"
  [ -f "$path" ] || die "private state file is missing or not regular: $path"
  [ "$(file_uid "$path")" = "$(id -u)" ] \
    || die "private state file is not owned by the current user: $path"
  [ "$(file_mode "$path")" = "600" ] \
    || die "private state file must have mode 0600: $path"
}

validate_state_paths() {
  local identity_dir
  local token_dir

  validate_normalized_absolute_path \
    "NEBIUS_GRAFANA_IDENTITY_FILE" \
    "$NEBIUS_GRAFANA_IDENTITY_FILE"
  validate_normalized_absolute_path "GRAFANA_TOKEN_FILE" "$GRAFANA_TOKEN_FILE"

  identity_dir="$(dirname -- "$NEBIUS_GRAFANA_IDENTITY_FILE")"
  token_dir="$(dirname -- "$GRAFANA_TOKEN_FILE")"
  [ "$identity_dir" = "$token_dir" ] \
    || die "identity and token files must share one profile-scoped state directory"
  [ "$(basename -- "$NEBIUS_GRAFANA_IDENTITY_FILE")" = "identity" ] \
    || die "NEBIUS_GRAFANA_IDENTITY_FILE must use the canonical identity filename"
  [ "$(basename -- "$GRAFANA_TOKEN_FILE")" = "iam-token" ] \
    || die "GRAFANA_TOKEN_FILE must use the canonical token filename"
  [ "$(basename -- "$token_dir")" = "$NEBIUS_GRAFANA_USER_PROFILE" ] \
    || die "profile-scoped state directory must end with the pinned profile name"

  validate_private_state_dir "$token_dir" \
    || die "profile-scoped state directory is unsafe; require an owned non-symlink mode-0700 path below HOME"
  validate_private_file "$NEBIUS_GRAFANA_IDENTITY_FILE"
  if [ -e "$GRAFANA_TOKEN_FILE" ] || [ -L "$GRAFANA_TOKEN_FILE" ]; then
    validate_private_file "$GRAFANA_TOKEN_FILE"
  fi
}

read_identity_binding() {
  local line_count

  line_count="$(awk 'END { print NR }' "$NEBIUS_GRAFANA_IDENTITY_FILE")"
  [ "$line_count" = "3" ] || die "identity binding has an unsupported format"

  binding_version="$(sed -n 's/^version=//p' "$NEBIUS_GRAFANA_IDENTITY_FILE")"
  binding_profile="$(sed -n 's/^profile=//p' "$NEBIUS_GRAFANA_IDENTITY_FILE")"
  binding_user_id="$(sed -n 's/^user_id=//p' "$NEBIUS_GRAFANA_IDENTITY_FILE")"

  [ "$binding_version" = "1" ] || die "identity binding version is unsupported"
  [ "$binding_profile" = "$NEBIUS_GRAFANA_USER_PROFILE" ] \
    || die "identity binding profile does not match NEBIUS_GRAFANA_USER_PROFILE"
  if [[ ! "$binding_user_id" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$ ]]; then
    die "identity binding contains an invalid user ID"
  fi
}

run_nebius_clean() (
  local variable
  local harness_agent="${AI_AGENT:-${NEBIUS_GRAFANA_AGENT}}"
  while IFS= read -r variable; do
    case "$variable" in
      NEBIUS_* | GRAFANA_* | CODEX_NEBIUS_* | TOKEN | IAM_TOKEN) unset "$variable" ;;
    esac
  done < <(compgen -e)
  export AI_AGENT="$harness_agent"
  # CLI diagnostics can contain credentials or browser login URLs.
  nebius "$@" 2>/dev/null
)

run_nebius_browser_auth() {
  run_nebius_clean "$@"
}

resolve_profile_user_id() {
  local auth_mode="${1:-noninteractive}"
  local -a auth_args=(
    --no-browser
    --auth-timeout 10s
    --timeout 20s
    --retries 1
  )
  local identity_json
  local user_id

  case "$auth_mode" in
    interactive)
      auth_args=(
        --auth-timeout 120s
        --timeout 20s
        --retries 1
      )
      ;;
    noninteractive) ;;
    *)
      die "unsupported Nebius authentication mode"
      ;;
  esac

  if [ "$auth_mode" = "interactive" ]; then
    if ! identity_json="$(
      run_nebius_browser_auth iam whoami \
        --profile "$NEBIUS_GRAFANA_USER_PROFILE" \
        --format json \
        "${auth_args[@]}" </dev/null
    )"; then
      printf 'error: pinned Nebius profile could not be validated after browser authentication\n' >&2
      return 1
    fi
  elif ! identity_json="$(
    run_nebius_clean iam whoami \
      --profile "$NEBIUS_GRAFANA_USER_PROFILE" \
      --format json \
      "${auth_args[@]}" </dev/null 2>/dev/null
  )"; then
    printf 'error: pinned Nebius profile could not be validated non-interactively\n' >&2
    return 1
  fi

  if ! user_id="$(
    printf '%s' "$identity_json" \
      | python3 -B -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except (TypeError, ValueError):
    raise SystemExit(2)

user = payload.get("user_profile")
if not isinstance(user, dict):
    raise SystemExit(3)
if "service_account_profile" in payload or "anonymous_profile" in payload:
    raise SystemExit(4)
user_id = user.get("id")
if not isinstance(user_id, str) or not user_id:
    raise SystemExit(5)
print(user_id)
'
  )"; then
    printf 'error: pinned Nebius profile is not a validated human user profile\n' >&2
    return 1
  fi

  printf '%s\n' "$user_id"
}

validate_identity_binding() {
  local auth_mode="${1:-noninteractive}"
  local actual_user_id

  actual_user_id="$(resolve_profile_user_id "$auth_mode")" || return 1
  if [ "$actual_user_id" != "$binding_user_id" ]; then
    printf 'error: pinned Nebius profile identity changed; create a distinct human profile and rerun setup\n' >&2
    return 1
  fi
}

validate_token_contents() {
  python3 -B - "$script_dir" "$1" <<'PYCODE'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from token_state import token_bytes
try:
    token_bytes(Path(sys.argv[2]))
except Exception:
    raise SystemExit(1)
PYCODE
}

token_file_is_fresh() {
  python3 -B "$script_dir/token_state.py" inspect "$GRAFANA_TOKEN_FILE" >/dev/null 2>&1
}

refresh_token() {
  local observation_started_at=""
  local auth_mode="${1:-noninteractive}"
  local -a auth_args=(
    --no-browser
    --auth-timeout 10s
    --timeout 20s
    --retries 1
  )
  local lock_dir="${GRAFANA_TOKEN_FILE}.lock"
  local lock_owner_file="${lock_dir}/owner"
  local lock_inode=""
  local lock_uid=""
  local lock_mode=""
  local lock_mtime=""
  local lock_age=0
  local writer_pid=""
  local writer_started_at=""
  local owner_file_inode=""
  local owner_file_uid=""
  local owner_file_mode=""
  local owner_version=""
  local owner_pid=""
  local owner_started_at=""
  local owner_process_started_at=""
  local current_process_started_at=""
  local metadata_valid="false"
  local now_epoch=""
  local token_inode_before=""
  local token_inode_after=""
  local waited=0
  local lock_wait_seconds="$NEBIUS_GRAFANA_LOCK_WAIT_SECONDS"

  case "$auth_mode" in
    interactive)
      lock_wait_seconds="$NEBIUS_GRAFANA_STARTUP_LOCK_WAIT_SECONDS"
      ;;
    noninteractive) ;;
    *)
      die "unsupported Nebius authentication mode"
      ;;
  esac

  exit_if_refresh_worker_stop_requested
  # exec replaces the command-substitution child, so its parent is this
  # writer's Bash process even when refresh runs in a background subshell.
  # Resolve identity before acquiring a lock; PID discovery creates no files.
  writer_pid="$(exec python3 -B -c 'import os; print(os.getppid())' 2>/dev/null)" \
    || die "unable to identify token refresh lock owner process"
  [[ "$writer_pid" =~ ^[0-9]+$ ]] \
    || die "token refresh lock owner PID is invalid"
  writer_started_at="$(process_started_at "$writer_pid")"
  [ -n "$writer_started_at" ] \
    || die "unable to identify token refresh lock owner process"
  exit_if_refresh_worker_stop_requested
  if [ -f "$GRAFANA_TOKEN_FILE" ] && [ ! -L "$GRAFANA_TOKEN_FILE" ]; then
    token_inode_before="$(file_inode "$GRAFANA_TOKEN_FILE")"
  fi

  while :; do
    exit_if_refresh_worker_stop_requested
    if mkdir -- "$lock_dir" 2>/dev/null; then
      lock_inode="$(file_inode "$lock_dir")"
      refresh_lock_dir="$lock_dir"
      refresh_lock_inode="$lock_inode"
      exit_if_refresh_worker_stop_requested
      break
    fi
    if [ -L "$lock_dir" ]; then
      [ -L "$lock_dir" ] || continue
      printf 'error: profile-scoped token refresh lock path is unsafe\n' >&2
      return 1
    fi
    lock_inode="$(file_inode "$lock_dir" 2>/dev/null || true)"
    [ -n "$lock_inode" ] || continue
    lock_uid="$(file_uid "$lock_dir" 2>/dev/null || true)"
    lock_mode="$(file_mode "$lock_dir" 2>/dev/null || true)"
    if [ ! -d "$lock_dir" ] \
      || [ "$lock_uid" != "$(id -u)" ] \
      || [ "$lock_mode" != "700" ]; then
      [ "$(file_inode "$lock_dir" 2>/dev/null || true)" = "$lock_inode" ] \
        || continue
      printf 'error: profile-scoped token refresh lock path is unsafe\n' >&2
      return 1
    fi
    [ "$(file_inode "$lock_dir" 2>/dev/null || true)" = "$lock_inode" ] \
      || continue

    if [ -e "$lock_owner_file" ] || [ -L "$lock_owner_file" ]; then
      if [ -L "$lock_owner_file" ]; then
        [ -L "$lock_owner_file" ] || continue
        printf 'error: profile-scoped token refresh lock metadata is unsafe\n' >&2
        return 1
      fi
      owner_file_inode="$(file_inode "$lock_owner_file" 2>/dev/null || true)"
      [ -n "$owner_file_inode" ] || continue
      owner_file_uid="$(file_uid "$lock_owner_file" 2>/dev/null || true)"
      owner_file_mode="$(file_mode "$lock_owner_file" 2>/dev/null || true)"
      if [ ! -f "$lock_owner_file" ] \
        || [ "$owner_file_uid" != "$(id -u)" ] \
        || [ "$owner_file_mode" != "600" ]; then
        [ "$(file_inode "$lock_owner_file" 2>/dev/null || true)" = "$owner_file_inode" ] \
          || continue
        printf 'error: profile-scoped token refresh lock metadata is unsafe\n' >&2
        return 1
      fi
      [ "$(file_inode "$lock_owner_file" 2>/dev/null || true)" = "$owner_file_inode" ] \
        || continue
    fi
    owner_file_inode=""
    owner_version=""
    owner_pid="$(
      sed -n 's/^pid=//p' "$lock_owner_file" 2>/dev/null \
        | head -n 1 \
        || true
    )"
    owner_started_at="$(
      sed -n 's/^started_at_epoch=//p' "$lock_owner_file" 2>/dev/null \
        | head -n 1 \
        || true
    )"
    owner_process_started_at="$(
      sed -n 's/^process_started_at=//p' "$lock_owner_file" 2>/dev/null \
        | head -n 1 \
        || true
    )"
    owner_version="$(
      sed -n 's/^version=//p' "$lock_owner_file" 2>/dev/null \
        | head -n 1 \
        || true
    )"
    if [ -f "$lock_owner_file" ]; then
      owner_file_inode="$(file_inode "$lock_owner_file" 2>/dev/null || true)"
    fi
    metadata_valid="false"
    if [ "$owner_version" = "1" ] \
      && [[ "$owner_pid" =~ ^[0-9]+$ ]] \
      && [[ "$owner_started_at" =~ ^[0-9]+$ ]] \
      && [ -n "$owner_process_started_at" ] \
      && [ "$(wc -l <"$lock_owner_file" | tr -d '[:space:]')" = "4" ] \
      && [ "$(grep -Ec '^(version|pid|started_at_epoch|process_started_at)=' "$lock_owner_file")" = "4" ]; then
      metadata_valid="true"
    fi

    if [ "$metadata_valid" = "true" ]; then
      current_process_started_at=""
      if kill -0 "$owner_pid" 2>/dev/null; then
        current_process_started_at="$(process_started_at "$owner_pid" || true)"
      fi
      if ! kill -0 "$owner_pid" 2>/dev/null \
        || { [ -n "$current_process_started_at" ] \
          && [ "$current_process_started_at" != "$owner_process_started_at" ]; }; then
        if [ "$(file_inode "$lock_dir" 2>/dev/null || true)" = "$lock_inode" ] \
          && [ "$(file_inode "$lock_owner_file" 2>/dev/null || true)" = "$owner_file_inode" ]; then
          rm -f -- "$lock_owner_file"
          if rmdir -- "$lock_dir" 2>/dev/null; then
            printf 'warning: recovered a stale profile-scoped token refresh lock\n' >&2
            continue
          fi
        fi
      fi
    else
      now_epoch="$(date +%s)"
      lock_mtime="$(file_mtime_epoch "$lock_dir" 2>/dev/null || true)"
      case "$lock_mtime" in
        '' | *[!0-9]*)
          lock_age=0
          ;;
        *)
          lock_age=$((now_epoch - lock_mtime))
          [ "$lock_age" -ge 0 ] || lock_age=0
          ;;
      esac
      if [ "$lock_age" -ge "$lock_wait_seconds" ] \
        && [ "$(file_inode "$lock_dir" 2>/dev/null || true)" = "$lock_inode" ]; then
        if [ -n "$owner_file_inode" ]; then
          if [ "$(file_inode "$lock_owner_file" 2>/dev/null || true)" = "$owner_file_inode" ]; then
            rm -f -- "$lock_owner_file"
          fi
        elif [ -e "$lock_owner_file" ] || [ -L "$lock_owner_file" ]; then
          sleep 1
          waited=$((waited + 1))
          continue
        fi
        if rmdir -- "$lock_dir" 2>/dev/null; then
          printf 'warning: recovered an incomplete profile-scoped token refresh lock\n' >&2
          continue
        fi
      fi
    fi
    if [ "$waited" -ge "$lock_wait_seconds" ]; then
      printf 'error: timed out waiting for the profile-scoped token refresh lock\n' >&2
      return 1
    fi
    sleep 1
    waited=$((waited + 1))
  done
  if [ "$waited" -gt 0 ] \
    && [ -f "$GRAFANA_TOKEN_FILE" ] \
    && [ ! -L "$GRAFANA_TOKEN_FILE" ]; then
    token_inode_after="$(file_inode "$GRAFANA_TOKEN_FILE")"
    if [ -n "$token_inode_after" ] \
      && [ "$token_inode_after" != "$token_inode_before" ]; then
      validate_private_file "$GRAFANA_TOKEN_FILE"
      if ! token_file_is_fresh; then
        cleanup_refresh_artifacts
        printf 'error: concurrent refresh produced incomplete or stale token state; retry setup if this persists\n' >&2
        return 1
      fi
      if [ "$(file_inode "$lock_dir" 2>/dev/null || true)" = "$lock_inode" ]; then
        cleanup_refresh_artifacts
        if [ ! -e "$lock_dir" ] && [ ! -L "$lock_dir" ]; then
          printf 'warning: reused the fresh profile-scoped token produced by the prior refresh owner\n' >&2
          return 0
        fi
      fi
      die "token refresh lock changed while reusing a concurrent refresh"
    fi
  fi
  if [ "$waited" -gt 0 ] && [ "$auth_mode" = "interactive" ]; then
    cleanup_refresh_artifacts
    printf 'error: prior foreground token refresh ended without producing a fresh token\n' >&2
    return 1
  fi
  refresh_lock_owner_pid="$writer_pid"
  refresh_lock_process_started_at="$writer_started_at"
  {
    printf 'version=1\n'
    printf 'pid=%s\n' "$writer_pid"
    printf 'started_at_epoch=%s\n' "$(date +%s)"
    printf 'process_started_at=%s\n' "$writer_started_at"
  } >"$lock_owner_file"
  chmod 600 "$lock_owner_file" \
    || die "unable to protect token refresh lock metadata"
  exit_if_refresh_worker_stop_requested

  active_tmp_file="$(mktemp "${GRAFANA_TOKEN_FILE}.tmp.XXXXXX")"
  if ! chmod 600 "$active_tmp_file"; then
    printf 'error: unable to enforce mode 0600 on the temporary token file\n' >&2
    cleanup_refresh_artifacts
    return 1
  fi
  exit_if_refresh_worker_stop_requested

  if ! validate_identity_binding "$auth_mode"; then
    cleanup_refresh_artifacts
    return 1
  fi
  exit_if_refresh_worker_stop_requested
  observation_started_at="$(date +%s)"
  if ! run_nebius_clean iam get-access-token \
    --profile "$NEBIUS_GRAFANA_USER_PROFILE" \
    "${auth_args[@]}" </dev/null >"$active_tmp_file"; then
    printf 'error: Nebius CLI could not mint a token for the pinned human profile\n' >&2
    cleanup_refresh_artifacts
    return 1
  fi
  exit_if_refresh_worker_stop_requested
  if ! validate_identity_binding noninteractive; then
    cleanup_refresh_artifacts
    return 1
  fi
  exit_if_refresh_worker_stop_requested
  if ! validate_token_contents "$active_tmp_file"; then
    printf 'error: Nebius CLI returned an invalid access token payload\n' >&2
    cleanup_refresh_artifacts
    return 1
  fi

  if ! mv -f -- "$active_tmp_file" "$GRAFANA_TOKEN_FILE"; then
    printf 'error: unable to atomically replace the profile-scoped token file\n' >&2
    cleanup_refresh_artifacts
    return 1
  fi
  active_tmp_file=""
  if ! chmod 600 "$GRAFANA_TOKEN_FILE"; then
    printf 'error: unable to enforce mode 0600 on the token file\n' >&2
    cleanup_refresh_artifacts
    return 1
  fi
  if ! validate_private_file "$GRAFANA_TOKEN_FILE"; then
    cleanup_refresh_artifacts
    return 1
  fi

  if ! python3 -B "$script_dir/token_state.py" record "$GRAFANA_TOKEN_FILE" "$observation_started_at"; then
    cleanup_refresh_artifacts
    return 1
  fi
  cleanup_refresh_artifacts
}

run_mcp_clean() {
  export NEBIUS_GRAFANA_GENERATION_FILE="$generation_file"
  exec python3 -B "$script_dir/mcp_bridge.py" 2>/dev/null
}

build_mcp_args() {
  # Accept exactly the registration contract, or no arguments for direct
  # operator invocation. The bridge always supplies its own immutable flags.
  python3 -B - "$script_dir" "$@" <<'PYARGS'
import sys
sys.path.insert(0, sys.argv[1])
from runtime_contract import MCP_ARGS
if sys.argv[2:] and tuple(sys.argv[2:]) != MCP_ARGS:
    print("Unsupported MCP arguments; fixed read-only flags are required.", file=sys.stderr)
    raise SystemExit(1)
PYARGS
}

refresh_with_retries() {
  local delay

  if refresh_token noninteractive; then
    return 0
  fi
  for delay in $NEBIUS_GRAFANA_TOKEN_REFRESH_RETRY_SECONDS; do
    printf 'warning: Nebius Grafana token refresh failed; retrying after %s seconds\n' "$delay" >&2
    wait_for_worker_timer "$delay"
    exit_if_refresh_worker_stop_requested
    if refresh_token noninteractive; then
      return 0
    fi
  done
  return 1
}

run_refresh_loop() {
  trap cleanup_refresh_worker EXIT
  trap 'request_refresh_worker_stop 130' INT
  trap 'request_refresh_worker_stop 143' TERM

  wait_for_worker_timer "$refresh_after_seconds"
  exit_if_refresh_worker_stop_requested
  if ! refresh_with_retries; then
    printf 'error: Nebius Grafana token refresh exhausted; stopping MCP at the operational limit\n' >&2
    refresh_worker_stopped_mcp="true"
    write_refresh_exit_reason "refresh-exhausted" || return 1
    return 1
  fi

  # Each proxy connection freezes one token generation. Reconnect only after
  # the file contains a different generation; repeated cached bytes are not
  # successful renewal and must never extend the operational deadline.
  if ! python3 -B "$script_dir/token_state.py" changed "$GRAFANA_TOKEN_FILE" "$generation_file"; then
    write_refresh_exit_reason "refresh-exhausted" || return 1
    refresh_worker_stopped_mcp="true"
    return 1
  fi
  printf 'warning: refreshed the Nebius Grafana token; requesting bounded stdio shutdown because a new chat or client restart is required to load it\n' >&2
  refresh_worker_stopped_mcp="true"
  write_refresh_exit_reason "rotation-required" || return 1
  return 75
}

case "${1:-}" in
  -h | --help) usage; finish 0 ;;
esac
[ -n "${GRAFANA_URL:-}" ] || die "GRAFANA_URL is required"
[ -n "${NEBIUS_GRAFANA_AGENT:-}" ] || die "NEBIUS_GRAFANA_AGENT is required"
[ -n "${NEBIUS_GRAFANA_MCP_BINARY:-}" ] || die "NEBIUS_GRAFANA_MCP_BINARY is required"
: "${NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS:=36000}"
: "${NEBIUS_GRAFANA_TOKEN_REFRESH_RETRY_SECONDS:=60 300 900}"
: "${NEBIUS_GRAFANA_LOCK_WAIT_SECONDS:=90}"
: "${NEBIUS_GRAFANA_STARTUP_LOCK_WAIT_SECONDS:=210}"

case "${1:-}" in
  -h | --help)
    usage
    finish 0
    ;;
esac

[ -n "${NEBIUS_GRAFANA_USER_PROFILE:-}" ] || die "NEBIUS_GRAFANA_USER_PROFILE is required"
[ -n "${NEBIUS_GRAFANA_IDENTITY_FILE:-}" ] || die "NEBIUS_GRAFANA_IDENTITY_FILE is required"
[ -n "${GRAFANA_TOKEN_FILE:-}" ] || die "GRAFANA_TOKEN_FILE is required"

require_command python3
require_command ps
validate_profile_name "$NEBIUS_GRAFANA_USER_PROFILE"
validate_positive_integer \
  "NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS" \
  "$NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS" \
  36000
validate_positive_integer \
  "NEBIUS_GRAFANA_LOCK_WAIT_SECONDS" \
  "$NEBIUS_GRAFANA_LOCK_WAIT_SECONDS" \
  120
validate_positive_integer \
  "NEBIUS_GRAFANA_STARTUP_LOCK_WAIT_SECONDS" \
  "$NEBIUS_GRAFANA_STARTUP_LOCK_WAIT_SECONDS" \
  240
validate_retry_delays
validate_nebius_grafana_url
validate_state_paths
read_identity_binding


require_command nebius

if [ "${1:-}" = "--refresh-token-only" ]; then
  [ "$#" -eq 1 ] || die "invalid internal refresh arguments"
  refresh_token interactive
  finish 0
fi

build_mcp_args "$@"
if ! token_file_is_fresh; then
  printf 'warning: cached pinned-human token is missing or older than one hour; renewing it before MCP startup\n' >&2
  refresh_token noninteractive \
    || die "human authentication is required; invoke nebius-grafana-mcp-install again and complete browser sign-in if needed"
  token_file_is_fresh \
    || die "renewed pinned-human token failed the startup freshness check"
fi

refresh_reason_file="$(mktemp "${GRAFANA_TOKEN_FILE}.restart.XXXXXX")" \
  || die "unable to create private refresh-reason state"
chmod 600 "$refresh_reason_file"
validate_private_file "$refresh_reason_file"
generation_file="${refresh_reason_file}.generation"
loaded_observed_at="$(python3 -B "$script_dir/token_state.py" freeze "$GRAFANA_TOKEN_FILE" "$generation_file")" \
  || die "unable to freeze the startup token generation"
refresh_after_seconds=$((loaded_observed_at + 36000 - $(date +%s)))
[ "$refresh_after_seconds" -ge 0 ] || refresh_after_seconds=0
if [ "$NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS" -lt "$refresh_after_seconds" ]; then
  refresh_after_seconds="$NEBIUS_GRAFANA_TOKEN_REFRESH_SECONDS"
fi

# Bash redirects stdin for asynchronous commands to /dev/null when job control
# is unavailable unless the command has an explicit stdin redirection. Preserve
# the wrapper's MCP stdio stream on a private descriptor before backgrounding.
exec 3<&0
run_mcp_clean <&3 3<&- &
mcp_pid="$!"
mcp_process_started_at="$(process_started_at "$mcp_pid" 2>/dev/null || true)"
group_wait=0
while [ "$group_wait" -lt 40 ]; do
  candidate_group="$(ps -o pgid= -p "$mcp_pid" 2>/dev/null | tr -d '[:space:]' || true)"
  if [ "$candidate_group" = "$mcp_pid" ]; then
    mcp_group_id="$candidate_group"
    break
  fi
  process_is_live_instance "$mcp_pid" "$mcp_process_started_at" || break
  sleep 0.05
  group_wait=$((group_wait + 1))
done
exec 3<&-
if [ -z "$mcp_group_id" ]; then
  stop_owned_mcp_from_parent || true
  die "MCP process-group ownership was not established; startup stopped"
fi
if [ -z "$mcp_process_started_at" ]; then
  status=0
  wait "$mcp_pid" || status="$?"
  mcp_pid=""
  finish "$status"
fi

python3 -B "$script_dir/token_state.py" watch "$loaded_observed_at" "$refresh_reason_file" &
deadline_pid="$!"
deadline_process_started_at="$(process_started_at "$deadline_pid" 2>/dev/null || true)"
run_refresh_loop &
refresher_pid="$!"
refresher_process_started_at="$(
  process_started_at "$refresher_pid" 2>/dev/null || true
)"

refresh_reason=""
confirmed_refresh_reason=""
while process_is_live_instance "$mcp_pid" "$mcp_process_started_at"; do
  refresh_reason=""
  IFS= read -r refresh_reason <"$refresh_reason_file" || true
  if [ -n "$refresh_reason" ]; then
    if stop_owned_mcp_from_parent; then
      confirmed_refresh_reason="$refresh_reason"
    fi
    break
  fi
  if ! process_is_live_instance \
    "$refresher_pid" "$refresher_process_started_at"; then
    IFS= read -r refresh_reason <"$refresh_reason_file" || true
    [ -n "$refresh_reason" ] || refresh_reason="refresh-worker-failed"
    if stop_owned_mcp_from_parent; then
      confirmed_refresh_reason="$refresh_reason"
    fi
    break
  fi
  if ! process_is_live_instance "$deadline_pid" "$deadline_process_started_at" \
    || process_is_stopped_instance "$deadline_pid" "$deadline_process_started_at"; then
    if stop_owned_mcp_from_parent; then
      confirmed_refresh_reason="deadline-worker-failed"
    fi
    break
  fi
  sleep 1
done

status=0
kill_owned_mcp_group
wait "$mcp_pid" || status="$?"
mcp_pid=""
case "$confirmed_refresh_reason" in
  '') finish "$status" ;;
esac

refresh_reason="$confirmed_refresh_reason"
case "$refresh_reason" in
  rotation-required)
    refresh_status=0
    wait "$refresher_pid" || refresh_status="$?"
    refresher_pid=""
    if [ "$refresh_status" -ne 75 ]; then
      printf 'error: token rotation stopped MCP without the expected refresh-worker status\n' >&2
      finish 1
    fi
    printf 'error: Nebius Grafana credential rotated; start a new chat or restart the selected client before using this MCP server again\n' >&2
    finish 75
    ;;
  refresh-exhausted | refresh-worker-failed | credential-deadline | deadline-worker-failed)
    kill -CONT "$refresher_pid" >/dev/null 2>&1 || true
    kill "$refresher_pid" >/dev/null 2>&1 || true
    wait "$refresher_pid" >/dev/null 2>&1 || true
    refresher_pid=""
    finish 1
    ;;
  '')
    ;;
  *)
    printf 'error: invalid refresh exit reason; refusing to report MCP success\n' >&2
    finish 1
    ;;
esac
finish "$status"
