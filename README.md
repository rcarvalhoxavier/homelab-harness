# homelab-harness

A template for documenting, and safely changing, a self-hosted environment with an AI agent as
the maintainer. The wiki covers anything whose state you can capture as text: Proxmox nodes,
Raspberry Pis, NAS boxes, network gear and the services on top. The bundled toolkit adds
read-only collectors and guarded changes for Proxmox VE.

```text
you>    Is the Pi-hole pair actually redundant?

agent>  Partly. The two instances run on different nodes, CT 101 on pve1 and CT 102 on pve2
        [[sources/2026-06-01-guests]], and every client gets both addresses
        [[sources/2026-06-02-router-dhcp]], so losing one node does not take DNS down.
        But CT 101 answered about 91 % of last week's queries, and CT 102 is missing three
        local records: nas.lab.example, rpi.lab.example, backup.lab.example
        [[sources/2026-06-20-pihole-pair]]. While CT 101 is down, those names stop resolving.
        Filed as analyses/2026-06-20-pihole-pair-redundancy.md.
```

Every claim points to captured evidence, so you can check it, and the answer is kept for next
time. The example comes from the fictional homelab in [`examples/wiki/`](examples/wiki/).

**Try it** before touching your own machines: clone the repository, run
`bin/wiki-lint --wiki examples/wiki --today 2026-07-01` (0 errors, 3 warnings it explains), then
open your agent in the clone and ask: "Using examples/wiki, is the Pi-hole pair actually
redundant?"

It builds on Andrej Karpathy's [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
pattern. Instead of re-deriving answers from scattered notes every time, the agent **compiles**
knowledge once into a Markdown wiki and keeps it current. This template hardens the pattern for
infrastructure:

- **Every claim cites its source.** Raw evidence (command output, logs) is kept immutable under
  `wiki/raw/`, hashed, and **redacted of secrets** before it is stored.
- **Trust tiers** tell a measured fact (`pct config` output) from what the admin remembers and
  from what another agent session reported.
- **Changes are planned, approved and recorded** as baseline, change and after, captured with the
  same read-only collector, with the rollback secured first and "done" proven by measurement.
- **A deterministic linter** catches broken links, tampered evidence, stale pages, forgotten
  pending decisions and leaked secrets, in the agent loop, in CI and in a pre-commit hook.

It works with [Claude Code](https://claude.com/claude-code) out of the box (skills in
`.claude/skills/`). The rules are plain Markdown, so any agent that reads `AGENTS.md` can follow
them.

## What's inside

| Path | What |
|---|---|
| `.claude/skills/llm-wiki/` | The wiki method: capture, ingest, query, diagnose, lint |
| `.claude/skills/infra-change/` | Plan, run and record an infrastructure change |
| `bin/init` | Creates your `wiki/` and `.claude/rules/local.md` from `templates/`; never overwrites |
| `bin/wiki-capture` | Redacts command output and stores it as evidence |
| `bin/wiki-lint` | Deterministic wiki checks |
| `bin/pve-*`, `lib/pve/` | Proxmox toolkit: five read-only tools (state, health, capacity, discovery, self-test) and eight changing tools ([guide](docs/proxmox-toolkit.md)) |
| `remote/` | The forced-command dispatcher and allowlist installed on your hosts |
| `examples/local/` | How an installation extends the toolkit |
| `examples/wiki/` | A complete fictional homelab wiki to learn from |
| `docs/ssh-access.md` | Give the agent password-less SSH that can only read |

Requirements: Python 3.10+ (standard library only), Git, and Bash for the pre-commit hook. The
Proxmox toolkit also needs Bash 4.4+ and OpenSSH (and `sshpass` only for the password fallback).
It targets Proxmox VE 8, verified on real nodes. Proxmox VE 9 support is experimental: its test
fixtures were not yet compared with a real PVE 9 node, `bin/pve-selftest` warns on a PVE 9 node,
and the update and cleanup tools fail closed ("no summary line") if apt's output there differs.

## Working on code: superpowers (recommended)

