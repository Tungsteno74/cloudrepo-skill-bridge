---
name: cloudrepo-skill-discovery
description: >-
  Discover and validate skills in the Git repository explicitly associated with
  a Root or Child task. Use when skill lookup or repository-local provenance is
  requested; never claim plugin registration or automatically execute a skill.
---

# CloudRepo skill discovery

This skill is independent of Codex Cloud generation, provider and task mode.
For the legacy single-repository path, the checkout must be associated with the
current task by verified host context, explicit caller context, or an exact
user-supplied repository path and revision. For multi-repository requests,
additional repositories must each be explicitly scoped and pinned by Root/Child
under the current task; never infer access from a plugin installation.
Do not search unrelated repositories, guess an environment ID, change directories
at process startup, install a plugin, or assume that a successful plugin lookup
proves repository discovery.

Read [the shared discovery contract](references/discovery-contract.md) first.

## Procedure

1. Recover the exact associated repository root, canonical repository identity,
   and expected full commit SHA from the caller/host; if any mandatory identity
   is unavailable or conflicting, return `REPOSITORY_CONTEXT_REQUIRED` with
   the missing fields. A session `cwd` is not evidence of the repository root.
2. Prefer the actual host's supported native skill inventory when available.
   Match *name, source path, scope and plugin ID*. An authoritative `scope=repo`
   locator rooted in the associated checkout proves native repo discovery; an
   installed plugin with the same name does **not**.
3. To enumerate on disk without requiring the native loader, use the packaged
   read-only CLI with an **absolute repository root**, `--expected-commit` and
   `--expected-repository`, when Python/Git and the plugin runtime are available:

   ```text
   python <bridge-plugin-root>/runtime/cli.py discover --repository-root <checkout-root> --expected-commit <full-sha> --expected-repository <owner/repo>
   ```

4. If code execution is unavailable but an authorized repository reader is
   available to Root or Child, use it to read `.agents/skills/<name>/SKILL.md`
   from the exact verified repository and revision. Check scope, identity,
   frontmatter and supporting file existence. Do not claim CLI-side symlink or
   filesystem checks took place through a GitHub content API.
5. Return names, manifest hashes/paths, source revision, and separate evidence
   fields for `filesystem_discovery`, `native_registration`, and `plugin_catalog`.
   An empty/filtered plugin catalog is not proof of missing repo files.

No repo/Git writes, symlink following, untrusted shell execution, network token
extraction, plugin installation, environment update, or CI. Never return a
barely inferred native locator. The discovery skill cannot authorize execution.

## Multi-repository discovery (optional)

For task-authorized skills held in *other* repositories, do not scan GitHub
accounts or infer mutable default branches. Require a bounded caller/Root-approved
list identifying **each** canonical `owner/repo`, full immutable commit, skill
root and source key. No automatic plugin installation or repository modification.

Supported skill roots are `.agents/skills`, `skills`, and
`plugins/<canonical-plugin-name>/skills`. Never guess a different root. When
the plugin CLI is executable and the caller has supplied a source catalog:

```text
python <bridge-plugin-root>/runtime/cli.py multi-discover --sources-file <absolute-sources-json>
```

The catalog permits at most eight sources: `local-git` (an already present,
verified separate checkout), `github-public` (read-only unauthenticated GitHub
API), or a `github-connector` source provided by an explicitly injected,
already authorized host reader. The standalone CLI cannot access private
repositories or manufacture connector credentials.
The local backend inspects committed Git objects at the pinned source revision,
not dirty/unpublished working-tree text. Remote resources are checked against
immutable Git blob IDs. Nothing is copied into the associated task repository.

When the CLI is unavailable, a caller with an **already authorized** GitHub
connector may perform bounded same-revision commit, tree and blob reads for the
explicitly approved source. Record this separately as `connector_document_fallback`:
it is not a Python CLI invocation, a native skill locator or a proof of local
symlink checks. An authentication denial, missing identity, truncated Git tree,
non-regular object or ambiguous source is a stop condition, never a reason to
change identities or guess a repo. Read the [multi-source contract](references/multi-source-contract.md).
