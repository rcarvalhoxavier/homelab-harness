# shellcheck shell=bash
# shellcheck disable=SC2034  # globals exported to the tools
# Reads .env.local literally: no expansion, known names only, the environment wins.

PVE_ENV_NAMES=(PVE_BACKUP_STORAGE PVE_STORAGE_WARN_PCT PVE_BACKUP_MAX_AGE_DAYS
               HOMELAB_SSHPASS SSHPASS HOMELAB_LOG_DIR HOMELAB_LOG)
_PVE_SSHPASS=""

# _pve_env_parse_line LINE: on an assignment, set _PVE_ENV_KEY and _PVE_ENV_VAL and return 0.
# Mirrors env_values() in lib/wikitools/redact.py; tests/test_pve_env.py keeps them equal.
_pve_env_parse_line() {
  local line="${1%$'\r'}" key val quote
  local comment_re='^[[:space:]]*#'
  local assign_re='^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$'
  [[ "$line" =~ $comment_re ]] && return 1
  [[ "$line" =~ $assign_re ]] || return 1
  key="${BASH_REMATCH[2]}"
  val="${BASH_REMATCH[3]}"
  val="${val%"${val##*[![:space:]]}"}"
  quote="${val:0:1}"
  if [[ "$quote" == '"' || "$quote" == "'" ]]; then
    val="${val:1}"
    if [[ "$val" == *"$quote"* ]]; then
      val="${val%%"$quote"*}"
    fi
  else
    val="${val%%[[:blank:]]#*}"
    val="${val%"${val##*[![:space:]]}"}"
  fi
  _PVE_ENV_KEY="$key"
  _PVE_ENV_VAL="$val"
}

_pve_env_known() {
  local name
  for name in "${PVE_ENV_NAMES[@]}"; do
    [[ "$name" == "$1" ]] && return 0
  done
  return 1
}

_pve_env_int() { # NAME MIN MAX
  local value="${!1}"
  if [[ ! "$value" =~ ^[0-9]{1,4}$ ]] || (( 10#$value < $2 || 10#$value > $3 )); then
    pve_die 2 "$1 must be an integer from $2 to $3 (got '$value')"
  fi
  printf -v "$1" '%d' "$((10#$value))"
}

_pve_env_flag() { # NAME
  [[ "${!1}" == 0 || "${!1}" == 1 ]] || pve_die 2 "$1 must be 0 or 1 (got '${!1}')"
}

# pve_env_load [FILE]: load the known names from FILE (default $PVE_ROOT/.env.local), apply
# defaults, validate. Other names are ignored: the file also holds secrets for wiki-capture.
pve_env_load() {
  local file="${1:-$PVE_ROOT/.env.local}" line
  if [[ -f "$file" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      _pve_env_parse_line "$line" || continue
      _pve_env_known "$_PVE_ENV_KEY" || continue
      [[ -n "${!_PVE_ENV_KEY+x}" ]] && continue
      printf -v "$_PVE_ENV_KEY" '%s' "$_PVE_ENV_VAL"
    done < "$file"
  fi
  : "${PVE_BACKUP_STORAGE:=}"
  : "${PVE_STORAGE_WARN_PCT:=85}"
  : "${PVE_BACKUP_MAX_AGE_DAYS:=2}"
  : "${HOMELAB_SSHPASS:=0}"
  : "${HOMELAB_LOG:=1}"
  : "${HOMELAB_LOG_DIR:=$PVE_ROOT/logs}"
  # a relative directory is under the repository, never under the working directory
  [[ "$HOMELAB_LOG_DIR" == /* ]] || HOMELAB_LOG_DIR="$PVE_ROOT/$HOMELAB_LOG_DIR"
  if [[ -n "$PVE_BACKUP_STORAGE" && ! "$PVE_BACKUP_STORAGE" =~ ^[A-Za-z][A-Za-z0-9_.-]{0,63}$ ]]; then
    pve_die 2 "PVE_BACKUP_STORAGE is not a storage name (got '$PVE_BACKUP_STORAGE')"
  fi
  _pve_env_int PVE_STORAGE_WARN_PCT 1 100
  _pve_env_int PVE_BACKUP_MAX_AGE_DAYS 0 9999
  _pve_env_flag HOMELAB_SSHPASS
  _pve_env_flag HOMELAB_LOG
  _PVE_SSHPASS="${SSHPASS:-}"
  unset SSHPASS
  if [[ "$HOMELAB_SSHPASS" == 1 && -z "$_PVE_SSHPASS" ]]; then
    pve_die 2 "HOMELAB_SSHPASS=1 needs SSHPASS in .env.local"
  fi
}
