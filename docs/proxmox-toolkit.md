# Proxmox toolkit

Command-line tools that read and change a Proxmox VE 8 or 9 homelab from your admin machine over
SSH, built so an agent can use them safely. Reads go through a key that can only run a fixed list
of read-only commands on each host; changes go through a second key, one target at a time, after a
dry run and an explicit confirmation.

| Tool | Kind | What |
|---|---|---|
| `bin/pve-state <vmid\|node>` | read | The state of one guest or node in a fixed order: the collector of `infra-change` baselines and afters |
| `bin/pve-health` | read | Daily health: storage use, ZFS pools, memory, quorum, stopped guests, backup ages |
| `bin/pve-capacity` | read | Thin pools, disks per storage, orphaned volumes, `storage.cfg` against reality, quorum, recommendations |
| `bin/pve-selftest` | read | Is this installation able to collect safely? Plus your own checks |
| `bin/pve-discover [--seed ALIAS]` | read | Members, storages and guests in a fixed order; with `--seed`, writes `inventory/nodes` on a fresh install |
| `bin/pve-snapshot <vmid> <name>` | change | Snapshot one guest |
| `bin/pve-backup <vmid>` | change | On-demand vzdump of one guest |
| `bin/pve-update-host <node>` | change | `apt-get dist-upgrade` of one node (`--simulate` reads only) |
| `bin/pve-update-ct <vmid>` | change | Package upgrade inside one container (`--snapshot`, `--simulate`) |
| `bin/pve-cleanup <node\|vmid>` | change | `apt-get autoremove` and `clean` |
| `bin/pve-move-disk <vmid> <storage>` | change | Move one volume; the source stays as an unused disk unless `--delete-source` |
| `bin/pve-repo-setup <node>` | change | Enterprise repositories off, `pve-no-subscription` on (`.list` on 8, deb822 on 9) |
| `bin/pve-collect-install <node>` | change | Install the dispatcher and its allowlists on a host |

Every tool has `--help`. Requirements on the admin machine: Bash 4.4 or newer (macOS: `brew
install bash`), OpenSSH, and `sshpass` only for the password fallback.

**Proxmox VE 9:** Proxmox VE 9 support is experimental. The PVE 9 test fixtures have not yet been
compared with a real PVE 9 node (`pveversion`, `pvecm`, the deb822 sources); `bin/pve-selftest`
and `bin/pve-repo-setup` print a warning on a PVE 9 node, so run `--simulate` and `--dry-run`
before any change there. Proxmox VE 8 was verified on real nodes. apt 3 itself was
checked: in a Debian 13 container, apt 3.0.3 prints the same summary line, `The following packages
will be upgraded:` and `Inst`/`Conf` lines as apt 2 (only `Reading state information...` is
missing, and the toolkit does not read it); `Remv` lines were not observed. If apt's output
differs, `pve-update-host`, `pve-update-ct` and `pve-cleanup` fail closed with "no summary line"
before changing anything.

## Setup

1. **SSH aliases for one node.** Follow [`ssh-access.md`](ssh-access.md) for one node: one key for
   reads (`pve1`), one for changes (`pve1-admin`), both in `~/.ssh/config` with `BatchMode yes`.
   Every call the toolkit makes passes `-o ControlMaster=no -o ControlPath=none`: both aliases
   reach the same host, and a shared connection would mix the two keys. The admin alias must
   log in as **root**: the changing tools run `pct` and `qm` and install files with
   `install -o root`.
2. **Settings.** Copy `.env.local.example` to `.env.local` and set what you need
   (`PVE_BACKUP_STORAGE` at least). The file is read literally, never sourced.
3. **Inventory.** `bin/pve-discover --seed pve1` reads the cluster members through that alias,
   tests the alias `<member>` of every other member, and writes `inventory/nodes` with the ones
   that answer (it refuses when the file exists, and never uses an admin alias). Its report lists
   the members it left out: give each the aliases of step 1, then add its line. The format, if you
   write or edit the file by hand (tabs, `#` comments and CRLF endings are fine):

   ```text
   # node   collect   admin
   pve1
   pve2     pve2      pve2-admin
   ```

   The aliases default to `<node>` and `<node>-admin`; they must differ, and no alias may serve
   two nodes. No addresses or users here: they live in `~/.ssh/config`. Use the Proxmox name in
   the node column: `bin/pve-discover` compares it with the cluster members.
