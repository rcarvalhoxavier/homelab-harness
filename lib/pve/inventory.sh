# shellcheck shell=bash
# shellcheck disable=SC2034  # globals exported to the tools
# inventory/nodes: one Proxmox node per line, "node [collect-alias] [admin-alias]".

PVE_NAME_RE='^[A-Za-z0-9][A-Za-z0-9.-]*$'
PVE_NODE_LIST=()
declare -A _PVE_COLLECT_ALIAS=() _PVE_ADMIN_ALIAS=() _PVE_ALIAS_OWNER=()

# pve_inventory_load [FILE]: read FILE (default $PVE_ROOT/inventory/nodes); exit 2 on any error.
pve_inventory_load() {
  local file="${1:-$PVE_ROOT/inventory/nodes}" line n=0 rel node collect admin name
  local -a cols
  rel="${file#"$PVE_ROOT"/}"
  [[ -f "$file" ]] ||
    pve_die 2 "no inventory: create $rel with one Proxmox node per line, e.g. 'pve1' (docs/proxmox-toolkit.md)"
  PVE_NODE_LIST=()
  _PVE_COLLECT_ALIAS=()
  _PVE_ADMIN_ALIAS=()
  _PVE_ALIAS_OWNER=()
  while IFS= read -r line || [[ -n "$line" ]]; do
    n=$((n + 1))
    line="${line%$'\r'}"
    line="${line%%#*}"
    read -r -a cols <<< "$line"
    ((${#cols[@]} > 0)) || continue
    ((${#cols[@]} <= 3)) || pve_die 2 "$rel:$n: expected 'node [collect] [admin]', got ${#cols[@]} columns"
    node="${cols[0]}"
    collect="${cols[1]:-$node}"
    admin="${cols[2]:-$node-admin}"
    for name in "$node" "$collect" "$admin"; do
      [[ "$name" =~ $PVE_NAME_RE ]] || pve_die 2 "$rel:$n: invalid name '$name'"
    done
    [[ -z "${_PVE_COLLECT_ALIAS[$node]+x}" ]] || pve_die 2 "$rel:$n: node '$node' listed twice"
    [[ "$collect" != "$admin" ]] || pve_die 2 "$rel:$n: the collect and admin aliases must differ ('$collect')"
    # one alias per node and role: a shared alias would send one node's commands to another
    for name in "$collect" "$admin"; do
      [[ -z "${_PVE_ALIAS_OWNER[$name]+x}" ]] ||
        pve_die 2 "$rel:$n: alias '$name' is already used by node '${_PVE_ALIAS_OWNER[$name]}'"
      _PVE_ALIAS_OWNER[$name]="$node"
    done
    _PVE_COLLECT_ALIAS[$node]="$collect"
    _PVE_ADMIN_ALIAS[$node]="$admin"
    PVE_NODE_LIST+=("$node")
  done < "$file"
  ((${#PVE_NODE_LIST[@]} > 0)) || pve_die 2 "$rel: no node listed"
  mapfile -t PVE_NODE_LIST < <(printf '%s\n' "${PVE_NODE_LIST[@]}" | LC_ALL=C sort)
}

pve_nodes() {
  printf '%s\n' "${PVE_NODE_LIST[@]}"
}

pve_node_known() {
  [[ -n "${_PVE_COLLECT_ALIAS[$1]+x}" ]]
}

pve_require_node() {
  pve_node_known "$1" || pve_die 2 "unknown node '$1': not in inventory/nodes"
}

# pve_inventory_reset: an empty in-memory inventory (pve-discover builds one before
# inventory/nodes exists).
pve_inventory_reset() {
  PVE_NODE_LIST=()
  _PVE_COLLECT_ALIAS=()
  _PVE_ADMIN_ALIAS=()
  _PVE_ALIAS_OWNER=()
}

# pve_inventory_add NODE [COLLECT]: add one node in memory, with the defaults and checks of the file
# format (the admin alias is <node>-admin); exit 2 on an error.
pve_inventory_add() {
  local node="$1" collect="${2:-$1}" admin="$1-admin" name
  for name in "$node" "$collect"; do
    [[ "$name" =~ $PVE_NAME_RE ]] || pve_die 2 "invalid name '$name'"
  done
  [[ -z "${_PVE_COLLECT_ALIAS[$node]+x}" ]] || pve_die 2 "node '$node' listed twice"
  [[ "$collect" != "$admin" ]] || pve_die 2 "the collect and admin aliases must differ ('$collect')"
  for name in "$collect" "$admin"; do
    [[ -z "${_PVE_ALIAS_OWNER[$name]+x}" ]] ||
      pve_die 2 "alias '$name' is already used by node '${_PVE_ALIAS_OWNER[$name]}'"
    _PVE_ALIAS_OWNER[$name]="$node"
  done
  _PVE_COLLECT_ALIAS[$node]="$collect"
  _PVE_ADMIN_ALIAS[$node]="$admin"
  PVE_NODE_LIST+=("$node")
  mapfile -t PVE_NODE_LIST < <(printf '%s\n' "${PVE_NODE_LIST[@]}" | LC_ALL=C sort)
}

# pve_alias_owner ALIAS: set REPLY to the node that uses ALIAS (collect or admin); return 1 when
# no node does.
pve_alias_owner() {
  [[ -n "${_PVE_ALIAS_OWNER[$1]+x}" ]] || return 1
  REPLY="${_PVE_ALIAS_OWNER[$1]}"
}

# _pve_alias_of NODE collect|admin: set REPLY to the SSH alias (no subshell, so pve_die stops the script).
_pve_alias_of() {
  pve_require_node "$1"
  if [[ "$2" == admin ]]; then
    REPLY="${_PVE_ADMIN_ALIAS[$1]}"
  else
    REPLY="${_PVE_COLLECT_ALIAS[$1]}"
  fi
}
