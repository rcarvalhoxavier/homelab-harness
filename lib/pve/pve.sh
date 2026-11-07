# shellcheck shell=bash
# shellcheck disable=SC2034  # globals exported to the tools
# Composite queries over the collect alias: guests, snapshots, storages, backups, APT sources.

pve_cli_of() {
  if [[ "$1" == vm ]]; then echo qm; else echo pct; fi
}

# pve_guests NODE -> "vmid ct|vm status name", sorted by VMID; fails when the node cannot be read.
pve_guests() {
  local node="$1" cts vms
  cts="$(pve_collect "$node" pct list)" || return
  vms="$(pve_collect "$node" qm list)" || return
  {
    pve_parse_pct_list <<< "$cts" | awk '{ print $1, "ct", $2, $3 }'
    pve_parse_qm_list <<< "$vms" | awk '{ print $1, "vm", $2, $3 }'
  } | sort -n -k1,1
}

# _pve_cluster_has NODE OTHER...: true when NODE is in a cluster whose members include every
# OTHER (inventory names, compared with the Proxmox names of `pvecm nodes`). Any doubt is false.
# The PVE_QUORUM_* globals of the caller are kept.
_pve_cluster_has() {
  local node="$1" other
  local PVE_QUORUM_STATE PVE_QUORUM_EXPECTED PVE_QUORUM_TOTAL PVE_QUORUM_QUORATE PVE_QUORUM_COROSYNC
  local PVE_QUORUM_NODES PVE_QUORUM_WHAT PVE_QUORUM_RC PVE_QUORUM_MEMBERS PVE_QUORUM_LOCAL
  shift
  pve_quorum "$node"
  [[ "$PVE_QUORUM_STATE" == cluster ]] || return 1
  pve_quorum_members "$node" || return 1
  for other in "$@"; do
    [[ " $PVE_QUORUM_MEMBERS " == *" $other "* ]] || return 1
  done
}

