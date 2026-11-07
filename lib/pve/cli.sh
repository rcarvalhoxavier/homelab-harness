# shellcheck shell=bash
# shellcheck disable=SC2034  # globals exported to the tools
# Common flags, confirmation, check lines and the step plan of changing tools.

PVE_DRY_RUN=0
PVE_YES=0
PVE_NODE_OPT=""
PVE_ARGS=()
PVE_PLAN=()
PVE_HINTS=()
PVE_STEP_OUT=()
# Optional numbering of a plan that is one phase of a longer one: steps print as BASE+n/TOTAL.
PVE_STEP_BASE=0
PVE_STEP_TOTAL=""

# pve_cli_parse ARGS...: -h/--help (calls the tool's usage), --dry-run, --yes, --quiet, --node NODE
# (PVE_NODE_OPT: the node of a VMID target, or the only node a collector reports; pve_init checks it
# against the inventory); the rest lands in PVE_ARGS in order.
pve_cli_parse() {
  PVE_ARGS=()
  while (($# > 0)); do
    case "$1" in
      -h|--help) usage; exit 0 ;;
      --dry-run) PVE_DRY_RUN=1 ;;
      --yes) PVE_YES=1 ;;
      --quiet) PVE_QUIET=1 ;;
      --node)
        (($# >= 2)) || pve_usage_error "--node needs a value"
        PVE_NODE_OPT="$2"
        shift
        ;;
      *) PVE_ARGS+=("$1") ;;
    esac
    shift
  done
}

# pve_target_node NODE: for a tool whose target is a node: NODE must be in the inventory, and
# --node, when given, must name the same node.
pve_target_node() {
  pve_require_node "$1"
  [[ -z "$PVE_NODE_OPT" || "$PVE_NODE_OPT" == "$1" ]] ||
    pve_usage_error "--node $PVE_NODE_OPT does not match the target node $1"
}

pve_usage_error() {
  printf '%s: %s\n' "$(basename "$0")" "$1" >&2
  usage >&2
  exit 2
}

# pve_confirm PROMPT: --yes, or a "y" typed on a terminal. Without a terminal and without --yes,
# exit 2: the agent passes --yes only after the user approved that exact command.
pve_confirm() {
  local reply
  ((PVE_YES == 1)) && return 0
  [[ -t 0 ]] || pve_die 2 "confirmation needed and stdin is not a terminal: re-run with --yes once the user has approved this exact command"
  read -r -p "$1 [y/N] " reply
  [[ "${reply,,}" == y || "${reply,,}" == yes ]]
}

pve_check_ok() { printf 'check: %s: ok\n' "$1"; }
pve_check_warn() { printf 'check: %s: WARNING\n' "$1"; log_warn "$1"; }
pve_check_fail() { printf 'check: %s: FAILED\n' "$1"; log_error "$1"; exit 1; }
pve_verify_ok() { printf 'verify: %s: ok\n' "$1"; }
pve_verify_fail() { printf 'verify: %s: FAILED\n' "$1"; log_error "$1"; exit 1; }

pve_plan_reset() {
  PVE_PLAN=()
  PVE_HINTS=()
  PVE_STEP_OUT=()
  PVE_STEP_BASE=0
  PVE_STEP_TOTAL=""
}

# pve_plan_numbering BASE TOTAL: print this plan's steps as BASE+1/TOTAL...; call after pve_plan_reset.
pve_plan_numbering() {
  PVE_STEP_BASE="$1"
  PVE_STEP_TOTAL="$2"
}

# pve_hint KEY VALUE: a line printed before the steps (target, path, rollback, baseline/after).
pve_hint() {
  PVE_HINTS+=("$1: $2")
}

# pve_plan_add NODE ARGV...: a command for the node's admin alias.
pve_plan_add() {
  local node="$1"
  shift
  PVE_PLAN+=("run"$'\t'"$node"$'\t'"$(_pve_quote "$@")")
}

# pve_plan_put NODE LOCAL REMOTE MODE [summary]: a file written on the node. A dry run shows its
# content, or with "summary" only its line count and hash (for a long file that ships with the repo).
pve_plan_put() {
  PVE_PLAN+=("put"$'\t'"$1"$'\t'"$2"$'\t'"$3"$'\t'"$4"$'\t'"${5:-content}")
}

