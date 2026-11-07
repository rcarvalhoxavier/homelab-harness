# shellcheck shell=bash
# Progress messages on stderr, the audit log of each run, and cleanup at exit.

PVE_QUIET="${PVE_QUIET:-0}"
_PVE_AUDIT_FILE=""
_PVE_CLEANUP=()

_pve_log() {
  local level="$1"
  shift
  if [[ "$level" != INFO || "$PVE_QUIET" != 1 ]]; then
    printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*" >&2
  fi
  _pve_audit "[$level] $*"
}

log_info() { _pve_log INFO "$@"; }
log_warn() { _pve_log WARN "$@"; }
log_error() { _pve_log ERROR "$@"; }

# pve_die CODE MESSAGE...: log an error and exit with CODE.
pve_die() {
  local code="$1"
  shift
  log_error "$@"
  exit "$code"
}

_pve_audit() {
  [[ -n "$_PVE_AUDIT_FILE" ]] || return 0
  printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')" "$*" >> "$_PVE_AUDIT_FILE" 2>/dev/null || true
}

# pve_cleanup_add PATH: remove PATH (file or directory) when the script exits.
pve_cleanup_add() {
  _PVE_CLEANUP+=("$1")
}

_pve_on_exit() {
  local code="$1"
  if ((${#_PVE_CLEANUP[@]} > 0)); then
    rm -rf -- "${_PVE_CLEANUP[@]}"
  fi
  _pve_audit "finished: exit $code"
}
trap '_pve_on_exit $?' EXIT

# pve_audit_start TOOL ARGS...: open $HOMELAB_LOG_DIR/<date>_<tool>.log unless HOMELAB_LOG=0.
# The log records actions (log lines, remote commands and their exit codes), not the report. It is
# private: a directory the tool creates is 0700, the file 0600.
pve_audit_start() {
  local tool="$1" dir file mask
  shift
  [[ "${HOMELAB_LOG:-1}" == 1 ]] || return 0
  dir="${HOMELAB_LOG_DIR:-$PVE_ROOT/logs}"
  mask="$(umask)"
  umask 077
  if ! mkdir -p "$dir" 2>/dev/null; then
    umask "$mask"
    log_warn "cannot create $dir: audit log disabled"
    return 0
  fi
  file="$dir/$(date +%Y-%m-%d_%H%M%S)_${tool}.log"
  if ! { : >> "$file" && chmod 600 "$file"; } 2>/dev/null; then
    umask "$mask"
    log_warn "cannot write $file: audit log disabled"
    return 0
  fi
  umask "$mask"
  _PVE_AUDIT_FILE="$file"
  {
    printf 'tool: %s\n' "$tool"
    printf 'args: %s\n' "$*"
    printf 'user: %s\n' "$(id -un 2>/dev/null || echo unknown)"
    printf 'started: %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')"
  } >> "$_PVE_AUDIT_FILE"
}
