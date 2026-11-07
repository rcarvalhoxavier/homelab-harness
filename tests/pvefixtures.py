"""Fictional Proxmox VE outputs for the toolkit tests (the lab.example homelab).

Every output keeps the shape of the real command (headers, column order, separators) with
fictional names and addresses. ORIGIN records whether each version's shapes were compared with a
real node; a version that was not is "experimental", and must be declared so in the docs
(tests/test_pve_fixture_origin.py).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ORIGIN = {"8": "pve-manager/8.4.19, verified 2026-10-15",
          "9": "experimental: not yet compared with a real node (apt 3 summary checked in a Debian 13 CT)"}

LVS_POOLS = ("lvs --noheadings --units b --nosuffix -o vg_name,lv_name,lv_size,data_percent,"
             "metadata_percent --select segtype=thin-pool")
LVS_ALL = "lvs --noheadings --units b --nosuffix -o lv_name,vg_name,lv_size,data_percent"
VGS = "vgs --noheadings --units b --nosuffix -o vg_name,vg_free"
ZPOOL = "zpool list -Hp -o name,size,alloc,free,cap,health"

VERSIONS = {
    "8": {"manager": "8.4.1/2a5fa54a8503f96d", "kernel": "6.8.12-10-pve", "newer": "6.8.12-11-pve",
          "codename": "bookworm", "debian": "12", "ve": "8.4.0"},
    "9": {"manager": "9.0.10/deb1ca707ec72a89", "kernel": "6.14.11-3-pve", "newer": "6.14.11-4-pve",
          "codename": "trixie", "debian": "13", "ve": "9.0.0"},
}

GUESTS = {
    "pve1": {"ct": [("101", "running", "pihole")], "vm": []},
    "pve2": {"ct": [("102", "running", "pihole")], "vm": [("200", "running", "nas")]},
}

CONFIGS = {
    "101": """\
arch: amd64
cores: 1
features: nesting=1
hostname: pihole
memory: 512
net0: name=eth0,bridge=vmbr0,gw=10.0.0.1,hwaddr=BC:24:11:0A:00:65,ip=10.0.0.53/24,type=veth
onboot: 1
ostype: debian
parent: pre-upgrade
rootfs: local-lvm:vm-101-disk-0,size=8G
swap: 512
unprivileged: 1
""",
    "102": """\
arch: amd64
cores: 1
hostname: pihole
memory: 512
net0: name=eth0,bridge=vmbr0,gw=10.0.0.1,hwaddr=BC:24:11:0A:00:66,ip=10.0.0.54/24,type=veth
onboot: 1
ostype: debian
rootfs: local-lvm:vm-102-disk-0,size=8G
swap: 512
unprivileged: 1
""",
    "200": """\
boot: order=scsi0;ide2
cores: 2
ide2: local:iso/debian-12.7.0-amd64-netinst.iso,media=cdrom,size=631M
memory: 4096
meta: creation-qemu=9.0.2,ctime=1717236000
name: nas
net0: virtio=BC:24:11:0A:00:C8,bridge=vmbr0
ostype: l26
scsi0: local-lvm:vm-200-disk-0,iothread=1,size=32G
scsihw: virtio-scsi-single
smbios1: uuid=00000000-0000-4000-8000-000000000200
vmgenid: 5f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f
""",
}

SNAPSHOTS = {
    "101": "`-> pre-upgrade                 2026-06-01 10:00:00     no-description\n"
           " `-> current                                        You are here!\n",
    "102": "`-> current                                             You are here!\n",
    "200": "`-> current                                             You are here!\n",
}

BACKUPS = """\
Volid                                                          Format  Type            Size VMID
nas-backup:backup/vzdump-lxc-101-2026_06_29-23_00_03.tar.zst   tar.zst backup     412345678 101
nas-backup:backup/vzdump-lxc-101-2026_06_30-23_00_02.tar.zst   tar.zst backup     412398765 101
nas-backup:backup/vzdump-lxc-102-2026_06_30-23_10_04.tar.zst   tar.zst backup     398765432 102
nas-backup:backup/vzdump-qemu-200-2026_06_30-23_20_11.vma.zst  vma.zst backup    9876543210 200
"""

# A Proxmox Backup Server storage lists snapshots, not files: the volid ends in an ISO timestamp (UTC).
PBS_BACKUPS = """\
Volid                                     Format  Type            Size VMID
pbs:backup/ct/101/2026-06-29T23:00:03Z    pbs-ct  backup     412345678 101
pbs:backup/ct/101/2026-06-30T23:00:02Z    pbs-ct  backup     412398765 101
pbs:backup/ct/102/2026-06-30T23:10:04Z    pbs-ct  backup     398765432 102
pbs:backup/vm/200/2026-06-30T23:20:11Z    pbs-vm  backup    9876543210 200
"""

STORAGE_CFG = """\
dir: local
\tpath /var/lib/vz
\tcontent iso,vztmpl,backup

