#!/usr/bin/env bash
# CI only, on a throwaway machine: a real sshd on localhost with the forced-command dispatcher,
# for tests/test_pve_sshd.py. Never run it on a machine you care about.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runner="${SUDO_USER:?run with sudo from the CI user}"
runner_home="$(getent passwd "$runner" | cut -d: -f6)"
out=/tmp/harness-sshd
user=harness-ci
password="ci-only-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq -o Dpkg::Options::=--force-confold openssh-server sshpass >/dev/null
mkdir -p "$out"
ssh-keygen -q -t ed25519 -N '' -f "$out/collect"
ssh-keygen -q -t ed25519 -N '' -f "$out/admin"
printf '%s\n' "$password" > "$out/password"

id "$user" >/dev/null 2>&1 || useradd -m -s /bin/bash "$user"
printf '%s:%s\n' "$user" "$password" | chpasswd
install -d -m 0700 -o "$user" -g "$user" "/home/$user/.ssh"
{
  printf 'command="/usr/local/bin/homelab-collect",restrict %s\n' "$(cat "$out/collect.pub")"
  cat "$out/admin.pub"
} > "/home/$user/.ssh/authorized_keys"
chown "$user:$user" "/home/$user/.ssh/authorized_keys"
chmod 0600 "/home/$user/.ssh/authorized_keys"

install -m 0755 "$repo/remote/homelab-collect" /usr/local/bin/homelab-collect
install -d -m 0755 /etc/homelab-collect
install -m 0644 "$repo/remote/collect.allow" /etc/homelab-collect/framework.allow
: > /etc/homelab-collect/local.allow
cat > /usr/sbin/pct <<'EOF'
#!/bin/sh
# CI stub of Proxmox's pct
if [ "$1" = list ]; then
  printf 'VMID       Status     Lock         Name                \n'
  printf '101        running                 pihole              \n'
  exit 0
fi
echo "pct stub: unsupported: $*" >&2
exit 2
EOF
chmod 0755 /usr/sbin/pct
cat > /usr/sbin/pvesm <<'EOF'
#!/bin/sh
# CI stub of Proxmox's pvesm
if [ "$1" = status ]; then
  printf 'Name             Type     Status           Total            Used       Available        %%\n'
  printf 'local             dir     active        10000000         2000000         8000000   20.00%%\n'
  exit 0
fi
echo "pvesm stub: unsupported: $*" >&2
exit 2
EOF
chmod 0755 /usr/sbin/pvesm

cat > /etc/ssh/sshd_config.d/10-harness-ci.conf <<EOF
Match User $user
    PasswordAuthentication yes
    KbdInteractiveAuthentication yes
EOF
# Socket-activated ssh (Ubuntu 24.04) creates the privilege separation directory only when the
# service starts; sshd -t needs it first.
install -d -m 0755 /run/sshd
sshd -t
systemctl restart ssh || systemctl restart sshd

install -d -m 0700 -o "$runner" "$runner_home/.ssh"
cat >> "$runner_home/.ssh/config" <<EOF

Host ci ci-admin ci-pw ci-pw2 ci-nokey
    HostName 127.0.0.1
    User $user
    StrictHostKeyChecking accept-new
    UserKnownHostsFile $out/known_hosts
Host ci
    IdentityFile $out/collect
    IdentitiesOnly yes
Host ci-admin
    IdentityFile $out/admin
    IdentitiesOnly yes
Host ci-nokey
    IdentityFile $out/missing
    IdentitiesOnly yes
EOF
chown -R "$runner" "$out" "$runner_home/.ssh"
chmod 0600 "$runner_home/.ssh/config"
