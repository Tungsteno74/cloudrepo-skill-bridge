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

The ChatGPT plugin and its source repository have distinct identities and
lifecycles. The prior CloudCodeX Repository Skill Bridge plugin remains separate
during migration; no alias or automatic deletion is implied. Source updates do
not automatically publish a ChatGPT plugin release.

See the package README in plugins/cloudrepo-skill-bridge/ and project memory in
docs/PROJECT_MEMORY.md. This repository does not contain marketplace metadata.
