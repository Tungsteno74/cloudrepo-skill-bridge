# CloudRepo Skill Bridge

Provider-neutral, read-only discovery and resolution of skills from explicitly
scoped and pinned Git repositories. This repository contains the standalone
CloudRepo Skill Bridge 0.2.0 Agent Plugins 1.0 source package.

## Source and validation

- Canonical package: plugins/cloudrepo-skill-bridge/
- Python CLI: plugins/cloudrepo-skill-bridge/runtime/cli.py
- Native skill names: cloudrepo-skill-discovery, cloudrepo-skill-invoke
- GitHub dependency: optional existing, authorized GitHub connector
- Python dependency: PyYAML from runtime/requirements.txt

From the repository root, install requirements in a **separately approved**
Python environment, then run:

    python -X utf8 tools/validate.py
    python -X utf8 tools/build_release.py

The deterministic standalone ZIP and checksum manifest are written to dist/
without changing the source tree. The plugin never installs itself, registers
repository files natively, or executes an untrusted skill. The Current Cloud
native-loader / packaged runtime behavior remains a separate live acceptance
test, not a property established by offline validation.

## Governance

CloudRepo Skill Bridge 0.2.0 is the sole maintained, canonical distribution.
Its ChatGPT plugin release and public GitHub source repository have distinct
lifecycles. Source updates do not automatically publish a plugin release.

## Acceptance evidence

- Python CLI: offline conformance and pinned repository discovery/resolve
  validated; the standalone read-only CLI works when supplied locally.
- Current Cloud: both plugin-owned skills were exposed and successfully read
  through the native plugin loader. Immutable GitHub document fallback was
  verified against an independent repository fixture.
- Provider limitations: no authoritative repository-native skill locator
  was exposed in that Cloud task, and the plugin's packaged Python CLI was
  not mounted there. Neither result is a proven Bridge source regression.
- Downstream Windows Bootstrap managed validation: one successful Windows
  GitHub Actions run, with baseline restored and the default branch unchanged.

Version 0.2.0 is accepted with the Cloud provider limitations documented
above. Do not count document fallback as native repository activation.

See the package README in plugins/cloudrepo-skill-bridge/ and project memory in
docs/PROJECT_MEMORY.md. This repository does not contain marketplace metadata.
