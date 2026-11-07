# SSH access for the agent

The agent runs read-only collectors on your hosts over SSH. It cannot type a password: a
password prompt makes it hang or fail. This guide sets up key-based, non-interactive access
where any authentication problem fails immediately.

## 1. Create a dedicated key

```bash
ssh-keygen -t ed25519 -f ~/.ssh/homelab_agent -C "homelab-agent@$(hostname)"
```

Give it a passphrase and load it into `ssh-agent` once per login session; the agent then uses
the key without any prompt:

```bash
eval "$(ssh-agent -s)"    # skip if your desktop session already runs an agent
ssh-add ~/.ssh/homelab_agent
```

A key without a passphrase also works and survives reboots without `ssh-add`, but anyone who
copies the file gets the same access to your hosts. Only do that on a machine you fully
control, with an encrypted disk.

## 2. Install the key on each host

```bash
ssh-copy-id -i ~/.ssh/homelab_agent.pub root@10.0.0.11
```

**Proxmox cluster:** root's `authorized_keys` is shared by every node of a cluster
(`/root/.ssh/authorized_keys` points to `/etc/pve/priv/authorized_keys`), so installing the key
on one node authorizes it on all of them.

On a Raspberry Pi or any host where you do not log in as root, install the key for that user
(`ssh-copy-id -i ~/.ssh/homelab_agent.pub pi@10.0.0.20`) and grant only what the collectors
need (step 5).

## 3. One `~/.ssh/config` block per host

```sshconfig
Host pve1
    HostName 10.0.0.11
    User root
    IdentityFile ~/.ssh/homelab_agent
    IdentitiesOnly yes
    BatchMode yes
    ConnectTimeout 10
    StrictHostKeyChecking accept-new
    ControlMaster no
    ControlPath none
```

- `IdentitiesOnly yes` offers only this key, not every key in your agent.
- `BatchMode yes` never prompts: a missing key or a wrong user fails at once instead of hanging.
- `ConnectTimeout 10` fails fast when a host is down.
- `StrictHostKeyChecking accept-new` records a new host's key on first contact and still refuses
  a key that later changes.
- `ControlMaster no` and `ControlPath none` turn connection sharing off. The read alias and the
  admin alias of step 5 reach the same `user@host:port`, so a shared connection (a
  `ControlMaster auto` in a `Host *` block) would run reads with the admin key, or changes with
  the restricted one. The toolkit passes both options on every call; keep them here for `ssh` by
  hand.

The agent now runs `ssh pve1 pveversion -v`.

## 4. Verify

```bash
ssh -o BatchMode=yes pve1 true && echo OK
```

`Permission denied (publickey)` means the key is not installed for that user, the `User` is
wrong, or the key is not loaded in `ssh-agent` (`ssh-add -l` lists loaded keys).

## 5. Limit what the agent's key can run (recommended)

An allow rule on `ssh` in an agent's permission system is typically a **prefix** rule: in Claude
Code, `Bash(ssh pve1 pct config:*)` also approves `ssh pve1 pct config 101 '&&' pct destroy 101`.
`ssh` joins its arguments and the remote shell runs the result, so the quoted `&&` chains a
destructive command, and the prompt that would have stopped a command injected through an
ingested source never appears. Other agents' permission systems have the same weakness.