4. **Dispatcher.** `bin/pve-collect-install pve1 --dry-run`, then without `--dry-run`. Add the
   printed `command="/usr/local/bin/homelab-collect",restrict` prefix to the read key's line in
   `authorized_keys` by hand: the tool never edits that file. On a cluster, install on every node
   first: root's `authorized_keys` is shared.
5. **Check.** `bin/pve-selftest` must pass, including "the collect key is restricted".
6. **Agent permissions.** Only after step 5, pre-approve the read-only tools in your agent's
   local, uncommitted permission settings. Every agent has its own mechanism; for Claude Code it
   is `.claude/settings.local.json`:

   ```json
   { "permissions": { "allow": [
     "Bash(bin/pve-state:*)", "Bash(bin/pve-health:*)", "Bash(bin/pve-capacity:*)",
     "Bash(bin/pve-selftest:*)", "Bash(bin/pve-discover:*)"
   ] } }
   ```

   Never pre-approve a changing tool, `pve-selftest --admin`, or `ssh` to an admin alias.

The wiki side of steps 3 and later is the `llm-wiki` DISCOVER operation: it captures the report,
writes the first pages, and on later runs lists what changed without rewriting them.

## Reading

Collectors print the report on stdout (plain, sorted, absolute dates) and progress on stderr
(`--quiet` silences it). The same state gives the same bytes, so a report can be piped to
`bin/wiki-capture` and two captures can be diffed:

```bash
bin/pve-state 101 | bin/wiki-capture ct-101-baseline --origin "bin/pve-state 101"
```

Exit codes: 0 no critical finding, 1 a `CRIT` finding or an unreachable node, 2 a usage or
configuration error. Capture the exit code before any pipe.

`bin/pve-discover` without options is the reconciliation report: the members, storages and guests
of every node in `inventory/nodes`, with the inventory compared to the live members (`inventory:
unchanged`, or `differs: +<member not listed> -<listed node not a member>`). It never writes. A
node it cannot read is marked (`unreachable`, `guests not read: <node>`, `members not read:
<node>`): its guests are unknown, not gone. A `-<node>` whose node line says `unreachable` is
unknown too: an independent node that is off and a removed cluster member look the same. A node
listed under a name that is not its Proxmox name shows `<node> (Proxmox name <name>)` on its line
and `+<name> -<node>` in the comparison; rename the line in `inventory/nodes` to match. A
standalone node whose `/etc/pve/nodes` still holds the directory of an old name shows `+<old>` on
every run, until that directory is removed on the host (a change, through `infra-change`).

