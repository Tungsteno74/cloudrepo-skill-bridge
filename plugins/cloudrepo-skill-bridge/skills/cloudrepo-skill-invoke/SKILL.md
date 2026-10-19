---
name: cloudrepo-skill-invoke
description: >-
  Resolve task-relevant skills from the verified Git repository linked to
  Root or Child, including autonomous or explicit selection. Prefer proven
  native repo skill loading; otherwise use a bounded read-only fallback.
  Never claim manual execution is native plugin activation.
---

# CloudRepo Skill Bridge — repository skill invocation

**This skill is a resolver/orchestrator, not a native skill registration API.**
It never executes shell instructions automatically. Root and Child may select
this resolver implicitly when the current authorized task requires a repository
skill; the end user need not name or explicitly invoke this resolver. Read the
[invocation contract](references/invocation-contract.md) before selection.

## Required inputs

- A target skill selected by Root/Child from verified discovery and current
  task purpose, or explicitly specified by the caller. Require an unambiguous
  match; return target candidates to Root when selection is uncertain.
- Verified associated repository root or trusted provider repository identity.
- Full expected source commit or equivalent verified immutable revision.
- Current task permissions, approvals and prohibited side effects.
- The real host's provider/native skill discovery results when available.

Implicit selection and read-only resolution need no separate end-user
confirmation when covered by the current task. They do not authorize execution.
Do not infer permission for side effects from a plugin install, remote write
capabilities, implicit-invocation metadata, or a previous unrelated run. A Child
missing this context returns fields to Root instead of guessing.

## Resolution precedence

1. Try the supported native loader only if it can return the **same repository
   skill** with authoritative `scope=repo` and source path (or equivalent
   verified provenance). Distinguish a matching plugin-owned skill: it does not
   satisfy a request for the repository copy.
2. If the native repository locator is unavailable (not denied), select
   the uniquely task-relevant or caller-specified repository skill using the
   packaged CLI:

   ```text
   python <bridge-plugin-root>/runtime/cli.py resolve --repository-root <checkout-root> --expected-repository <owner/repo> --expected-commit <full-sha> --name <skill-name> --reference references/<requested-text-file>
   ```

   The command returns the verified `SKILL.md` and only explicitly requested
   reference text. It reports `activation=manual_repository_fallback`,
   `native_registration=not_tested_by_bridge` and `execution_performed=false`.
   These markers are **not** optional.
3. Where the runtime CLI is not available, a Root/Child with an already
   authorized repository connector may read the exact repository paths at a
   verified immutable ref and manually apply the same trust/scope checks. This
   is a document-reading fallback, not the complete local CLI security check.
4. The agent applies the selected instructions with existing user/host policy
   and approval rules, resolving more references only when actually needed.
   No execution of code, scripts, GitHub Actions, permission changes, branch
   edits or network writes occurs solely by calling this bridge.
5. Report explicit provenance and **two separate results**: resolution and
   actual work outcome. A successful document read is never an operational
   Windows CI pass. Never present manually applied instructions as a provider
   `skills.read` activation.

If a native provider returns 401/403, a security challenge, a policy denial,
wrong repository/revision or ambiguous identity, **stop**; do not substitute
manual reading to bypass the denial. An empty unrelated plugin inventory is
not such a denial and is not evidence of repo unavailability.

## External-repository invocation (multi-source)

Root/Child may autonomously select this resolver for an authorized task involving
skills published in a different repository. Obtain an **unambiguous** pinned
source from the multi-repository discovery contract; do not mistake the task's
associated Git checkout for the external repository.

When the packaged runtime and a caller-provided explicit source catalog are
available, read-only resolution is:

```text
python <bridge-plugin-root>/runtime/cli.py multi-resolve --sources-file <absolute-sources-json> --source-id <source-key> --name <task-relevant-skill> --reference references/<text-file>
```

The `source_id` selector is mandatory in practice whenever different sources
publish the same skill name. A native skill from a different plugin does not
become a native **repository** skill; do not substitute such a locator silently.
Do not recursively search GitHub or clone/install the external repository.

An already authorized GitHub connector can substitute read-only immutable Git
commit/tree/blob retrieval when the packaged CLI is not callable. Explicitly
label this `connector_document_fallback`, not `manual_remote_repository_fallback`
produced by the CLI. Treat 401/403, a security challenge, incomplete tree,
wrong source identity or unverified commit as terminal blockers, not triggers
for another identity, provider or new permission request.

Selecting and *reading* this resolver needs no end-user command naming it.
Executing instructions subsequently still uses ordinary user, Root, Child,
repository and provider approval gates; no cross-repository write is implicitly
authorized. The applicable boundaries are summarized in this skill's own
[invocation contract](references/invocation-contract.md); it has no mandatory
sibling-skill dependency.