lvmthin: local-lvm
\tthinpool data
\tvgname pve
\tcontent rootdir,images

nfs: nas-backup
\texport /export/backup
\tpath /mnt/pve/nas-backup
\tserver 10.0.0.20
\tcontent backup
\tprune-backups keep-last=3
"""

COROSYNC = """\
logging {
  debug: off
  to_syslog: yes
}

nodelist {
  node {
    name: pve1
    nodeid: 1
    quorum_votes: 1
    ring0_addr: 10.0.0.11
  }
  node {
    name: pve2
    nodeid: 2
    quorum_votes: 1
    ring0_addr: 10.0.0.12
  }
}

quorum {
  provider: corosync_votequorum
  two_node: 1
}

totem {
  cluster_name: lab
  config_version: 2
  interface {
    linknumber: 0
  }
  ip_version: ipv4-6
  link_mode: passive
  secauth: on
  version: 2
}
"""

PVECM_STATUS = """\
Cluster information
-------------------
Name:             lab
Config Version:   2
Transport:        knet
Secure auth:      on

Quorum information
------------------
Date:             Wed Jul  1 09:00:00 2026
Quorum provider:  corosync_votequorum
Nodes:            2
Node ID:          0x0000000{nodeid}
Ring ID:          1.2c
Quorate:          Yes

Votequorum information
----------------------
Expected votes:   2
Highest expected: 2
Total votes:      2
Quorum:           1  
Flags:            2Node Quorate WaitForAll 

Membership information
----------------------
    Nodeid      Votes Name
0x00000001          1 10.0.0.11{local1}
0x00000002          1 10.0.0.12{local2}
"""

PVECM_NODES = """\

Membership information
----------------------
    Nodeid      Votes Name
         1          1 pve1{local1}
         2          1 pve2{local2}
"""

STANDALONE = {"stdout": "", "exit": 2,
              "stderr": "Error: Corosync config '/etc/pve/corosync.conf' does not exist - "
                        "is this node part of a cluster?\n"}

# A node that is in no cluster has no /etc/pve/corosync.conf: cat exits 1 and prints nothing.
COROSYNC_ABSENT = {"stdout": "", "exit": 1,
                   "stderr": "cat: /etc/pve/corosync.conf: No such file or directory\n"}

# pvecm status runs corosync-quorumtool, which exits 2 when the cluster is not quorate and
# still prints the whole status (pve1 alone, two_node not set).
PVECM_NOT_QUORATE = {"exit": 2, "stderr": "", "stdout": """\
Cluster information
-------------------
Name:             lab
Config Version:   2
Transport:        knet
Secure auth:      on

Quorum information
------------------
Date:             Wed Jul  1 09:00:00 2026
Quorum provider:  corosync_votequorum
Nodes:            1
Node ID:          0x00000001
Ring ID:          1.30
Quorate:          No

Votequorum information
----------------------
Expected votes:   2
Highest expected: 2
Total votes:      1
Quorum:           2 Activity blocked
Flags:            

Membership information
----------------------
    Nodeid      Votes Name
0x00000001          1 10.0.0.11 (local)
"""}

# corosync is down: pvecm prints its own header, corosync-quorumtool fails and exits 1.
PVECM_COROSYNC_DOWN = {"exit": 1, "stderr": "Cannot initialize CMAP service\n", "stdout": """\
Cluster information
-------------------
Name:             lab
Config Version:   2
Transport:        knet
Secure auth:      on

