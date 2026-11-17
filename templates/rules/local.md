# Local rules for this installation

Claude Code loads this file in every session (`.claude/rules/` files without `paths:` load at
launch); the root `AGENTS.md` points other agents here. It belongs to this installation:
upstream never ships it, so edit it freely.

## Where things go here  [CUSTOMIZE]

- Specs and plans for code in this repository: specs in `local/docs/specs/`, plans in
  `local/docs/plans/`. With superpowers installed (`brainstorming`, `writing-plans`) this
  overrides its default, `docs/superpowers/`; without it, the design, plan and execution flow of
  `AGENTS.md` writes them there.
- Scripts and stacks of this installation: `local/`.

## Rules for this installation  [CUSTOMIZE]

- (Hosts the agent must never touch, maintenance windows, who approves what.)