A read that fails, is refused by the dispatcher (126), cannot connect (255) or comes back empty
or unparseable is never shown as a normal section. `bin/pve-state` exits 1 (an empty status,
config, package list or storage list, a snapshot list without its `current` line, or `/boot`
without a kernel included); `bin/pve-health` and `bin/pve-capacity` print
`finding CRIT could not read <what> on <node>` (or `UNREACHABLE`) and exit 1. A node that does
not connect also gets a line on stderr with the last line ssh printed ("Permission denied
(publickey)", "Host key verification failed") and a pointer to [`ssh-access.md`](ssh-access.md);
`bin/pve-selftest` puts the same on its `FAIL` line. A failed `zpool list` means "no ZFS" only
when `pvesm status` lists no `zfspool` storage; otherwise it is `could not read zpool`.

Quorum is read the same way by every collector. A node without `/etc/pve/corosync.conf` (`cat`
exits 1 and prints nothing) is standalone only when `ls /etc/pve/nodes` lists a node: with the
cluster file system down (`pve-cluster` stopped), `/etc/pve` is an empty directory and a cluster
node has no `corosync.conf` either, so that is a failed read of `/etc/pve/nodes`. On a cluster, `pvecm status` is parsed whatever its
exit code (`corosync-quorumtool` exits 2 when the cluster is not quorate and 1 when corosync is
down): a cluster that is not quorate is CRIT, and an answer without vote lines, or a
`corosync.conf` that cannot be read, is a failed read, never "standalone".

`--node NODE` is common to every tool. A collector reports only that node. With a VMID it names
the guest's node: a tool reads every node to find a VMID and stops (exit 2, `VMID 101 is on pve1
and pve2; pass --node NODE`) when two nodes that are not one cluster both list it. It also stops
when it finds the VMID but another node could not be read, unless that node is a member of the
cluster of the node that lists it (a cluster keeps VMIDs unique): an independent node that is down
may hold a guest with the same VMID. A node listed in `inventory/nodes` under a name other than
its Proxmox name does not count as a member, so the tool stops; pass `--node`. A tool whose
target is a node refuses a different `--node`.

Some findings worth knowing:

- `bin/pve-capacity` reports an inactive thin pool as CRIT with an `lvchange -ay`
  recommendation, deduplicates recommendations per node, counts cloud-init and vmstate volumes
  as referenced, and draws no orphan conclusion when the snapshot list is unreadable or empty.
- It never calls a volume an orphan when the VMID in its name belongs to a guest on any readable
  node: `pct config` and `qm config` print the current config only, so a snapshot's disk or RAM
  state shows as `not in the current config of <type> <id> (may belong to a snapshot)`, without
  a recommendation. Logical volumes are checked against the guests of every node (shared LVM).
- It checks orphans only when it can see every guest of the cluster: when `pvecm nodes` names a
  member that `inventory/nodes` does not list (its disks on a shared storage would look
  unreferenced), or the members cannot be read, the orphan section says so and checks nothing.
- Its `storage.cfg` check takes the member names from `pvecm nodes` on a cluster and from
  `/etc/pve/nodes` on a standalone node (the real Proxmox name, which `inventory/nodes` may not
  use). `shared 1` on a `dir` storage is correct only for a network mount shared by all nodes;
  the advice says so instead of telling you to change it.
- `bin/pve-health` reads backup dates from vzdump archive names and from Proxmox Backup Server
  volids (`pbs:backup/ct/101/<time>Z`, a UTC time), and matches them by guest type and VMID.
- `bin/pve-state` prints "unavailable on <node>" for the backup storage when `pvesm status` does
  not list it on that node (a storage restricted by `nodes`), and "unavailable on <node> (storage
  inactive)" (or `disabled`) when it lists it as not active, so an outage of the backup storage
  does not block guest baselines; any failure to list an active storage exits 1. `bin/pve-health`
  makes the same distinction: unavailable and not active are a WARN, an active storage that cannot
  be listed is `finding CRIT could not read backups`. Any other storage that `pvesm status` lists
  as `inactive` is `finding WARN storage <name> is inactive on <node>`; a `disabled` storage was
  turned off on purpose and is no finding.
- `bin/pve-selftest` fails when a `pvecm`, `pvesm status` or `lvs` read is refused or fails, and
  warns (not fails) on an inactive thin pool.

## Changing

Every changing tool:

- changes **one target per run**; several targets are an `infra-change` change with one record per
  unit;
- with `--dry-run`, runs its checks (reads only) and prints the exact commands, the suggested
  collector, rollback and `infra-change` path, and the content of each file it would write
  (the dispatcher, which ships with the repo, as a line count and hash), and changes nothing;
- without `--yes`, asks on a terminal and refuses without one (exit 2): an agent passes `--yes`
  only after you approved that exact command;
- prints `step N/M:` before each command and `result: exit X` after it, stops at the first
  failure, and re-reads the state to verify the result (`verify:` lines);
- never deletes a rollback asset unless a flag says so.

Exit codes: 0 done or nothing to do, 1 a check, step or verification failed (or you declined),
2 usage, configuration, or confirmation needed without a terminal.

The one exception: `pve-update-ct --simulate` runs `pct exec` through the admin alias without
`--yes`, because a simulation inside a container needs it.

### Per-tool behavior

- **`pve-snapshot`**: a name is a letter, then letters, digits, `-` or `_`, 2 to 40 characters;
  `current`, `pending` and `vzdump` are reserved (exit 2).
- **`pve-update-host`**: `--simulate` runs `apt-get -s dist-upgrade`, lists the `Inst` and `Remv`
  lines and counts removals as a WARNING; it is a usage error together with `--dry-run`. It reads
  the package lists as they are (a `note:` line says so): the real run refreshes them first, so it
  can find more. When the upgrade installs a new kernel package, `--simulate` and `--dry-run` print
  `note: the upgrade installs a new kernel (...)`: it runs only after a reboot. Before a real run
  it warns when an enterprise repository is enabled, and when not every APT source could be read
  it says it cannot tell, instead of reporting none. A real run is two
  confirmed phases: step 1/2 `apt-get update`, then a fresh simulation and the removal guard
  (below), then step 2/2 `apt-get dist-upgrade`. When the removal list after `apt-get update`
  differs from the one shown before, the tool prints it; with `--yes` it then stops before
  `dist-upgrade`, since the approval covered the earlier list. Declining phase 2 prints
  `cancelled: apt-get update ran; dist-upgrade was not run`. It never reboots; the reboot is a
  change of its own. If the SSH connection drops during `dist-upgrade`, dpkg may be left
  half-configured: recover with `dpkg --configure -a` on the node, as an `infra-change` change of
  its own.
- **`pve-update-ct`**: the simulation runs `env LC_ALL=C apt-get -s dist-upgrade` (Alpine: `apk
  upgrade --simulate`) and must print a summary line. `--simulate` does not run `apt-get update`
  (a `note:` line says so), so a container whose lists were never refreshed can show 0 packages
  while the real run, which refreshes them first, upgrades many. `--snapshot` takes
  `pre-update-<date>-<time>` and is verified after the plan. `--simulate` together with
  `--dry-run` or `--snapshot` is a usage error.
- **`pve-cleanup`**: on a node it first runs `apt-get -s autoremove` through the collect alias and
  shows the removal list (also with `--dry-run`), then applies the removal guard. It reports the
  space freed, or that none was.
- **The removal guard** (shared by `pve-update-host` and `pve-cleanup`): the check fails when the
  simulation has no summary line, when its "N to remove" disagrees with its `Remv` lines, or when
  it would remove `proxmox-ve`, `pve-manager`, `qemu-server`, `pve-container` or a package of the
  running kernel (`proxmox-kernel-<uname -r>`, its `-signed` package, `pve-kernel-<uname -r>`).
- **`pve-move-disk`**: refuses a guest with a `lock:` and refuses `--delete-source` when the guest
  has snapshots (`parent:`). The source stays as an unused disk unless `--delete-source` is given.
  A container the tool shut down is restarted by a `recovery:` step if the move fails, but never
  when its state is unknown, in a dry run, or after you declined.
- **`pve-repo-setup`**: stops before writing anything when a file cannot be read with certainty:
  CRLF line endings, deb822 URIs on continuation lines, a field without a space after the colon,
  or a `proxmox.com` host name that is not all lowercase (even in a comment). It refuses a PVE
  major version that does not match the Debian codename (8 with bookworm, 9 with trixie) and
  refuses to overwrite a no-subscription file that does not enable the repository. A
  no-subscription entry for another suite (bookworm left on a trixie node during an upgrade) is
  never "already configured": the tool stops and asks you to fix it by hand. The final
  `apt-get update` runs with `LC_ALL=C` and is scanned for signature errors (`GPG error`,
  `EXPKEYSIG`, `BADSIG`).
- **`pve-collect-install`**: installs everything as `root:root`. It warns when the node's
  `local.allow` is about to be emptied (you have no `local/collect.allow`). Its rollback hint
  tells a first install from a re-install and keeps `use-sudo`. Never remove the dispatcher while
  an `authorized_keys` line forces it: the key would lose all access.

Every file the toolkit uploads (`pve_admin_put`) goes through a temporary file that `mktemp`
creates on the node, and is installed as `root:root` at an absolute path.

Each run writes an audit log of its actions (not its report) to `logs/` (`HOMELAB_LOG_DIR`, a
relative path is under the repository; `HOMELAB_LOG=0` turns it off): the file is mode 0600, and
a directory the tool creates is 0700.

## The dispatcher

`remote/homelab-collect` runs on each host as the read key's forced command. It runs a command
only when it matches a line of `/etc/homelab-collect/framework.allow` (from
`remote/collect.allow`, 34 rules) or `local.allow` (from your `local/collect.allow`) token by
token:

```text
pct config {id}
pvesm list {storage} --content backup
cat {aptfile}
```

- A literal token matches exactly; a field matches its pattern: `{id}` digits, `{storage}` and
  `{node}` names, `{snap}` a snapshot name, `{aptfile}` a file under `/etc/apt/sources.list.d/`
  ending in `.list` or `.sources`. A field is always a whole token, and never the first token:
  a line that starts with a field, or has one right after `pct exec <id> --`, is invalid. The
  check does not know wrappers: in a line such as `env {storage}`, `timeout 5 {node}` or
  `pct exec 101 -- sh -c {storage}` the field still becomes the program that runs. Never write
  a field after a command that runs its argument.
- The number of tokens must match; there is no "rest of the line".
- Characters outside letters, digits and `_ . / : = , @ + -` are refused, so `;`, `&&`, `|`,
  `$()`, quotes and redirections never reach a shell. A refusal exits 126 with
  `homelab-collect: refused: <command>`; the command is shown (and logged to syslog) quoted with
  `printf %q` and cut at 512 bytes, so a newline in it cannot forge a second log line.
- An invalid line makes the dispatcher refuse everything (it fails closed). Check a list with
  `bash remote/homelab-collect --check local/collect.allow`; test one command with
  `--match "pct config 101"`.
- `homelab-collect --version` prints a hash of the installed files (the first 16 hex digits of
  a sha256 over the dispatcher and both lists, concatenated); `pve-selftest` compares it
  with this repository and tells you to re-run `pve-collect-install` after an upstream merge that
  changes `remote/`.
- When the account is not root and the file `/etc/homelab-collect/use-sudo` exists, the dispatcher
  runs each allowed command as `sudo -n` ([`ssh-access.md`](ssh-access.md) §7). It first asks
  `sudo -n -l` whether sudoers allows the command and refuses one that it does not with
  `homelab-collect: refused (sudo): <command>` (exit 126), so every command of both lists must be
  in sudoers.

## Extending it in your installation

Your own scripts and checks live in `local/`, which upstream never ships; never edit the
framework files to customize. `examples/local/` is a working example.

| Path | Contract |
|---|---|
| `local/collect.allow` | Extra read-only commands, same grammar; `pve-collect-install` installs it |
| `local/bin/`, `local/lib/` | Your scripts, built on `lib/pve/` |
| `local/selftest.d/NN-name` | Executables `pve-selftest` runs in order from the repo root: exit 0 PASS, 1 FAIL, 77 SKIP; the first line printed is the summary; 60 s limit (`PVE_SELFTEST_TIMEOUT`), after which the check's process group gets TERM, then KILL 2 s later |

A script finds the library and checks its version:

```bash
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [[ "$root" != / && ! -f "$root/lib/pve/init.sh" ]]; do root="$(dirname "$root")"; done
source "$root/lib/pve/init.sh"
pve_require_api 1
```

A read inside a container goes through `pve_ct_exec <node> <vmid> <argv...>`, and the whole
command must be a line of `local/collect.allow` (`pct exec 101 -- pihole -v`). When a read needs
quotes or a pipe, install a small script inside the guest and allow only its call.

### Library API (`PVE_LIB_API=1`)

The functions in this table and the parsers below are the public API: a change that breaks one
raises `PVE_LIB_API`. Any other function, with or without a leading `_`, is internal and may
change in any release.

| Function | Use |
|---|---|
| `pve_init TOOL ARGS...` | Load `.env.local` and `inventory/nodes`, start the audit log |
| `pve_env_load [FILE]`, `pve_inventory_load [FILE]` | The two loads alone, without an audit log (a `selftest.d` check) |
| `pve_inventory_reset`, `pve_inventory_add NODE [COLLECT]` | An inventory in memory, with the checks of the file (the admin alias is `<node>-admin`) |
| `pve_alias_owner ALIAS` | Sets `REPLY` to the node that uses the alias; returns 1 when none does |
| `pve_cli_parse ARGS...` | `--help` (calls your `usage`), `--dry-run`, `--yes`, `--quiet`, `--node NODE` (`PVE_NODE_OPT`); the rest in `PVE_ARGS` |
| `pve_target_node NODE` | For a tool whose target is a node: known node, and `--node` (when given) names it |
| `pve_collect NODE ARGV...` | A read through the collect alias |
| `pve_admin NODE ARGV...` | A change through the admin alias |
| `pve_admin_put NODE LOCAL REMOTE MODE` | Install a local file at an absolute path on the node, as `root:root` |
| `pve_reachable NODE` | The connection probe; on failure `PVE_REACH_RC`, `PVE_REACH_ERR` (ssh's last line), and the reason on stderr |
| `pve_ct_exec NODE VMID ARGV...` | A read inside a container (needs a `local/collect.allow` line) |
| `pve_ct_exec_admin NODE VMID ARGV...` | The same through the admin alias (changing tools only) |
| `pve_find_guest VMID` | Sets `PVE_GUEST_NODE` and `PVE_GUEST_TYPE` (`ct` or `vm`); honors `--node`; exit 2 when two nodes list the VMID |
| `pve_quorum NODE`, `pve_quorum_members NODE` | `PVE_QUORUM_STATE` (`cluster`, `standalone`, `unreadable`) with the votes; `PVE_QUORUM_MEMBERS`; `PVE_QUORUM_LOCAL` (the member marked `(local)`, or the only name of a standalone node) |
| `pve_read`, `pve_must_read`, `pve_opt_read` | Collector reads with the failure rules above; redefine `pve_read_failed WHAT` to report a failure |
| `pve_zpool_read STATUS` | `zpool list` as `pve_opt_read`, but a failed read when `STATUS` (`pvesm status`) lists a `zfspool` storage |
| `pve_removal_guard NODE LABEL SIMULATION` | The removal guard of an apt simulation (`PVE_REMOVALS`, `PVE_REMOVAL_COUNT`) |
| `pve_guests NODE` | `vmid ct\|vm status name` lines |
| `pve_guest_has_snapshot NODE TYPE VMID NAME` | Three-state: 0 found, 1 absent, 2 unreadable; test for 2 before treating 1 as "absent" |
| `pve_check_ok`, `pve_check_warn`, `pve_check_fail` | Pre-check lines (`fail` exits 1) |
| `pve_plan_reset`, `pve_hint`, `pve_plan_add`, `pve_plan_put`, `pve_plan_execute` | The changing-tool contract: dry run, confirmation, steps, results |
| `pve_verify_ok`, `pve_verify_fail` | Verification lines (`fail` exits 1) |
| `log_info`, `log_warn`, `log_error`, `pve_die` | Messages on stderr and in the audit log |
| `pve_require_api N` | Stop with a clear message when the library is not API `N` |

The parsers (`pve_parse_*`) and helpers in `lib/pve/parse.sh` are public too; each documents its
output line in a comment.

## Tests and CI

The tests run the real Bash code against fake `ssh`, `scp` and `sshpass` that consult the real
dispatcher. CI runs the framework job on Python 3.10 and the latest 3.x, an `sshd` job with a real
`sshd` and stub `pct`/`pvesm` (it fails when its tests are skipped), and, in an installation, a
check of `local/collect.allow` when the file exists.

## Limits

- Orphan detection covers LVM volumes and volumes no guest config references; ZFS datasets are not
  checked.
- A backup volid does not name the node: two guests of the same type and VMID in two clusters
  that share one backup storage count each other's backups in `pve-health`.
- `pve-repo-setup` does not add a Ceph no-subscription repository.
- No tool reboots a node or creates or destroys a guest; those are changes you run through
  `infra-change` by hand.
- The password fallback (`HOMELAB_SSHPASS=1`) has no forced command: read-only then rests on the
  toolkit's code alone, and `pve-selftest` says so on every run.