_pve_plan_describe() {
  local i="$1" kind node rest src dest mode
  IFS=$'\t' read -r kind node rest <<< "${PVE_PLAN[$i]}"
  _pve_alias_of "$node" admin
  if [[ "$kind" == run ]]; then
    printf 'step %d/%d: ssh %s -- %s\n' $((PVE_STEP_BASE + i + 1)) "${PVE_STEP_TOTAL:-${#PVE_PLAN[@]}}" "$REPLY" "$rest"
  else
    IFS=$'\t' read -r src dest mode _ <<< "$rest"
    printf 'step %d/%d: put %s (mode %s) on %s\n' $((PVE_STEP_BASE + i + 1)) "${PVE_STEP_TOTAL:-${#PVE_PLAN[@]}}" "$dest" "$mode" "$REPLY"
  fi
}

_pve_plan_show_put() {
  local kind node rest src dest mode show
  IFS=$'\t' read -r kind node rest <<< "${PVE_PLAN[$1]}"
  [[ "$kind" == put ]] || return 0
  IFS=$'\t' read -r src dest mode show <<< "$rest"
  if [[ "$show" == summary ]]; then
    printf '    (%d lines, sha256 %s; content not shown)\n' "$(wc -l < "$src")" "$(pve_sha256 < "$src" | cut -c1-16)"
  else
    sed 's/^/    | /' "$src"
  fi
}

_pve_plan_run_one() {
  local i="$1" kind node rest src dest mode out
  local -a argv
  IFS=$'\t' read -r kind node rest <<< "${PVE_PLAN[$i]}"
  out="$(mktemp)"
  pve_cleanup_add "$out"
  PVE_STEP_OUT[i]="$out"
  if [[ "$kind" == run ]]; then
    eval "argv=($rest)"
    pve_admin "$node" "${argv[@]}" 2>&1 | tee "$out"
    return "${PIPESTATUS[0]}"
  fi
  IFS=$'\t' read -r src dest mode _ <<< "$rest"
  pve_admin_put "$node" "$src" "$dest" "$mode" 2>&1 | tee "$out"
  return "${PIPESTATUS[0]}"
}

# pve_plan_execute PROMPT [CANCELLED]: with --dry-run, print hints and steps and change nothing;
# otherwise confirm, then run the steps in order, stopping at the first failure (its exit code is
# returned). A declined confirmation prints CANCELLED (default "cancelled") and returns 1.
pve_plan_execute() {
  local prompt="$1" cancelled="${2:-cancelled}" hint i rc
  for hint in "${PVE_HINTS[@]+"${PVE_HINTS[@]}"}"; do
    printf '%s\n' "$hint"
  done
  if ((${#PVE_PLAN[@]} == 0)); then
    printf 'nothing to do\n'
    return 0
  fi
  if ((PVE_DRY_RUN == 1)); then
    for i in "${!PVE_PLAN[@]}"; do
      _pve_plan_describe "$i"
      _pve_plan_show_put "$i"
    done
    printf 'dry run: nothing was changed\n'
    return 0
  fi
  if ! pve_confirm "$prompt"; then
    printf '%s\n' "$cancelled"
    return 1
  fi
  for i in "${!PVE_PLAN[@]}"; do
    _pve_plan_describe "$i"
    rc=0
    _pve_plan_run_one "$i" || rc=$?
    printf 'result: exit %d\n' "$rc"
    if ((rc != 0)); then
      log_error "step $((PVE_STEP_BASE + i + 1)) failed; the remaining steps were not run"
      return "$rc"
    fi
  done
}

# pve_run_timeout SECONDS OUTFILE CMD...: run CMD with stdout and stderr in OUTFILE; 124 on timeout.
pve_run_timeout() {
  local seconds="$1" out="$2" pid ticks=0 had_m=0
  shift 2
  # Job control around the start makes the child a process-group leader (no setsid needed), so a
  # timeout can signal the whole group; the caller's setting is restored right after.
  [[ $- == *m* ]] && had_m=1
  set -m
  "$@" > "$out" 2>&1 < /dev/null &
  pid=$!
  ((had_m == 1)) || set +m
  while kill -0 "$pid" 2>/dev/null; do
    if ((ticks >= seconds * 10)); then
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
      ticks=0
      while ((ticks < 20)) && kill -0 "$pid" 2>/dev/null; do
        sleep 0.1
        ticks=$((ticks + 1))
      done
      kill -KILL -- "-$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 124
    fi
    sleep 0.1
    ticks=$((ticks + 1))
  done
  wait "$pid"
}
