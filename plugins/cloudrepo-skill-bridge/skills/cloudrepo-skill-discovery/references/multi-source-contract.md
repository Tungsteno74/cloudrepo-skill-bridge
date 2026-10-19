# CloudRepo Skill Bridge — multi-source contract (0.2.0-alpha.1)

## Authorization and scope

Use only repositories deliberately associated with the current user task or
explicitly selected by the Root/Child under an existing authorization. A source
list is a **scope declaration**, not an authorization grant; neither it nor a
plugin install provides missing provider permissions. Never enumerate arbitrary
user/org repositories just to find a skill. Never infer a floating `main`, tag,
or latest commit; pin a full immutable Git commit ID for every source.

Valid roots: `.agents/skills`, `skills`, or `plugins/<canonical-name>/skills`.
External skills are **not** registered natively because their bytes can be read.
The normal local repository skill path is backward compatible and unchanged.

## Provider selection

- `local-git`: caller passes a separate checkout root. Verify exact root, remote
  GitHub identity, full HEAD, cleanliness and committed Git objects; reject any
  skill symlinks or non-regular files. No cloning, `git fetch` or branch writes.
- `github-public`: read-only unauthenticated GitHub REST for public source
  repositories, using the pinned commit, tree and Git blobs. Verify blob IDs,
  reject truncated tree responses, and bound files. Access denied/404/rate limit
  stops the adapter; never read stored GitHub CLI/browser credentials.
- `github-connector`: optional **injected provider** for a preauthorized
  GitHub read-only adapter. It can process private immutable Git object responses
  if that specific authenticated host exposes them, but the standalone CLI has
  no such adapter and returns `SOURCE_PROVIDER_UNAVAILABLE`. The bridge never
  copies or derives the connector's credentials.
- Authorized manual connector fallback: when the host has an *already connected*
  GitHub app but cannot inject a Python adapter, Root/Child can still read the
  same pinned commit/tree/blob through that app and label the result explicitly
  as **manual connector document fallback**, not CLI execution, native loading,
  or a complete local filesystem audit.

No `create_tree`, commits, workflows, PRs, environment setup, credential
escalation, or remote writes are part of this resolver.

## Result and ambiguity

Preserve `source_id`, `repository`, `commit`, `skill_root`, `provider` and the
per-skill source path. Source selection must be unique. If two approved sources
contain the same requested skill name and the caller did not choose `source_id`,
return `AMBIGUOUS_SKILL`; do not choose based on plugin installation order.

For local or GitHub source metadata, preserve `native_registration:
not_tested_by_bridge`, `execution_performed: false`, `authorization_granted:
false` and `activation: manual_remote_repository_fallback`. Reading files is
resolution only; applying instructions remains a separate authorized task step.