"""}


# When pmxcfs (pve-cluster) is down, /etc/pve is an empty directory: corosync.conf is missing on a
# cluster node too, and /etc/pve/nodes cannot be listed.
PMXCFS_DOWN_NODES = {"stdout": "", "exit": 2,
                     "stderr": "ls: cannot access '/etc/pve/nodes': No such file or directory\n"}


def pmxcfs_down(lab, node: str) -> None:
    """Make NODE a node whose cluster file system is not mounted."""
    lab.respond(node, "cat /etc/pve/corosync.conf", **COROSYNC_ABSENT)
    lab.respond(node, "ls /etc/pve/nodes", **PMXCFS_DOWN_NODES)


def standalone(lab, node: str) -> None:
    """Make NODE a node that is in no cluster."""
    lab.respond(node, "cat /etc/pve/corosync.conf", **COROSYNC_ABSENT)
    lab.respond(node, "pvecm status", **STANDALONE)
    lab.respond(node, "pvecm nodes", **STANDALONE)
    lab.respond(node, "ls /etc/pve/nodes", stdout=f"{node}\n")

SOURCES = {
    "8": {
        "/etc/apt/sources.list": (
            "deb http://deb.debian.org/debian bookworm main contrib\n"
            "deb http://deb.debian.org/debian bookworm-updates main contrib\n"
            "deb http://security.debian.org/debian-security bookworm-security main contrib\n"),
        "/etc/apt/sources.list.d/ceph.list":
            "deb https://enterprise.proxmox.com/debian/ceph-quincy bookworm enterprise\n",
        "/etc/apt/sources.list.d/pve-enterprise.list":
            "deb https://enterprise.proxmox.com/debian/pve bookworm pve-enterprise\n",
    },
    "9": {
        "/etc/apt/sources.list.d/ceph.sources": (
            "Types: deb\nURIs: https://enterprise.proxmox.com/debian/ceph-squid\nSuites: trixie\n"
            "Components: enterprise\nSigned-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n"),
        "/etc/apt/sources.list.d/debian.sources": (
            "Types: deb\nURIs: http://deb.debian.org/debian/\nSuites: trixie trixie-updates\n"
            "Components: main contrib non-free-firmware\n"
            "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n\n"
            "Types: deb\nURIs: http://security.debian.org/debian-security/\nSuites: trixie-security\n"
            "Components: main contrib non-free-firmware\n"
            "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\n"),
        "/etc/apt/sources.list.d/pve-enterprise.sources": (
            "Types: deb\nURIs: https://enterprise.proxmox.com/debian/pve\nSuites: trixie\n"
            "Components: pve-enterprise\nSigned-By: /usr/share/keyrings/proxmox-archive-keyring.gpg\n"),
    },
}

AUTOREMOVE_SIM = """\
Reading package lists...
Building dependency tree...
Reading state information...
The following packages will be REMOVED:
  proxmox-kernel-6.8.12-8-pve-signed
0 upgraded, 0 newly installed, 1 to remove and 0 not upgraded.
Remv proxmox-kernel-6.8.12-8-pve-signed [6.8.12-8]
"""

APT_SIM = """\
Reading package lists...
Building dependency tree...
Reading state information...
Calculating upgrade...
The following packages will be upgraded:
  proxmox-kernel-6.8 pve-manager
2 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
Inst pve-manager [8.4.1] (8.4.2 Proxmox:8.4/stable [all])
Inst proxmox-kernel-6.8 [6.8.12-10] (6.8.12-11 Proxmox:8.4/stable [all])
Conf pve-manager (8.4.2 Proxmox:8.4/stable [all])
Conf proxmox-kernel-6.8 (6.8.12-11 Proxmox:8.4/stable [all])
"""

# A kernel upgrade as a real node simulates it: the meta-package moves and pulls in a new
# versioned kernel package (no installed version in brackets).
APT_SIM_NEW_KERNEL = """\
Reading package lists...
Building dependency tree...
Reading state information...
Calculating upgrade...
The following NEW packages will be installed:
  proxmox-kernel-6.8.12-11-pve-signed
The following packages will be upgraded:
  proxmox-kernel-6.8
