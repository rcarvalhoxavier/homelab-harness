# shellcheck shell=bash
# shellcheck disable=SC2034  # globals exported to the tools
# SSH to Proxmox nodes: argv only, never a shell string. Reads go through the collect alias (the
# forced-command key); changes go through the admin alias. See docs/proxmox-toolkit.md.

PVE_ARG_RE='^[A-Za-z0-9_./:=,@+-]+$'
PVE_REFUSED_MARKER='homelab-collect: refused'
# Connection sharing is off: the collect and admin aliases usually reach the same user@host:port,
# and a shared ControlMaster socket would run reads with the admin key (or changes with the
# restricted one).
PVE_SSH_OPTS=(-o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3
              -o ControlMaster=no -o ControlPath=none)

# _pve_ssh_prefix ssh|scp: set _PVE_SSH_PREFIX to the program and options of one call.
_pve_ssh_prefix() {
  if [[ "${HOMELAB_SSHPASS:-0}" == 1 ]]; then
    command -v sshpass >/dev/null 2>&1 ||
      pve_die 2 "HOMELAB_SSHPASS=1 needs sshpass (Debian/Ubuntu: apt install sshpass)"
    _PVE_SSH_PREFIX=(sshpass -e "$1" -o BatchMode=no -o PubkeyAuthentication=no "${PVE_SSH_OPTS[@]}")
  else
    _PVE_SSH_PREFIX=("$1" -o BatchMode=yes "${PVE_SSH_OPTS[@]}")
  fi
}

# _pve_exec_ssh ARGV...: run a prepared call; only the fallback's child process sees SSHPASS.
_pve_exec_ssh() {
  if [[ "${HOMELAB_SSHPASS:-0}" == 1 ]]; then
    SSHPASS="$_PVE_SSHPASS" "$@"
  else
    "$@"
  fi
}

# _pve_run_ssh ALIAS STRING: one ssh call; returns ssh's exit code.
_pve_run_ssh() {
  _pve_ssh_prefix ssh
  _pve_exec_ssh "${_PVE_SSH_PREFIX[@]}" -n -- "$1" "$2"
}

# _pve_quote ARGV...: one string the remote bash splits back into the same argv.
_pve_quote() {
  local arg out=""
  for arg in "$@"; do
    out+="$(printf '%q' "$arg") "
  done
  printf '%s' "${out% }"
}

# pve_collect NODE ARGV...: run a read-only command through the node's collect alias. Every
# argument must match PVE_ARG_RE, so the string the host receives equals the argv.
pve_collect() {
  local node="$1" arg alias remote errfile rc=0
  shift
  for arg in "$@"; do
    [[ "$arg" =~ $PVE_ARG_RE ]] || pve_die 2 "pve_collect: argument not allowed on the collect path: '$arg'"
  done
  _pve_alias_of "$node" collect
  alias="$REPLY"
  printf -v remote '%s ' "$@"
  remote="${remote% }"
  _pve_ssh_prefix ssh # fail on a missing sshpass before stderr is redirected
  errfile="$(mktemp)"
  pve_cleanup_add "$errfile"
  _pve_run_ssh "$alias" "$remote" 2> "$errfile" || rc=$?
  if ((rc == 126)) && grep -q "^$PVE_REFUSED_MARKER (sudo)" "$errfile"; then
    log_error "refused by sudo on $node: '$remote': every command of the allowlists must be allowed in sudoers (docs/ssh-access.md §7)"
  elif ((rc == 126)) && grep -q "^$PVE_REFUSED_MARKER" "$errfile"; then
    log_error "refused by the host's dispatcher on $node: '$remote' (run bin/pve-selftest to compare versions)"
  else
    cat "$errfile" >&2
  fi
  rm -f "$errfile"
  _pve_audit "collect $node ($alias): $remote -> exit $rc"
  return "$rc"
}

# pve_admin NODE ARGV...: run a changing command through the node's admin alias.
pve_admin() {
  local node="$1" alias remote rc=0
  shift
  _pve_alias_of "$node" admin
  alias="$REPLY"
  remote="$(_pve_quote "$@")"
  _pve_run_ssh "$alias" "$remote" || rc=$?
  _pve_audit "admin $node ($alias): $remote -> exit $rc"
  return "$rc"
}

# pve_admin_put NODE LOCAL REMOTE MODE: copy LOCAL to the absolute path REMOTE (mode like 0644) on
# the node, through a temporary file that mktemp creates on the host (never a predictable name).
pve_admin_put() {
  local node="$1" src="$2" dest="$3" mode="$4" alias tmp rc=0
  [[ "$dest" == /* && "$dest" =~ $PVE_ARG_RE && "$mode" =~ ^[0-7]{4}$ ]] ||
    pve_die 2 "pve_admin_put: bad destination '$dest' (an absolute path) or mode '$mode'"
  _pve_alias_of "$node" admin
  alias="$REPLY"
  _pve_ssh_prefix scp # fail on a missing sshpass before anything is sent
  tmp="$(pve_admin "$node" mktemp /tmp/homelab-put.XXXXXXXX)" || rc=$?
  if ((rc == 0)) && [[ ! "$tmp" =~ ^/tmp/homelab-put\.[A-Za-z0-9]{8}$ ]]; then
    log_error "pve_admin_put: mktemp on $node did not answer a temporary file name: '$tmp'"
    rc=1
  fi
  if ((rc == 0)); then
    _pve_ssh_prefix scp
    _pve_exec_ssh "${_PVE_SSH_PREFIX[@]}" -q -- "$src" "$alias:$tmp" || rc=$?
    if ((rc == 0)); then
      pve_admin "$node" install -o root -g root -m "$mode" "$tmp" "$dest" || rc=$?
    fi
    pve_admin "$node" rm -f "$tmp" || true
  fi
  _pve_audit "put $node ($alias): $dest mode $mode -> exit $rc"
  return "$rc"
}

# pve_reachable NODE: the probe every tool uses (uname -r through the collect alias). On failure
# PVE_REACH_RC is its exit code and PVE_REACH_ERR the last line ssh or the dispatcher printed; that
# reason goes to stderr with a pointer to docs/ssh-access.md (stdout stays the report).
PVE_REACH_RC=0
PVE_REACH_ERR=""
pve_reachable() {
  local err
  _pve_ssh_prefix ssh # a missing sshpass is a configuration error, not "unreachable"
  err="$(mktemp)"
  pve_cleanup_add "$err"
  PVE_REACH_RC=0
  pve_collect "$1" uname -r > /dev/null 2> "$err" || PVE_REACH_RC=$?
  PVE_REACH_ERR="$(grep -v '^[[:space:]]*$' "$err" | tail -n 1)" || true
  rm -f "$err"
  if ((PVE_REACH_RC != 0)); then
    log_error "$1: the collect alias does not connect (exit $PVE_REACH_RC)${PVE_REACH_ERR:+: $PVE_REACH_ERR}; see docs/ssh-access.md"
    return 1
  fi
  PVE_REACH_ERR=""
}