# pve_find_guest VMID: set PVE_GUEST_NODE and PVE_GUEST_TYPE; return 1 when not found. Every node
# is read (only PVE_NODE_OPT with --node); a VMID listed by two nodes (not one cluster) exits 2, and
# so does a VMID found while a node outside the cluster of that node could not be read.
pve_find_guest() {
  local id="$1" node guests vmid type rc err list
  local -a unreadable=() nodes=() found=() names=()
  err="$(mktemp)"
  pve_cleanup_add "$err"
  [[ "$id" =~ ^[0-9]{1,9}$ ]] || pve_die 2 "invalid VMID '$id'"
  if [[ -n "${PVE_NODE_OPT:-}" ]]; then
    pve_require_node "$PVE_NODE_OPT"
    nodes=("$PVE_NODE_OPT")
  else
    nodes=("${PVE_NODE_LIST[@]}")
  fi
  for node in "${nodes[@]}"; do
    rc=0
    guests="$(pve_guests "$node" 2> "$err")" || rc=$?
    if ((rc != 0)); then
      # the reason (ssh error, dispatcher refusal, missing sshpass) reaches the user
      cat "$err" >&2
      # a configuration error (pve_die 2 in the subshell) must stop the caller too
      ((rc == 2)) && exit 2
      unreadable+=("$node")
      continue
    fi
    while read -r vmid type _; do
      if [[ "$vmid" == "$id" ]]; then
        found+=("$node $type")
        break
      fi
    done <<< "$guests"
  done
  if ((${#found[@]} > 1)); then
    for node in "${found[@]}"; do
      names+=("${node% *}")
    done
    list="${names[*]:0:${#names[@]}-1}"
    pve_die 2 "VMID $id is on ${list// /, } and ${names[-1]}; pass --node NODE"
  fi
  if ((${#found[@]} == 1)) && ((${#unreadable[@]} > 0)) &&
    ! _pve_cluster_has "${found[0]% *}" "${unreadable[@]}"; then
    pve_die 2 "VMID $id is on ${found[0]% *}, but ${unreadable[*]} could not be read and may list it too; pass --node NODE"
  fi
  if ((${#found[@]} == 1)); then
    PVE_GUEST_NODE="${found[0]% *}"
    PVE_GUEST_TYPE="${found[0]#* }"
    return 0
  fi
  if ((${#unreadable[@]} > 0)); then
    log_error "guest $id not found; could not read: ${unreadable[*]}"
  elif [[ -n "${PVE_NODE_OPT:-}" ]]; then
    log_error "guest $id not found on $PVE_NODE_OPT"
  else
    log_error "guest $id not found on any node of inventory/nodes"
  fi
  return 1
}

# pve_guest_status NODE TYPE VMID -> running|stopped|...
pve_guest_status() {
  local out
  out="$(pve_collect "$1" "$(pve_cli_of "$2")" status "$3")" || return
  awk '/^status:/ { print $2 }' <<< "$out"
}

# pve_guest_has_snapshot NODE TYPE VMID NAME: 0 = found, 1 = absent, 2 = unreadable (failed read,
# empty answer, or no "current" line); the stderr of a failed read stays visible.
pve_guest_has_snapshot() {
  local out
  out="$(pve_collect "$1" "$(pve_cli_of "$2")" listsnapshot "$3")" || return 2
  grep -q 'current' <<< "$out" || return 2
  pve_parse_snapshots <<< "$out" | awk -v want="$4" '$1 == want { found = 1 } END { exit !found }'
}

# pve_snapshot_capable STORAGE_TYPE VOLUME: can Proxmox snapshot a volume on this storage?
pve_snapshot_capable() {
  case "$1" in
    lvmthin|zfspool|rbd|btrfs) return 0 ;;
    dir|nfs|cifs|glusterfs) [[ "$2" == *.qcow2 ]] ;;
    *) return 1 ;;
  esac
}

# pve_require_snapshot_capable NODE TYPE VMID: check line, or exit 1 naming the first disk that cannot.
pve_require_snapshot_capable() {
  local node="$1" type="$2" id="$3" config status key storage volume stype
  config="$(pve_collect "$node" "$(pve_cli_of "$type")" config "$id")" ||
    pve_check_fail "cannot read the config of $type $id"
  [[ -n "$config" ]] || pve_check_fail "cannot read the config of $type $id: empty answer"
  status="$(pve_collect "$node" pvesm status)" || pve_check_fail "cannot read pvesm status on $node"
  # A raw passthrough disk (value starts with /) is skipped by pve_parse_config_volumes, but Proxmox
  # refuses to snapshot a VM that has one.
  local value
  while IFS=': ' read -r key value; do
    [[ "$key" =~ ^(scsi|virtio|sata|ide|nvme)[0-9]+$ || "$key" == efidisk0 || "$key" == tpmstate0 ]] || continue
    [[ "$value" == /* && "$value" != *media=cdrom* ]] || continue
    pve_check_fail "$key of $type $id is a passthrough device (${value%%,*}), which cannot be snapshotted"
  done <<< "$config"
  while read -r key storage volume _; do
    [[ -n "$key" && "$key" != unused* ]] || continue
    stype="$(pve_parse_pvesm_status <<< "$status" | awk -v s="$storage" '$1 == s { print $2 }')"
    if ! pve_snapshot_capable "$stype" "$volume"; then
      pve_check_fail "$key of $type $id is on $storage (${stype:-unknown type}), which cannot snapshot it"
    fi
  done < <(pve_parse_config_volumes <<< "$config")
  pve_check_ok "every disk of $type $id supports snapshots"
}

# pve_storage_line NODE STORAGE -> the parsed `pvesm status` line; exit 1 when absent.
pve_storage_line() {
  local out
  out="$(pve_collect "$1" pvesm status)" || return
  pve_parse_pvesm_status <<< "$out" | awk -v s="$2" '$1 == s { print; found = 1 } END { exit !found }'
}

# pve_storage_content NODE STORAGE -> the content list of storage.cfg (e.g. "rootdir,images")
pve_storage_content() {
  local out
  out="$(pve_collect "$1" cat /etc/pve/storage.cfg)" || return
  pve_parse_storage_cfg <<< "$out" | awk -F'|' -v s="$2" '$1 == s { print $6; found = 1 } END { exit !found }'
}

# pve_guest_backups NODE STORAGE VMID -> "YYYY-MM-DDTHH:MM:SS volid", oldest first.
pve_guest_backups() {
  local out volid vmid date
  out="$(pve_collect "$1" pvesm list "$2" --content backup)" || return
  while read -r volid _ _ _ vmid; do
    [[ "$vmid" == "$3" ]] || continue
    date="$(pve_backup_volid_date "$volid")" || date="-"
    printf '%s %s\n' "$date" "$volid"
  done < <(pve_parse_pvesm_list <<< "$out") | LC_ALL=C sort
}

# pve_removal_guard NODE LABEL SIMULATION: the removal check before any apt run on a node
# (pve-update-host, pve-cleanup). Fails the check (exit 1) when the simulation has no summary line,
# when its "N to remove" differs from its Remv lines, when the running kernel cannot be read, or
# when it would remove the Proxmox stack (proxmox-ve, pve-manager, qemu-server, pve-container) or
# a package of the running kernel. Sets PVE_REMOVALS (names, sorted, space-separated) and
# PVE_REMOVAL_COUNT.
pve_removal_guard() {
  local node="$1" label="$2" sim="$3" list stated running
  PVE_REMOVALS=""
  PVE_REMOVAL_COUNT=0
  grep -Eq "$PVE_APT_SUMMARY_RE" <<< "$sim" ||
    pve_check_fail "the $label simulation on $node returned no summary line"
  list="$(pve_parse_pkg_removals <<< "$sim" | LC_ALL=C sort)"
  PVE_REMOVAL_COUNT="$(awk 'NF { n++ } END { print n + 0 }' <<< "$list")"
  stated="$(sed -nE 's/^[0-9]+ upgraded, [0-9]+ newly installed, ([0-9]+) to remove and .*/\1/p' <<< "$sim")"
  stated="${stated%%$'\n'*}"
  [[ "$stated" == "$PVE_REMOVAL_COUNT" ]] ||
    pve_check_fail "the $label simulation on $node states $stated package(s) to remove but lists $PVE_REMOVAL_COUNT: do not trust it"
  running="$(pve_collect "$node" uname -r)" || pve_check_fail "cannot read the running kernel of $node"
  [[ -n "$running" ]] || pve_check_fail "cannot read the running kernel of $node: empty answer"
  PVE_REMOVALS="${list//$'\n'/ }"
  # membership tests on a variable: no early-exiting reader in a pipeline (SIGPIPE under pipefail)
  case $'\n'"$list"$'\n' in
    *$'\n'proxmox-ve$'\n'*|*$'\n'pve-manager$'\n'*|*$'\n'qemu-server$'\n'*|*$'\n'pve-container$'\n'*)
      pve_check_fail "the $label simulation on $node would remove part of the Proxmox stack ($PVE_REMOVALS): do not run it" ;;
    *$'\n'"proxmox-kernel-$running"$'\n'*|*$'\n'"proxmox-kernel-$running-signed"$'\n'*|*$'\n'"pve-kernel-$running"$'\n'*)
      pve_check_fail "the $label simulation on $node would remove the running kernel $running ($PVE_REMOVALS): do not run it" ;;
  esac
}

# pve_ct_exec NODE VMID ARGV...: a read inside a container through the collect alias; the whole
# command must be a line of local/collect.allow.
pve_ct_exec() {
  local node="$1" id="$2"
  shift 2
  pve_collect "$node" pct exec "$id" -- "$@"
}

# pve_ct_exec_admin NODE VMID ARGV...: the same through the admin alias (changing tools only).
pve_ct_exec_admin() {
  local node="$1" id="$2"
  shift 2
  pve_admin "$node" pct exec "$id" -- "$@"
}

# pve_apt_fetch NODE DIR: save the node's APT source files into DIR as DIR/1, DIR/2... and list
# "n path" in DIR/index (sources.list first, when it exists, then sources.list.d by name). Only
# cat's exit 1 means that sources.list is absent; any other failed read fails the whole fetch.
pve_apt_fetch() {
  local node="$1" dir="$2" list name n=0 rc=0
  : > "$dir/index"
  pve_collect "$node" cat /etc/apt/sources.list > "$dir/0" 2> "$dir/0.err" || rc=$?
  case "$rc" in
    0) printf '0 /etc/apt/sources.list\n' >> "$dir/index" ;;
    1) ;;
    *) cat "$dir/0.err" >&2; return "$rc" ;;
  esac
  list="$(pve_collect "$node" ls /etc/apt/sources.list.d)" || return
  while read -r name; do
    [[ "$name" =~ ^[A-Za-z0-9_.-]+\.(list|sources)$ ]] || continue
    n=$((n + 1))
    pve_collect "$node" cat "/etc/apt/sources.list.d/$name" > "$dir/$n" || return
    printf '%d /etc/apt/sources.list.d/%s\n' "$n" "$name" >> "$dir/index"
  done < <(LC_ALL=C sort <<< "$list")
}

# _pve_apt_file_enabled FILE PATH URI_RE COMP_RE: does FILE (remote PATH) have an enabled entry
# whose URI matches URI_RE and whose components match COMP_RE? One-line .list or deb822 .sources.
_pve_apt_file_enabled() {
  local deb822=0
  [[ "$2" == *.sources ]] && deb822=1
  URI_RE="$3" COMP_RE="$4" awk -v deb822="$deb822" '
    function stanza_end() { if (uri && comp && !off) hit = 1; uri = 0; comp = 0; off = 0 }
    deb822 == 1 {
      if ($0 ~ /^[[:space:]]*$/) { stanza_end(); next }
      key = tolower($1)
      if (key == "uris:" && $0 ~ ENVIRON["URI_RE"]) uri = 1
      if (key == "components:" && $0 ~ ENVIRON["COMP_RE"]) comp = 1
      if (key == "enabled:" && tolower($2) ~ /^(no|false|0)$/) off = 1
      next
    }
    { line = $0; sub(/#.*/, "", line) }
    line ~ /^[[:space:]]*deb(-src)?[[:space:]]/ && line ~ ENVIRON["URI_RE"] && line ~ ENVIRON["COMP_RE"] { hit = 1 }
    END { if (deb822 == 1) stanza_end(); exit !hit }' "$1"
}

# pve_apt_enabled DIR URI_RE COMP_RE -> the remote paths (from pve_apt_fetch) with an enabled entry.
pve_apt_enabled() {
  local dir="$1" n path
  while read -r n path; do
    if _pve_apt_file_enabled "$dir/$n" "$path" "$2" "$3"; then
      printf '%s\n' "$path"
    fi
  done < "$dir/index"
}

# pve_apt_suites DIR URI_RE COMP_RE -> "PATH SUITE" for each suite of each enabled entry that
# pve_apt_enabled would match (a deb822 Suites field may name several).
pve_apt_suites() {
  local dir="$1" n path deb822
  while read -r n path; do
    deb822=0
    [[ "$path" == *.sources ]] && deb822=1
    URI_RE="$2" COMP_RE="$3" awk -v deb822="$deb822" -v path="$path" '
      function stanza_end(   i) {
        if (uri && comp && !off) for (i = 1; i <= ns; i++) print path, suites[i]
        uri = 0; comp = 0; off = 0; ns = 0
      }
      deb822 == 1 {
        if ($0 ~ /^[[:space:]]*$/) { stanza_end(); next }
        key = tolower($1)
        if (key == "uris:" && $0 ~ ENVIRON["URI_RE"]) uri = 1
        if (key == "components:" && $0 ~ ENVIRON["COMP_RE"]) comp = 1
        if (key == "enabled:" && tolower($2) ~ /^(no|false|0)$/) off = 1
        if (key == "suites:") for (i = 2; i <= NF; i++) suites[++ns] = $i
        next
      }
      { line = $0; sub(/#.*/, "", line) }
      line ~ /^[[:space:]]*deb(-src)?[[:space:]]/ && line ~ ENVIRON["URI_RE"] && line ~ ENVIRON["COMP_RE"] {
        gsub(/\[[^]]*\]/, " ", line); split(line, f); print path, f[3]
      }
      END { if (deb822 == 1) stanza_end() }' "$dir/$n"
  done < "$dir/index"
}

# pve_apt_disable FILE PATH URI_RE: print FILE with every enabled entry matching URI_RE disabled:
# "# " before a one-line entry; "Enabled: no" in a deb822 stanza.
pve_apt_disable() {
  local deb822=0
  [[ "$2" == *.sources ]] && deb822=1
  URI_RE="$3" awk -v deb822="$deb822" '
    function flush(   i) {
      if (n == 0) return
      if (uri && !off) { if (en) lines[en] = "Enabled: no"; else lines[++n] = "Enabled: no" }
      for (i = 1; i <= n; i++) print lines[i]
      n = 0; uri = 0; off = 0; en = 0
    }
    deb822 == 1 {
      if ($0 ~ /^[[:space:]]*$/) { flush(); print; next }
      lines[++n] = $0
      key = tolower($1)
      if (key == "uris:" && $0 ~ ENVIRON["URI_RE"]) uri = 1
      if (key == "enabled:") { en = n; if (tolower($2) ~ /^(no|false|0)$/) off = 1 }
      next
    }
    { line = $0; sub(/#.*/, "", line) }
    line ~ /^[[:space:]]*deb(-src)?[[:space:]]/ && line ~ ENVIRON["URI_RE"] { print "# " $0; next }
    { print }
    END { if (deb822 == 1) flush() }' "$1"
}

# pve_quorum NODE: the node's cluster state, in globals (call it without $(...)):
#   PVE_QUORUM_STATE     cluster | standalone | unreadable
#   PVE_QUORUM_EXPECTED, PVE_QUORUM_TOTAL, PVE_QUORUM_QUORATE (Yes, No or unknown) for a cluster
#   PVE_QUORUM_COROSYNC  the text of /etc/pve/corosync.conf on a cluster
#   PVE_QUORUM_NODES     the listing of /etc/pve/nodes on a standalone node
#   PVE_QUORUM_WHAT, PVE_QUORUM_RC  the read that made it unreadable and its exit code (0 when the
#                        answer could not be parsed)
# A node without /etc/pve/corosync.conf (cat exits 1 and prints nothing) is standalone, but only
# when /etc/pve/nodes lists at least one node: with pmxcfs (pve-cluster) down, /etc/pve is an empty
# directory, so a cluster node has no corosync.conf either. On a cluster, `pvecm status` is parsed whatever its exit code: corosync-quorumtool exits 2 when the
# cluster is not quorate and 1 when corosync is down. The stderr of the reads is replayed only when
# the state is unreadable.
pve_quorum() {
  local node="$1" out err rc=0 votes
  PVE_QUORUM_STATE=unreadable
  PVE_QUORUM_EXPECTED=""
  PVE_QUORUM_TOTAL=""
  PVE_QUORUM_QUORATE=""
  PVE_QUORUM_COROSYNC=""
  PVE_QUORUM_NODES=""
  PVE_QUORUM_WHAT=/etc/pve/corosync.conf
  PVE_QUORUM_RC=0
  err="$(mktemp)"
  pve_cleanup_add "$err"
  out="$(pve_collect "$node" cat /etc/pve/corosync.conf 2> "$err")" || rc=$?
  if ((rc == 1)) && [[ -z "$out" ]]; then
    PVE_QUORUM_WHAT=/etc/pve/nodes
    rc=0
    out="$(pve_collect "$node" ls /etc/pve/nodes 2> "$err")" || rc=$?
    if ((rc == 0)) && [[ -n "$out" ]]; then
      PVE_QUORUM_STATE=standalone
      PVE_QUORUM_NODES="$out"
    else
      PVE_QUORUM_RC="$rc"
      cat "$err" >&2
    fi
    rm -f "$err"
    return 0
  fi
  if ((rc != 0)) || [[ -z "$out" ]]; then
    PVE_QUORUM_RC="$rc"
    cat "$err" >&2
    rm -f "$err"
    return 0
  fi
  PVE_QUORUM_COROSYNC="$out"
  PVE_QUORUM_WHAT="pvecm status"
  rc=0
  out="$(pve_collect "$node" pvecm status 2> "$err")" || rc=$?
  if ((rc != 126 && rc != 255)) && votes="$(pve_parse_pvecm_status <<< "$out")"; then
    read -r PVE_QUORUM_EXPECTED PVE_QUORUM_TOTAL PVE_QUORUM_QUORATE <<< "$votes"
    PVE_QUORUM_STATE=cluster
  else
    # an answer without vote lines is unreadable whatever its exit code (0 included)
    PVE_QUORUM_RC="$rc"
    cat "$err" >&2
  fi
  rm -f "$err"
  return 0
}

# pve_quorum_members NODE: after pve_quorum, set PVE_QUORUM_MEMBERS to the node names, sorted and
# space-separated: `pvecm nodes` on a cluster (parsed whatever its exit code, as pvecm status),
# the /etc/pve/nodes listing pve_quorum read on a standalone node (its real Proxmox name, which the
# inventory may not use). PVE_QUORUM_LOCAL is the member that answered: the "(local)" line on a
# cluster, the only name on a standalone node, empty when it cannot be told. Returns 1, with the
# stderr visible, when the list cannot be read or is empty; PVE_QUORUM_WHAT and PVE_QUORUM_RC then
# name that read.
pve_quorum_members() {
  local node="$1" out rc=0
  PVE_QUORUM_MEMBERS=""
  PVE_QUORUM_LOCAL=""
  case "$PVE_QUORUM_STATE" in
    cluster)
      PVE_QUORUM_WHAT="pvecm nodes"
      out="$(pve_collect "$node" pvecm nodes)" || rc=$?
      PVE_QUORUM_RC="$rc"
      ((rc != 126 && rc != 255)) || return 1
      PVE_QUORUM_MEMBERS="$(pve_parse_pvecm_nodes <<< "$out" | paste -sd' ' -)"
      PVE_QUORUM_LOCAL="$(pve_parse_pvecm_local <<< "$out")"
      ;;
    standalone)
      PVE_QUORUM_MEMBERS="$(awk 'NF == 1 && $1 ~ /^[A-Za-z0-9][A-Za-z0-9.-]*$/' <<< "$PVE_QUORUM_NODES" |
        LC_ALL=C sort | paste -sd' ' -)"
      [[ "$PVE_QUORUM_MEMBERS" == *" "* ]] || PVE_QUORUM_LOCAL="$PVE_QUORUM_MEMBERS"
      ;;
    *) return 1 ;;
  esac
  [[ -n "$PVE_QUORUM_MEMBERS" ]]
}

# Collector reads with the failure rules of docs/proxmox-toolkit.md (Reading), shared by
# pve-health and pve-capacity. The caller sets PVE_READ_NODE; each read sets PVE_READ_OUT and
# PVE_READ_RC. A failure the report must show calls pve_read_failed WHAT, which a collector
# redefines (pve-health: a CRIT finding; pve-capacity: a "could not read" line).
PVE_READ_NODE=""
PVE_READ_OUT=""
PVE_READ_RC=0
_PVE_READ_ERR=""

pve_read_failed() {
  log_error "could not read $1 on $PVE_READ_NODE"
}

# pve_read ARGV...: one read (call it without $(...)). The error text of a transport failure
# (255) or a dispatcher refusal (126) is replayed on stderr; any other stays for pve_read_replay.
pve_read() {
  if [[ -z "$_PVE_READ_ERR" ]]; then
    _PVE_READ_ERR="$(mktemp)"
    pve_cleanup_add "$_PVE_READ_ERR"
  fi
  PVE_READ_RC=0
  PVE_READ_OUT="$(pve_collect "$PVE_READ_NODE" "$@" 2> "$_PVE_READ_ERR")" || PVE_READ_RC=$?
  if ((PVE_READ_RC == 126 || PVE_READ_RC == 255)); then
    cat "$_PVE_READ_ERR" >&2
  fi
  return "$PVE_READ_RC"
}

# pve_read_replay: the stderr of the last pve_read, when pve_read kept it (exit code not 126/255).
pve_read_replay() {
  if ((PVE_READ_RC != 0 && PVE_READ_RC != 126 && PVE_READ_RC != 255)); then
    cat "$_PVE_READ_ERR" >&2
  fi
}

# pve_must_read WHAT ARGV...: a read that has to succeed; any failure calls pve_read_failed.
pve_must_read() {
  local what="$1"
  shift
  if pve_read "$@"; then
    return 0
  fi
  pve_read_replay
  pve_read_failed "$what"
  return 1
}

# pve_opt_read WHAT ARGV...: a read whose ordinary failure means "not applicable" (no ZFS); a
# transport failure or refusal still calls pve_read_failed. Returns 1 for that, 2 for the former.
pve_opt_read() {
  local what="$1"
  shift
  if pve_read "$@"; then
    return 0
  fi
  if ((PVE_READ_RC == 126 || PVE_READ_RC == 255)); then
    pve_read_failed "$what"
    return 1
  fi
  return 2
}

# pve_zpool_read STATUS: `zpool list` through pve_opt_read. When STATUS (the output of `pvesm
# status`) lists a zfspool storage, any failure is a failed read, never "no ZFS": zfsutils ships
# with Proxmox VE and `zpool list` exits 0 when there is no pool. Returns as pve_opt_read.
pve_zpool_read() {
  local rc=0
  pve_opt_read zpool zpool list -Hp -o name,size,alloc,free,cap,health || rc=$?
  if ((rc == 2)) && pve_parse_pvesm_status <<< "$1" | awk '$2 == "zfspool" { f = 1 } END { exit !f }'; then
    pve_read_replay
    pve_read_failed zpool
    return 1
  fi
  return "$rc"
}

# pve_collect_hash: the version a dispatcher installed from this repo reports.
pve_collect_hash() {
  local -a files=("$PVE_ROOT/remote/homelab-collect" "$PVE_ROOT/remote/collect.allow")
  if [[ -f "$PVE_ROOT/local/collect.allow" ]]; then
    files+=("$PVE_ROOT/local/collect.allow")
  fi
  cat "${files[@]}" | pve_sha256 | cut -c1-16
}