1 upgraded, 1 newly installed, 0 to remove and 0 not upgraded.
Inst proxmox-kernel-6.8.12-11-pve-signed (6.8.12-11 Proxmox:8.4/stable [amd64])
Inst proxmox-kernel-6.8 [6.8.12-10] (6.8.12-11 Proxmox:8.4/stable [all])
Conf proxmox-kernel-6.8.12-11-pve-signed (6.8.12-11 Proxmox:8.4/stable [amd64])
Conf proxmox-kernel-6.8 (6.8.12-11 Proxmox:8.4/stable [all])
"""

APT_SIM_NONE = """\
Reading package lists...
Building dependency tree...
Reading state information...
Calculating upgrade...
0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""


# what `mktemp /tmp/homelab-put.XXXXXXXX` prints on a node (pve_admin_put's remote temporary file)
PUT_TMP = "/tmp/homelab-put.Ab3dE5gH"


def ok(stdout: str = "") -> dict:
    return {"stdout": stdout, "exit": 0, "stderr": ""}


def pct_list(rows) -> str:
    lines = ["VMID       Status     Lock         Name                "]
    lines += [f"{vmid:<10} {status:<10} {'':<12} {name:<20}" for vmid, status, name in rows]
    return "\n".join(lines) + "\n"


def qm_list(rows) -> str:
    if not rows:
        return ""
    lines = ["      VMID NAME                 STATUS     MEM(MB)    BOOTDISK(GB) PID       "]
    lines += [f"{vmid:>10} {name:<20} {status:<10} {'4096':<10} {'32.00':>12} {'2211':<10}"
              for vmid, status, name in rows]
    return "\n".join(lines) + "\n"


def pvesm_status() -> str:
    return ("Name              Type     Status           Total            Used       Available        %\n"
            "local              dir     active        98497780        13120440        80327792   13.32%\n"
            "local-lvm      lvmthin     active       365760512       100022210       265738302   27.35%\n"
            "nas-backup         nfs     active      1951350784       512340224      1439010560   26.26%\n")


def local_lvm_volumes(node: str) -> str:
    rows = {"pve1": ["local-lvm:vm-101-disk-0  raw     rootdir    8589934592 101"],
            "pve2": ["local-lvm:vm-102-disk-0  raw     rootdir    8589934592 102",
                     "local-lvm:vm-200-disk-0  raw     images    34359738368 200"]}[node]
    return "Volid                    Format  Type             Size VMID\n" + "\n".join(rows) + "\n"


def lvs_all(node: str) -> str:
    disks = {"pve1": ["  vm-101-disk-0 pve  8589934592 41.20"],
             "pve2": ["  vm-102-disk-0 pve  8589934592 38.70", "  vm-200-disk-0 pve 34359738368 22.10"]}
    return ("  data          pve 374538764288 27.35\n  root          pve 103079215104\n"
            "  swap          pve   8589934592\n" + "\n".join(disks[node]) + "\n")


def collect_hash(root: Path) -> str:
    files = [root / "remote" / "homelab-collect", root / "remote" / "collect.allow",
             root / "local" / "collect.allow"]
    data = b"".join(path.read_bytes() for path in files if path.exists())
    return hashlib.sha256(data).hexdigest()[:16]


