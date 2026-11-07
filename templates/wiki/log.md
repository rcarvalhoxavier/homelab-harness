# Log

Append-only; newest entry last. Heading format: `## [YYYY-MM-DD] <op> | <title>`, where op is
one of `ingest`, `query`, `lint`, `update`, `capture`, `change`, `diagnose`, `reconcile`.

Recent entries: `grep "^## \[" wiki/log.md | tail -10`

## [{{date}}] update | Wiki created

Created by `bin/init` from `templates/wiki/`.
