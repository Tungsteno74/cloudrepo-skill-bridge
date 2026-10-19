# Changelog

## 0.2.0

- Rebrand the visible identity as CloudRepo Skill Bridge, aligning the provider-neutral scope with the CloudRepo family.
- Add a blue cloud/manifest/linked-source icon to both portable and Codex plugin interfaces.
- Adopt new canonical plugin slug, skill identifiers, Python import namespace and standard numeric SemVer. The existing GitHub app connection stays optional.

- Parse skill frontmatter and agent policy as typed YAML using a declared PyYAML
  runtime dependency; reject duplicate keys, malformed content and invalid types.
- Resolve selected multi-repository skill directly without validating unrelated
  siblings; preserve ambiguity detection across approved sources.
- Accept regular Git executable files (100755) without executing their contents,
  while still rejecting symlinks and non-regular Git objects.
- Reject GitHub API redirects before any follow-up request; preserve fixed-origin
  immutable-source reads.
- Validate packaged JSON/YAML structurally and emit ASCII-safe machine-readable
  CLI JSON across non-UTF-8 Windows terminals.
- Add regression coverage for real pinned sources, YAML policy variants, unsafe
  modes, redirect behavior, validator failures and CLI encoding.

## 0.2.0-alpha.1

- Add pinned, explicitly scoped multi-repository skill discovery and resolution.
- Support committed separate local Git checkouts and public GitHub immutable
  commit/tree/blob reads, with a separate injectable, preauthorized connector
  provider for private-source reads when actually available.
- Resolve standard repository-local and plugin source layouts without copying
  source files into the task repository.
- Enforce source identity, exact SHA, safe paths, Git object integrity, collision
  handling, bounded resources and read-only operation; preserve the existing CLI.
- Mark Current Cloud native repo discovery and hosted Python CLI execution as
  non-blocking diagnostic TODOs; retain successful manual E2E baselines.
- Add independent local/connector simulation regression tests and next-stage
  multi-repository Cloud validation guidance.

## 0.1.0-alpha.3

- Enable implicit selection of `cloudrepo-skill-invoke` for Root and Child.
- Permit autonomous, task-relevant read-only resolution without requiring an
  end-user request to name the resolver; prohibit permission escalation or
  operational side effects without existing authorization.
- Add regression checks for skill visibility and the authorization boundary.

## 0.1.0-alpha.2

- Document the retired Windows Bootstrap Alpha `install_script` attempt and its missing persistence/native discovery in Current Cloud.
- No runtime, skill contract or permission changes.

## 0.1.0-alpha.1

- Independent repository-scoped skill discovery and manual instruction bridge.
- Strict source/commit checks, bounded references, frontmatter and symlink validation.
- Explicit distinction between repository files, native repo locators and plugins.
- No automatic skill execution, token handling, setup or CI side effects.