The two skills here cover knowledge (`llm-wiki`) and operational changes (`infra-change`). When
the work is code, a script, a stack or a tool of your own, `AGENTS.md` routes it to
[superpowers](https://github.com/obra/superpowers), a separate MIT-licensed skills library by
Jesse Vincent: it turns an idea into a written design, the design into a plan, and the plan into
code built test-first and reviewed. A plan that runs anything on a host ends by handing over to
`infra-change`. The harness works without it; your agent then follows the design, plan and
execution flow you prefer.

Install it once for each agent you use:

- Claude Code: `/plugin install superpowers@claude-plugins-official`
- Codex, Cursor, Gemini CLI and others: see its
  [installation guide](https://github.com/obra/superpowers#installation).

## Getting started

### Path 1: your real homelab (recommended), as a private copy

Your wiki will describe your network, your hosts and, sometimes, their weaknesses. Keep it private.

```bash
git clone https://github.com/rcarvalhoxavier/homelab-harness.git my-homelab
cd my-homelab
git remote rename origin upstream
# Create an EMPTY private repository on GitHub (no README, no license), then:
git remote add origin git@github.com:<you>/my-homelab.git
git push -u origin main
bin/init --hooks
git add wiki .claude/rules/local.md && git commit -m "wiki: initial schema" && git push
```

Your copy shares its history with upstream, so updates are a normal merge (see below). Making it
public later is not a switch you flip: see [Exposure](#exposure-private-or-public).

### Path 2: fork

Fork only to contribute to the template, or if your wiki will be public from day one
(`exposure: public`).

> ⚠️ **A fork of a public repository can never be made private on GitHub.** All repositories in
> a fork network share the same visibility
> ([GitHub docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/about-permissions-and-visibility-of-forks)).

### Path 3: "Use this template"

GitHub's **Use this template** button creates a repository with a fresh, unrelated history.
Path 1 is simpler; if you used the button, connect the histories once, without changing any
file:

```bash
git remote add upstream https://github.com/rcarvalhoxavier/homelab-harness.git
git fetch upstream
# The upstream commit your copy was made from: the last one before your repository's first commit.
base=$(git log upstream/main -1 --format=%H --before="$(git log --reverse --format=%cI | head -1)")
git merge --allow-unrelated-histories -s ours "$base" -m "Adopt upstream history"
```

After that, `git merge upstream/main` works as in Path 1.

### After `bin/init`

1. Open `wiki/AGENTS.md` and fill in the `[CUSTOMIZE]` sections (what the wiki covers, your host
   names, your vocabulary), removing each marker as you go. Do the same in
   `.claude/rules/local.md`, your installation's agent rules.
2. Give the agent SSH access that can only read: [`docs/ssh-access.md`](docs/ssh-access.md).
3. Proxmox: once the aliases of one node work, `bin/pve-discover --seed pve1` writes
   `inventory/nodes` and prints the first evidence; ask your agent for the DISCOVER operation to
   turn it into pages. Then install the dispatcher and run `bin/pve-selftest`
   ([`docs/proxmox-toolkit.md`](docs/proxmox-toolkit.md#setup)). Run every changing tool with
   `--dry-run` first, and for real (an agent adds `--yes`) only after you have confirmed that
   exact command.
4. Capture your first evidence. Any command output works; the first one does not even need SSH:

   ```bash
   cat /etc/os-release | bin/wiki-capture laptop-os --origin "cat /etc/os-release @ laptop"
   ssh pve1 pveversion -v | bin/wiki-capture pve1-versions --origin "pveversion -v @ pve1"
   ```

5. Run `bin/wiki-lint`. Expect three warnings per capture until it is ingested: `W-STUB`
   (the source page still has `TODO(ingest)`), `W-ORPHAN` and `W-INDEX` (nothing links to it
   yet).
6. Ask your agent: *"ingest the pve1-versions capture into the wiki"*. Or do it by hand once, to
   see what the agent does (next section).
7. `bin/wiki-lint` shows 0 errors: commit `wiki/`. The CI of your copy lints the committed wiki.

### Your first ingest, by hand

Open `examples/wiki/` next to your wiki and copy its shapes:

1. Complete `wiki/sources/<date>-pve1-versions.md`: replace each `TODO(ingest)` with a summary
   and key points (see `examples/wiki/sources/2026-06-01-pve-versions.md`).
2. Create `wiki/entities/host-pve1.md` with `kind: host`, `status: active`,
   `last_verified: <date>`, and a paragraph that cites the source as `[[sources/<date>-pve1-versions]]`
   (see `examples/wiki/entities/host-pve1.md`).
3. Add both pages to `wiki/index.md`, and a line to `wiki/log.md`:
   `## [<date>] ingest | pve1 versions`.
4. `bin/wiki-lint`: 0 errors, 0 warnings.

`bin/wiki-lint --wiki examples/wiki --today 2026-07-01` shows the example's three intended
warnings (a pending decision and two stale pages); without `--today`, time has made every page
stale.

## How it works

| Layer | Where | Who writes it |
|---|---|---|
| Evidence | `wiki/raw/` | `bin/wiki-capture` only; immutable, hashed, redacted |
| Knowledge | `wiki/entities/`, `concepts/`, `sources/`, `changes/`, `analyses/` | the agent, citing evidence |
| Schema | `wiki/AGENTS.md` | you and the agent, together |

- **Capture**: run a read-only command and pipe it to `bin/wiki-capture <slug>`. Secrets are
  redacted, the result lands in `wiki/raw/` with a hash, and a source stub is created.
- **Ingest**: the agent reads the capture as untrusted data, completes the source page, and
  updates entity and concept pages. Every claim cites the source.
- **Diagnose**: when something breaks, the agent gathers read-only evidence, checks recent
  changes and records its hypotheses; the fix is a change.
- **Change**: the `infra-change` skill presents the plan (done-criteria, rollback, steps, abort
  conditions) for your approval, secures the rollback, captures a baseline, logs each step,
  captures the same state again, and records the diff in `wiki/changes/`.
- **Lint**: `bin/wiki-lint` checks links, evidence hashes, encodings, staleness, open pending
  decisions and secrets. Exit code 1 means errors.

## Exposure: private or public

`wiki/AGENTS.md` declares `exposure: private` or `exposure: public`. Secrets are always redacted.
In `public` mode, captures also replace IP and MAC addresses and home or dynamic-DNS hostnames
(`*.lan`, `*.home.arpa`, `*.duckdns.org`…) with `<IP-1>`, `<MAC-1>`, `<HOST-1>` and so on, and
the linter rejects any left in the wiki. Add your own domains, Wi-Fi names and serial numbers to
`wiki/.capture-patterns`.

**Going public later is not a visibility switch.** Git history keeps every capture made while
the wiki was private: addresses, topology and findings such as "this API is open without
authentication". To publish, either start a new repository from freshly captured, public-mode
evidence, or rewrite the history first. Both are deliberate decisions, not a settings change.

## Updating from upstream

```bash
git fetch upstream
git merge upstream/main
```

Upstream never ships `wiki/`, `local/`, `inventory/`, `.claude/rules/local.md` or `.env.local`,
so your content never conflicts. The only way to get a conflict is to edit a framework file.

After a merge, run `bin/init --hooks` again: it replaces an installed pre-commit hook that is an
unmodified earlier version of `templates/hooks/pre-commit` (`updated:`), and leaves any other hook
untouched.

### Customizing without conflicts

| You want | Put it in |
|---|---|
| Agent rules for your installation | `.claude/rules/local.md` |
| Wiki scope, entity kinds, vocabulary | `wiki/AGENTS.md` |
| Your own skills | `.claude/skills/<your-name>/` |
| Personal Claude Code permissions | `.claude/settings.local.json` |
| Extra ignore rules | `.git/info/exclude` (the committed `.gitignore` is upstream's) |
| Extra CI | a new `.github/workflows/local-<name>.yml` |
| Scripts, stacks, specs and plans | `local/` |

Team-wide Claude Code permissions live in the committed `.claude/settings.json`, which is
upstream's: changing it is a known conflict point on merge.

Obsidian users: the vault configuration lives in `wiki/.obsidian/`. The secret scan covers it
(plugins keep API keys there); add it to `.git/info/exclude` if you do not want it committed.

If you already have a personal skill named `llm-wiki` (in `~/.claude/skills/`), Claude Code may
pick either one; rename yours.

## Contributing

Issues and pull requests are welcome. Run `python3 -m unittest discover -s tests -t .` before
opening a pull request. The CI runs the framework checks (unit tests, shellcheck, the example
wiki lint and a real sshd) only in `rcarvalhoxavier/homelab-harness`, pull requests from forks
included; every copy runs its own wiki lint instead.

## Roadmap

- Migration guide for existing wikis

## Credits and license

The wiki pattern is Andrej Karpathy's
[LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). This template is
released under the [MIT License](LICENSE).
