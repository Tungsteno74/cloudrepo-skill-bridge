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
- CloudRepo Skill Bridge 0.2.0 is the sole maintained canonical identity;
  the migration is complete. Historical artifacts remain in Git history.
- Its GitHub source repository is intentionally public; the ChatGPT plugin
  distribution remains private to the user.

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

## E2E closure (2026-10-19)

- ChatGPT plugin-owned skills were listed and read natively in Current Cloud.
  Version 0.2.0 is confirmed by Plugin Creator, but the Cloud task's loader
  did not independently expose a version identifier.
- The independent private fixture at commit
  2b76c20a1104df182a79845a415b31a9778bfd49 proved read-only document
  resolution and retained a clean checkout. Its repository-local skill was
  NOT exposed with an authoritative native scope=repo locator.
- The packaged Python CLI was unavailable in the Current Cloud runtime;
  its separate local single-source and multi-source tests passed.
- Windows Bootstrap 0.6.8 managed E2E passed in run 39271694821, with
  WINDOWS_CLOUD_E2E_OK and verified baseline restoration; no default branch
  change, PR or merge occurred. This verifies Bootstrap operational CI,
  not native Bridge repository registration.
- E2E acceptance is complete for release 0.2.0 with provider-native repo
  discovery and Cloud CLI mounting recorded as external limitations, not
  passed gates. Do not broaden these observations into guaranteed provider
  features or claim the whole sequence runs automatically.

## Retention

- Historical releases and changelog entries remain preserved for audit.
- The retired independent E2E fixture may remain archived as a benchmark;
  no legacy plugin is part of the active distribution path.
