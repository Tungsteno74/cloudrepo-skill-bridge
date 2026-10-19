# Repository skill invocation contract — 0.1.0-alpha.3

## Selection and authorization

Root or Child may invoke this resolver **implicitly** when an already authorized
task needs a repository-local skill, or explicitly through a delegation or
prompt. An explicit request from the end user **naming this resolver** is not
required. The agent must still identify an unambiguous target skill from
verified discovery and task intent, or request the missing choice from Root;
never guess an unrelated skill.

Skill selection, manifest discovery and read-only resolution do not themselves
require a new confirmation when they fall within the existing task scope.
Resolving skill instructions is **not** authorization to execute them. Every
subsequent read/write/CI/tool action remains subject to existing user/host
permissions and approvals. Neither implicit invocation nor a Root handoff may
bypass denial, expand scope or create new credentials.

## Invocation state machine

```text
CONTEXT_REQUIRED -> NATIVE_REPO_LOADER_CHECK
    -> NATIVE_REPO_SELECTED
    -> MANUAL_REPOSITORY_RESOLVED
    -> USER_TASK_AUTHORIZATION_CHECK
    -> AGENT_APPLIES_INSTRUCTIONS -> RESULT
```

`MANUAL_REPOSITORY_RESOLVED` is a document/read state, never an executable
function call. Runtime writes and actual tool execution belong to the consuming
agent under the same user/provider authorization and checks it would need
without this plugin. The bridge grants no permissions and never promises
background work. Do not run references as executable scripts by default.

## Preference and evidence

Native repository loading requires authoritative source provenance (`scope=repo`,
repository-rooted path, verified Git revision). A `pluginId` source with the same
skill name is **not equivalent**. A provider skill read that succeeds from a
plugin proves only plugin availability. When the native provider refuses access,
do not reroute to another identity or an unapproved transport to bypass the
refusal. When the native provider is unavailable without a denial, the selected
local repository may be resolved in read-only fallback.

The original associated-checkout CLI never calls network APIs; the optional
multi-repository `github-public` CLI makes read-only GET requests for exact,
immutable GitHub objects when the executor permits it. Neither CLI path ever
executes any skill instruction or changes remote state.
The original CLI refuses dirty repositories by default for resolution; the exceptional
`--allow-dirty` requires separate explicit permission and must be labeled
unreproducible. `--expected-commit` and `--expected-repository` should be supplied
whenever an authoritative identity exists. Bound text resources must be named
explicitly relative to the skill root; absolute paths, `..`, symlinks and
oversized resources are rejected.

## Child handoff

Carry only repository identity, full HEAD SHA, skill name, requested reference
paths, relevant provenance (native locator or CLI resolution), user/task scope,
authorization and specific constraints. If the Child does not have this plugin,
Root may pass the **verified specific skill instructions** as part of an existing
task handoff; this does not imply that the Child loaded the plugin. A new task is
not created merely to overcome missing handoff context. This plugin does not
persist state, install itself or alter Root/global policies.

## Result fields

```text
REPOSITORY_SKILL_BRIDGE: <NATIVE_REPO|MANUAL_REPOSITORY|BLOCKED>
repository: <verified identity>
full_sha: <verified immutable commit>
name: <canonical skill name>
source_path: <repo-local SKILL.md>
native_locator: <actual provider locator or none>
registration: <verified_repo|not_verified>
execution: <not_started|success|failed|pending|blocked>
authorization_origin: <actual source or none>
side_effects: <observed actual changes or none>
```

A caller must not infer `execution=success` from a successful CLI invocation or
skill file read. Verification of side effects belongs to the owning executor.

## Multi-repository extension (0.2.0-alpha.1)

Source scope must be established separately for each repository. Every external
repository needs an approved canonical identity, **full immutable revision** and
allowed skill root. This is a bounded source allowlist (at most eight), not a
GitHub-wide discovery request. Repository root may be external to the task
checkout; no file need be copied into the task's repository.

An external skill is resolved via `multi-discover` / `multi-resolve` with an
explicit source catalog, or an already authorized connector's exact-revision
read-only APIs. GitHub's unauthenticated public adapter cannot read private
repositories. An explicit injected `github-connector` reader can use an already
approved private source, but the standalone CLI has no such adapter; it never
extracts plugin/CLI secrets or silently changes identities.
A Child unable to access the selected external source must return the exact
source identity/commit/root and failing capability to Root, not switch identity.

`AMBIGUOUS_SKILL`, `SOURCE_ACCESS_DENIED`, `WRONG_REPOSITORY`,
`WRONG_CHECKOUT`, `SOURCE_TREE_INCOMPLETE` and any provider denial stop automatic
fallback. Plugin-provenance, repo-provenance and manual document reading remain
separate. A successfully resolved external instruction does **not** authorize
any executable operation, CI, repository write or environment mutation.

The native associated-repository loader and the packaged local CLI are separate
from provider-hosted Cloud skill registration. Lack of native `scope=repo` or
lack of executable CLI in Current Cloud is a **non-blocking diagnostic TODO**:
never claim those paths succeeded when the connector/manual path was used.
