# shellcheck shell=bash
# shellcheck disable=SC2034  # globals exported to the tools
# Entry point of the Proxmox toolkit library. Tools and instance scripts source this file.

if ((BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 4))); then
  printf 'homelab-harness needs Bash 4.4 or newer (this is %s); on macOS: brew install bash\n' \
    "$BASH_VERSION" >&2
  exit 2
fi
if [[ -n "${_PVE_INIT_LOADED:-}" ]]; then
  return 0
fi
_PVE_INIT_LOADED=1

PVE_LIB_API=1
PVE_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PVE_ROOT="$(cd "$PVE_LIB_DIR/../.." && pwd)"

# shellcheck source=log.sh
source "$PVE_LIB_DIR/log.sh"
# shellcheck source=env.sh
source "$PVE_LIB_DIR/env.sh"
# shellcheck source=inventory.sh
source "$PVE_LIB_DIR/inventory.sh"
# shellcheck source=ssh.sh
source "$PVE_LIB_DIR/ssh.sh"
# shellcheck source=parse.sh
source "$PVE_LIB_DIR/parse.sh"
# shellcheck source=pve.sh
source "$PVE_LIB_DIR/pve.sh"
# shellcheck source=cli.sh
source "$PVE_LIB_DIR/cli.sh"

# pve_require_api N: stop with a clear message when the library's API version is not N.
pve_require_api() {
  [[ "$1" == "$PVE_LIB_API" ]] ||
    pve_die 2 "this script needs lib/pve API $1, but the library provides API $PVE_LIB_API: update one of them"
}

# pve_init TOOL ARGS...: load .env.local and the inventory, check --node, then open the audit log.
pve_init() {
  local tool="$1"
  shift
  pve_env_load "$PVE_ROOT/.env.local"
  pve_inventory_load "$PVE_ROOT/inventory/nodes"
  [[ -z "${PVE_NODE_OPT:-}" ]] || pve_require_node "$PVE_NODE_OPT"
  pve_audit_start "$tool" "$@"
}
