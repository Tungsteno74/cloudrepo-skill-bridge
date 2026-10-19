# Repository instructions — CloudRepo Skill Bridge

This is the source and distribution boundary for the independent
CloudRepo Skill Bridge plugin. The complete Agent Plugins 1.0 package is
in plugins/cloudrepo-skill-bridge/. Read docs/PROJECT_MEMORY.md before
significant changes and follow the applicable AGENTS_POLICY guidance.

- Preserve plugin/skill/source identifiers, semantic version, interface and
  dependency contracts unless a scoped change explicitly calls for migration.
- Discovery, resolution and the Python CLI are read-only: never execute skill
  content, create credentials, clone/fetch unapproved repos, alter environment
  settings, or claim provider-native skill activation from a document read.
- Require explicit repository identity, immutable source revision, source
  scope and authorization. Do not follow symlinks or bypass 401/403.
- Root Chat owns external mutations and consent. Plugin installation alone
  does not authorize GitHub writes or workflow/CI execution.
- Use Python 3.9+, type hints, PEP 8, straightforward interfaces and the
  declared PyYAML dependency. Do not add unrelated dependencies.
- Run python -X utf8 tools/validate.py before commits; report any skipped
  tests and keep Current Cloud native-loader work as an unverified TODO.
- Generated ZIPs belong under dist/, not in plugin source. No marketplace
  manifest, account-specific plugin ID, secrets or automatic plugin publisher
  belongs in this repository.
- Reconcile remote ref/commit/run state before retrying ambiguous GitHub
  operations. Preserve user work and keep changes reviewable.
