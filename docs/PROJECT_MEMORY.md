# CloudRepo Skill Bridge — Project Memory

## Confirmed decisions

- Standalone plugin identity and Python namespace are cloudrepo-skill-bridge
  and cloudrepo_skill_bridge; version 0.2.0 is numeric SemVer.
- Author is Tungsteno74. The icon retains the Windows Bootstrap cloud
  silhouette and replaces only the central Windows symbol with a skill
  manifest and three repository nodes.
- Source layout mirrors CloudRepo Environment Direct:
  plugins/cloudrepo-skill-bridge/ is the complete release package.
- The plugin remains provider-neutral, read-only, and has no native
  registration API or automatic CI publishing authority.
- This is a separate plugin from the historical
  cloudcodex-repository-skill-bridge; do not delete or silently redirect it.
- Repository hosting starts private pending an explicit visibility decision.

## Observed / verified

- Release source ZIP SHA-256:
  0822d2531c7e79d7e5fc166ed8927556a85d6c3c47f6944a8e9369e5f426cb5d.
- In isolated Linux validation, 62 automatic tests passed.
- Previous Windows validation completed 58 tests with 4 symlink tests
  skipped because Windows symlink creation required unavailable privileges.
- The release validator checks structural identity, frontmatter, icon,
  references, requirements and optional GitHub connection.
- Multi-source discovery and resolution against pinned published GitHub
  plugin sources previously completed via the declared public adapter.
- The initial Current Cloud read-only A/B experiment demonstrated
  connector-backed document resolution, not packaged CLI execution.

## Unresolved / future verification

- Native Current Cloud loader exposure of these plugin skills and the
  packaged Python runtime is not proven by a source ZIP or CI result.
- Windows Bootstrap managed-run E2E is a separately authorized subsequent
  workflow; do not trigger it from this repository setup.
- An initial GitHub CI result must be observed rather than inferred from
  workflow configuration alone.

## Retired / historical

- The CloudCodeX-branded alpha plugin used another canonical name, skill
  identifiers and Python namespace. Its release is retained for migration.