So restrict the key on the host itself, with a forced command: whatever the client asks for,
`sshd` runs the dispatcher `remote/homelab-collect` instead, and it runs only the read-only
commands listed in `remote/collect.allow` and your `local/collect.allow`
(grammar: [`proxmox-toolkit.md`](proxmox-toolkit.md#the-dispatcher)).

1. Install the dispatcher and its lists on each host, through the admin alias (defined at the
   end of this section):

   ```bash
   bin/pve-collect-install pve1 --dry-run
   bin/pve-collect-install pve1
   ```

   On a host outside the Proxmox toolkit, copy `remote/homelab-collect` to
   `/usr/local/bin/homelab-collect` (mode 755) and your list to
   `/etc/homelab-collect/local.allow` by hand.

2. In `~/.ssh/authorized_keys` on the host, prefix the agent key's line:

   ```text
   command="/usr/local/bin/homelab-collect",restrict ssh-ed25519 AAAA... homelab-agent@laptop
   ```

   On a Proxmox cluster that file is shared by all nodes: install the dispatcher on every node
   before adding the prefix. It lives on the cluster file system (`/etc/pve/priv/authorized_keys`,
   which `/root/.ssh/authorized_keys` points to): keep a copy outside `/etc/pve` first, edit a
   copy, then write it back with `cat edited > /etc/pve/priv/authorized_keys` so the link and the
   file stay in place. In-place editors that replace the file through a temporary file (`sed -i`)
   are not a safe choice there.

3. Check it refuses chaining:

   ```bash
   ssh pve1 pveversion                        # works
   ssh pve1 'pct config 101 && id'            # homelab-collect: refused: pct\ config\ 101\ \&\&\ id
   bin/pve-selftest --node pve1               # "the collect key is restricted" must PASS
   ```

The restricted key can only collect. For changes, use a second key without the restriction,
under its own host alias, and never pre-approve it, so every command it runs asks first. The
dispatcher installs through this alias, so create it before running the commands above:

```sshconfig
Host pve1-admin
    HostName 10.0.0.11
    User root
    IdentityFile ~/.ssh/homelab_admin
    IdentitiesOnly yes
    BatchMode yes
    ControlMaster no
    ControlPath none
```

## 6. Agent permissions

Pre-approve only commands that cannot change anything, and only once `bin/pve-selftest` shows
"the collect key is restricted". Put the rules in your agent's local, uncommitted settings. For
Claude Code, `.claude/settings.local.json` (gitignored):

```json
{
  "permissions": {
    "allow": [
      "Bash(bin/pve-state:*)",
      "Bash(bin/pve-health:*)",
      "Bash(bin/pve-capacity:*)",
      "Bash(bin/pve-selftest:*)",
      "Bash(ssh pve1 pveversion:*)"
    ]
  }
}
```

Never pre-approve a changing tool, `ssh` to an admin alias, or `ssh` to a host without the
forced command.

## 7. Optional: collectors without root

Run the collectors as a dedicated user with narrowly scoped `sudo`:

1. Create the user and install the agent key for it (`ssh-copy-id -i
   ~/.ssh/homelab_agent.pub homelab-agent@10.0.0.11`), with the forced-command prefix.
2. On the host, create the flag file `/etc/homelab-collect/use-sudo`: the dispatcher then runs
   each allowed command as `sudo -n <command>` when the account is not root.
3. Allow **every** command of the installed lists (`framework.allow` and `local.allow`) in
   `/etc/sudoers.d/homelab-agent`, and nothing else. Before each command the dispatcher asks
   `sudo -n -l` whether sudoers allows it; when it does not, the dispatcher refuses with
   `homelab-collect: refused (sudo): <command>` (exit 126) instead of letting `sudo` fail with
   exit 1, which a collector would read as the command's own answer ("dpkg is not in use", "no
   ZFS pool"). Generate the lines on the host, as root, from the lists `pve-collect-install`
   installed, then review and validate them:

   ```bash
   cat /etc/homelab-collect/framework.allow /etc/homelab-collect/local.allow |
     sed -e '/^[[:space:]]*#/d' -e '/^[[:space:]]*$/d' -e 's/[\\,:=]/\\&/g' \
         -e 's#{aptfile}#/etc/apt/sources.list.d/*#g' -e 's/{[a-z]*}/*/g' |
     while read -r cmd args; do
       printf 'homelab-agent ALL=(root) NOPASSWD: %s%s\n' "$(command -v "$cmd")" "${args:+ $args}"
     done > /tmp/homelab-agent.sudoers
   visudo -c -f /tmp/homelab-agent.sudoers && install -m 0440 /tmp/homelab-agent.sudoers /etc/sudoers.d/homelab-agent
   ```

   The `sed` drops comments and blank lines, escapes the characters sudoers treats specially
   (`\ , : =`) and turns each `{field}` into `*`. A `*` in sudoers matches more than the field
   allows (any characters, `/` and spaces included): the dispatcher still checks every field
   against its pattern before `sudo` runs, so the account must have no way in other than the
   forced-command key (no password, no other key). Run the generation again whenever the lists
   change.

4. Use that user in the host block:

   ```sshconfig
   Host pve1
       HostName 10.0.0.11
       User homelab-agent
       IdentityFile ~/.ssh/homelab_agent
       IdentitiesOnly yes
       BatchMode yes
       ConnectTimeout 10
       StrictHostKeyChecking accept-new
       ControlMaster no
       ControlPath none
   ```

## 8. Other hardening

Once keys work everywhere, disable password logins with `PasswordAuthentication no` in
`/etc/ssh/sshd_config` and `systemctl reload ssh`. Keep console access (Proxmox web shell,
keyboard and monitor) in case you lock yourself out.

## 9. Legacy: password with `sshpass`

Use this only while you cannot use keys. Put `HOMELAB_SSHPASS=1` and the password, as
`SSHPASS=...` (unquoted), in `.env.local` (gitignored; `bin/wiki-capture` redacts its value from
captures). The toolkit reads the file literally, never with `source`, and passes the password
only to `sshpass -e`, never to `sshpass -p`, which would show it in the process list. By hand,
read just that one variable:

```bash
SSHPASS="$(sed -n 's/^SSHPASS=//p' .env.local)" sshpass -e ssh -o BatchMode=no root@10.0.0.11 pveversion
```

Password login needs `BatchMode no`, so do not reuse the host block from step 3. A password login
has no forced command, so `bin/pve-selftest` warns on every run while the fallback is on.