def answers(node: str, version: str = "8") -> dict:
    v = VERSIONS[version]
    nodeid = "1" if node == "pve1" else "2"
    local = {"local1": " (local)" if node == "pve1" else "", "local2": " (local)" if node == "pve2" else ""}
    table = {
        "uname -r": ok(f"{v['kernel']}\n"),
        "pveversion": ok(f"pve-manager/{v['manager']} (running kernel: {v['kernel']})\n"),
        "pveversion -v": ok(
            f"proxmox-ve: {v['ve']} (running kernel: {v['kernel']})\n"
            f"pve-manager: {v['manager'].split('/')[0]} (running version: {v['manager']})\n"
            f"proxmox-kernel-{v['kernel']}-signed: {v['kernel'].removesuffix('-pve')}\n"
            "corosync: 3.1.9-pve1\nlxc-pve: 6.0.0-1\npve-container: 5.2.6\nqemu-server: 8.3.12\n"
            "zfsutils-linux: 2.2.7-pve2\n"),
        "ls /boot": ok(f"config-{v['kernel']}\nefi\ngrub\ninitrd.img-{v['kernel']}\npve\n"
                       f"System.map-{v['kernel']}\nvmlinuz-{v['kernel']}\nvmlinuz-{v['newer']}\n"),
        "pct list": ok(pct_list(GUESTS[node]["ct"])),
        "qm list": ok(qm_list(GUESTS[node]["vm"])),
        "pvesm status": ok(pvesm_status()),
        "pvesm list local": ok("Volid                                                Format  Type            Size VMID\n"
                               "local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst tzst    vztmpl     126030062\n"),
        "pvesm list local-lvm": ok(local_lvm_volumes(node)),
        "pvesm list nas-backup": ok(BACKUPS),
        "pvesm list nas-backup --content backup": ok(BACKUPS),
        "pvecm status": ok(PVECM_STATUS.format(nodeid=nodeid, **local)),
        "pvecm nodes": ok(PVECM_NODES.format(**local)),
        "ls /etc/pve/nodes": ok("pve1\npve2\n"),
        "cat /etc/pve/storage.cfg": ok(STORAGE_CFG),
        "cat /etc/pve/corosync.conf": ok(COROSYNC),
        LVS_POOLS: ok("  pve data 374538764288 27.35 1.87\n"),
        LVS_ALL: ok(lvs_all(node)),
        VGS: ok("  pve 17179869184\n"),
        ZPOOL: ok("no pools available\n"),
        "free -b": ok("               total        used        free      shared  buff/cache   available\n"
                      "Mem:     33454669824 10737418240 15032385536    83886080  7684866048 22717251584\n"
                      "Swap:     8589930496           0  8589930496\n"),
        "df -P -B1 /": ok("Filesystem              1-blocks        Used   Available Capacity Mounted on\n"
                          "/dev/mapper/pve-root 101203873792 13435469824 82580643840      14% /\n"),
        "apt list --upgradable": ok("Listing...\npve-manager/stable 8.4.2 all [upgradable from: 8.4.1]\n"
                                    "proxmox-kernel-6.8/stable 6.8.12-11 all [upgradable from: 6.8.12-10]\n"),
        "apt-get -s dist-upgrade": ok(APT_SIM),
        "apt-get -s autoremove": ok(AUTOREMOVE_SIM),
        "fuser /var/lib/dpkg/lock-frontend": {"stdout": "", "exit": 1, "stderr": ""},
        "mktemp /tmp/homelab-put.XXXXXXXX": ok(f"{PUT_TMP}\n"),   # admin alias (pve_admin_put)
        "cat /etc/os-release": ok(f'PRETTY_NAME="Debian GNU/Linux {v["debian"]} ({v["codename"]})"\n'
                                  f'NAME="Debian GNU/Linux"\nVERSION_ID="{v["debian"]}"\n'
                                  f"VERSION_CODENAME={v['codename']}\nID=debian\n"),
    }
    sources = SOURCES[version]
    if "/etc/apt/sources.list" in sources:
        table["cat /etc/apt/sources.list"] = ok(sources["/etc/apt/sources.list"])
    else:
        table["cat /etc/apt/sources.list"] = {
            "stdout": "", "exit": 1, "stderr": "cat: /etc/apt/sources.list: No such file or directory\n"}
    table["ls /etc/apt/sources.list.d"] = ok("".join(
        Path(path).name + "\n" for path in sorted(sources) if path.startswith("/etc/apt/sources.list.d/")))
    for path, text in sources.items():
        if path.startswith("/etc/apt/sources.list.d/"):
            table[f"cat {path}"] = ok(text)
    for kind, cli in (("ct", "pct"), ("vm", "qm")):
        for vmid, status, _name in GUESTS[node][kind]:
            table[f"{cli} status {vmid}"] = ok(f"status: {status}\n")
            table[f"{cli} config {vmid}"] = ok(CONFIGS[vmid])
            table[f"{cli} listsnapshot {vmid}"] = ok(SNAPSHOTS[vmid])
    return table


def load(lab, version: str = "8") -> None:
    """Register the collect answers of every node, plus the dispatcher version of the lab's repo."""
    for node in ("pve1", "pve2"):
        for command, answer in answers(node, version).items():
            lab.responses.setdefault(node, {})[command] = answer
        lab.responses[node]["homelab-collect --version"] = ok(
            f"homelab-collect {collect_hash(lab.root)}\n")
