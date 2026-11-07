# shellcheck shell=bash
# shellcheck disable=SC2034  # globals exported to the tools
# Parsers: Proxmox command output on stdin, normalized lines on stdout. Decimal commas (from
# non-English locales on paths without the dispatcher) become dots. Plus small helpers.

# pct list -> "vmid status name"; the optional Lock column is skipped.
pve_parse_pct_list() {
  awk '$1 ~ /^[0-9]+$/ { name = (NF >= 4) ? $4 : $3; print $1, $2, (name == "" ? "-" : name) }'
}

# qm list -> "vmid status name"; the columns are counted from the right, since a VM without a name
# is listed as "VM <vmid>" (two words): its name becomes "-".
pve_parse_qm_list() {
  awk '$1 ~ /^[0-9]+$/ && NF >= 6 { print $1, $(NF - 3), (NF == 6 ? $2 : "-") }'
}

# pvesm status -> "name type status total_kib used_kib avail_kib pct"; pct is "-" unless active.
pve_parse_pvesm_status() {
  awk 'NR > 1 && NF >= 7 {
    pct = $7; gsub(/%/, "", pct); gsub(/,/, ".", pct)
    if ($3 != "active" || pct !~ /^[0-9.]+$/) pct = "-"
    print $1, $2, $3, $4, $5, $6, pct
  }'
}

# pvesm list -> "volid format type size vmid"; vmid is "-" when empty.
pve_parse_pvesm_list() {
  awk 'NR > 1 && NF >= 4 { print $1, $2, $3, $4, (NF >= 5 ? $5 : "-") }'
}

# lvs (thin pools) -> "vg lv size_bytes data_pct meta_pct" ("-" for a percentage an inactive pool does not report)
pve_parse_lvs_thinpools() {
  awk 'NF >= 3 {
    size = $3; sub(/[.,]0*$/, "", size)
    data = (NF >= 4) ? $4 : "-"; meta = (NF >= 5) ? $5 : "-"
    gsub(/,/, ".", data); gsub(/,/, ".", meta)
    print $1, $2, size, data, meta
  }'
}

# lvs -> "lv vg size_bytes data_pct" (data_pct "-" for a volume that is not thin)
pve_parse_lvs() {
  awk 'NF >= 3 {
    size = $3; sub(/[.,]0*$/, "", size)
    data = (NF >= 4) ? $4 : "-"; gsub(/,/, ".", data)
    print $1, $2, size, data
  }'
}

# vgs -> "vg free_bytes"
pve_parse_vgs() {
  awk 'NF >= 2 { free = $2; sub(/[.,]0*$/, "", free); print $1, free }'
}

# zpool list -Hp (tab-separated) -> "name size alloc free cap health"
pve_parse_zpool() {
  awk -F'\t' 'NF >= 6 { print $1, $2, $3, $4, $5, $6 }'
}

# pvecm status -> "expected total quorate"; exit 1 when there are no vote lines (standalone).
pve_parse_pvecm_status() {
  awk -F: '
    /^Expected votes:/ { gsub(/[[:space:]]/, "", $2); expected = $2 }
    /^Total votes:/    { gsub(/[[:space:]]/, "", $2); total = $2 }
    /^Quorate:/        { gsub(/[[:space:]]/, "", $2); quorate = $2 }
    END {
      if (expected == "" || total == "") exit 1
      print expected, total, (quorate == "" ? "unknown" : quorate)
    }'
}

# pvecm nodes -> member names, sorted
pve_parse_pvecm_nodes() {
  awk '$1 ~ /^[0-9]+$/ && NF >= 3 { print $3 }' | LC_ALL=C sort
}

# pvecm nodes -> the name on the "(local)" line (the node that answered)
pve_parse_pvecm_local() {
  awk '$1 ~ /^[0-9]+$/ && NF >= 4 && $4 == "(local)" { print $3; exit }'
}

# corosync.conf -> the cluster name
pve_parse_cluster_name() {
  awk '$1 == "cluster_name:" { print $2; exit }'
}

# storage.cfg -> "name|type|nodes|shared|vgname|content"
pve_parse_storage_cfg() {
  awk '
    function flush() { if (name != "") print name "|" type "|" nodes "|" shared "|" vg "|" content }
    /^[a-z0-9]+:[[:space:]]/ {
      flush(); type = $1; sub(/:$/, "", type); name = $2
      nodes = ""; shared = ""; vg = ""; content = ""; next
    }
    $1 == "nodes"   { nodes = $2 }
    $1 == "shared"  { shared = $2 }
    $1 == "vgname"  { vg = $2 }
    $1 == "content" { content = $2 }
    END { flush() }'
}

# pct/qm listsnapshot -> "name YYYY-MM-DDTHH:MM:SS" (or "name -"); "current" is skipped.
pve_parse_snapshots() {
  awk '{
    sub(/^[[:space:]`>|-]+/, "")
    if ($1 == "" || $1 == "current") next
    date = "-"
    if ($2 ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$/ && $3 ~ /^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]$/)
      date = $2 "T" $3
    print $1, date
  }'
}

# pct/qm config -> "key storage volume size" for disks; bind mounts, CD-ROMs and "none" skipped.
pve_parse_config_volumes() {
  awk -F': ' '
    $1 ~ /^(rootfs|mp[0-9]+|unused[0-9]+|scsi[0-9]+|nvme[0-9]+|virtio[0-9]+|sata[0-9]+|ide[0-9]+|efidisk0|tpmstate0)$/ {
      value = $2
      if (value ~ /media=cdrom/ || value ~ /^none/) next
      n = split(value, parts, ",")
      volume = parts[1]
      colon = index(volume, ":")
      if (colon == 0) next
      size = "-"
      for (i = 2; i <= n; i++) if (parts[i] ~ /^size=/) size = substr(parts[i], 6)
      print $1, substr(volume, 1, colon - 1), substr(volume, colon + 1), size
    }'
}

# pve_config_value KEY: the value of KEY in a pct/qm config on stdin.
pve_config_value() {
  awk -F': ' -v key="$1" '$1 == key { print $2; exit }'
}

# pve_clean_description TEXT: a guest description (percent-encoded, often HTML) as one line:
# decoded, control characters and tags removed, whitespace collapsed, cut at 160 characters with
# "…" (characters in a UTF-8 locale, bytes otherwise). Prints nothing when no text is left.
pve_clean_description() {
  local out
  # one pass: backslashes escaped, %XX turned into \xXX for printf %b (a NUL cannot be held)
  out="$(printf '%s' "$1" | LC_ALL=C sed -E 's/\\/\\\\/g; s/%00//g; s/%([0-9A-Fa-f]{2})/\\x\1/g')"
  out="$(printf '%b' "$out" | LC_ALL=C tr '[:cntrl:]' ' ' | LC_ALL=C sed 's/<[^>]*>/ /g' | tr -s ' ')"
  out="${out#"${out%%[! ]*}"}"
  out="${out%"${out##*[! ]}"}"
  if ((${#out} > 160)); then
    out="$(_pve_utf8_trim "${out:0:160}")"
    out="${out%"${out##*[! ]}"}…"
  fi
  [[ -z "$out" ]] || printf '%s\n' "$out"
}

# _pve_utf8_trim TEXT: TEXT without a trailing incomplete UTF-8 sequence, counted in bytes (a cut
# made in a locale that is not UTF-8 can end inside a character).
_pve_utf8_trim() (
  LC_ALL=C
  local s="$1" i=1 byte need
  while ((i <= 4 && i <= ${#s})); do
    printf -v byte '%d' "'${s: -$i:1}"
    ((byte >= 128)) || break
    if ((byte >= 192)); then
      if ((byte >= 240)); then need=4; elif ((byte >= 224)); then need=3; else need=2; fi
      ((i >= need)) || s="${s:0:${#s}-i}"
      break
    fi
    i=$((i + 1))
  done
  printf '%s' "$s"
)

# free -b -> "mem_total mem_used swap_total swap_used"
pve_parse_free() {
  awk '$1 == "Mem:" { mt = $2; mu = $3 } $1 == "Swap:" { st = $2; su = $3 }
       END { print (mt == "" ? 0 : mt), (mu == "" ? 0 : mu), (st == "" ? 0 : st), (su == "" ? 0 : su) }'
}

# df -P -B1 / -> "size used avail pct"
pve_parse_df() {
  awk 'NR == 2 { pct = $5; sub(/%/, "", pct); print $2, $3, $4, pct }'
}

# apt list --upgradable -> "package old new"
pve_parse_upgradable() {
  awk '/\[upgradable from: / { split($1, name, "/"); old = $NF; sub(/\]$/, "", old); print name[1], old, $2 }'
}

# pve_parse_pkg_sim apt|apk: how many packages a simulation would upgrade or install.
pve_parse_pkg_sim() {
  if [[ "$1" == apk ]]; then
    awk '/^\([0-9]+\/[0-9]+\) (Upgrading|Installing) / { n++ } END { print n + 0 }'
  else
    awk '/^Inst / { n++ } END { print n + 0 }'
  fi
}

# The summary line every apt-get run or simulation prints (in the C locale); its absence means the
# output cannot be trusted.
PVE_APT_SUMMARY_RE='^[0-9]+ upgraded, [0-9]+ newly installed, [0-9]+ to remove and [0-9]+ not upgraded\.'

# pve_parse_pkg_removals: the names of the packages an apt simulation would remove (Remv lines).
pve_parse_pkg_removals() {
  awk '/^Remv / { print $2 }'
}

# pve_parse_new_kernels: the versioned kernel packages an apt simulation would newly install (an Inst
# line with no installed version in brackets), e.g. proxmox-kernel-6.8.12-11-pve-signed.
pve_parse_new_kernels() {
  awk '/^Inst (proxmox|pve)-kernel-[0-9][^ ]* \(/ { print $2 }'
}

# ls /boot -> the newest kernel version among vmlinuz-*
pve_newest_kernel() {
  sed -n 's/^vmlinuz-//p' | LC_ALL=C sort -V | tail -n 1
}

# pveversion -> the major version (8, 9)
pve_major_version() {
  sed -n 's|^pve-manager/\([0-9][0-9]*\)\..*|\1|p' | head -n 1
}

# Proxmox Backup Server volid: <storage>:backup/<ct|vm>/<vmid>/<ISO time, UTC>Z
_PVE_PBS_VOLID_RE=':backup/(ct|vm)/[0-9]+/([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})Z$'

# pve_backup_volid_date VOLID -> "YYYY-MM-DDTHH:MM:SS" from a vzdump archive name (local time) or a
# Proxmox Backup Server volid (UTC, as PBS names it); exit 1 otherwise.
pve_backup_volid_date() {
  local re='vzdump-(lxc|qemu|openvz)-[0-9]+-([0-9]{4})_([0-9]{2})_([0-9]{2})-([0-9]{2})_([0-9]{2})_([0-9]{2})'
  if [[ "$1" =~ $_PVE_PBS_VOLID_RE ]]; then
    printf '%s\n' "${BASH_REMATCH[2]}"
    return 0
  fi
  [[ "$1" =~ $re ]] || return 1
  printf '%s-%s-%sT%s:%s:%s\n' "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[4]}" \
    "${BASH_REMATCH[5]}" "${BASH_REMATCH[6]}" "${BASH_REMATCH[7]}"
}

# pve_backup_volid_type VOLID -> ct or vm, from a vzdump archive name or a Proxmox Backup Server
# volid; exit 1 otherwise.
pve_backup_volid_type() {
  local re='vzdump-(lxc|qemu|openvz)-[0-9]+-'
  if [[ "$1" =~ $_PVE_PBS_VOLID_RE ]]; then
    echo "${BASH_REMATCH[1]}"
    return 0
  fi
  [[ "$1" =~ $re ]] || return 1
  if [[ "${BASH_REMATCH[1]}" == qemu ]]; then echo vm; else echo ct; fi
}

# pve_days YYYY-MM-DD[...] -> days since 1970-01-01 (proleptic Gregorian; no date -d needed).
pve_days() {
  [[ "$1" =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2}) ]] || return 1
  local y=$((10#${BASH_REMATCH[1]})) m=$((10#${BASH_REMATCH[2]})) d=$((10#${BASH_REMATCH[3]}))
  local era yoe doy doe
  ((m <= 2)) && y=$((y - 1))
  era=$(((y >= 0 ? y : y - 399) / 400))
  yoe=$((y - era * 400))
  doy=$(((153 * ((m + 9) % 12) + 2) / 5 + d - 1))
  doe=$((yoe * 365 + yoe / 4 - yoe / 100 + doy))
  printf '%s\n' $((era * 146097 + doe - 719468))
}

# pve_gib BYTES -> GiB with two decimals
pve_gib() {
  LC_ALL=C awk -v b="${1:-0}" 'BEGIN { printf "%.2f\n", b / 1073741824 }'
}

# pve_num_gt A B: true when the number A is greater than B (decimals allowed).
pve_num_gt() {
  LC_ALL=C awk -v a="$1" -v b="$2" 'BEGIN { exit !((a + 0) > (b + 0)) }'
}

# pve_size_bytes SIZE: a Proxmox size such as 32G, 4M, 512 -> bytes; exit 1 when not an integer size.
pve_size_bytes() {
  [[ "$1" =~ ^([0-9]+)([KMGT]?)$ ]] || return 1
  local n=$((10#${BASH_REMATCH[1]})) mult=1
  case "${BASH_REMATCH[2]}" in
    K) mult=1024 ;;
    M) mult=$((1024 ** 2)) ;;
    G) mult=$((1024 ** 3)) ;;
    T) mult=$((1024 ** 4)) ;;
  esac
  printf '%s\n' $((n * mult))
}

# pve_indent: prefix every non-empty line with two spaces.
pve_indent() {
  awk 'length { print "  " $0 }'
}

# pve_sha256: sha256 of stdin, as sha256sum prints it.
pve_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum
  else
    shasum -a 256
  fi
}
