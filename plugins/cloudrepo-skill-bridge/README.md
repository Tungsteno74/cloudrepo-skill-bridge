# CloudRepo Skill Bridge

**Version:** 0.2.0 — private Agent Plugins 1.0.

Visible family: **CloudRepo** (provider-neutral Git repository tools). The canonical package ID `cloudrepo-skill-bridge` and renamed skills `cloudrepo-skill-discovery` / `cloudrepo-skill-invoke` are the native identifiers in this package; previous plugin identities are not aliases. This package is a new plugin identity, not an in-place update of an earlier plugin. — independent private Agent Plugin 1.0 prototype.

Two self-contained plugin skills:

- `cloudrepo-skill-discovery`: verify repository identity, full revision and
  skill manifests without executing instructions.
- `cloudrepo-skill-invoke`: allow Root/Child to select a task-relevant
  repository skill implicitly or explicitly, prefer authoritative native
  `scope=repo` provenance, otherwise use a bounded **manual** read-only fallback.
  The end user need not name the resolver; operational side effects still require
  existing permissions and approvals.

The bridge is independent of CloudCodeX Environment Discovery and Windows
Bootstrap. It does not require Current Cloud environment APIs, assume a startup
`cwd`, change `AGENTS.md`, update configuration or grant tool permissions.

The independent two-repository E2E (Windows fixture and a separate provider-neutral
fixture) passed for **manual read-only instruction resolution**. Native
repository-skill discovery and execution of the packaged Python CLI inside the
Current Cloud task have not been demonstrated; they are tracked as non-blocking
TODOs, not a reason to repeat those tests.

## Local CLI

Requires Python 3.9+ and Git for local checkouts, with PyYAML as an explicit runtime dependency (see
`runtime/requirements.txt`) and no remote writes. The original associated-checkout commands do not access the
network; the optional multi-repository `github-public` commands use bounded,
read-only GitHub API GET requests. The plugin must be loaded in the host and
the associated repository must already exist locally for the original commands. Give an **absolute path to the exact
repository root**, not `/workspace` if the repository is mounted below it.

```sh
python runtime/cli.py discover \
  --repository-root /workspace/owner-project \
  --expected-commit <verified-full-HEAD> \
  --expected-repository owner/project

python runtime/cli.py resolve \
  --repository-root /workspace/owner-project \
  --expected-commit <verified-full-HEAD> \
  --expected-repository owner/project \
  --name my-repo-skill \
  --reference references/procedure.md
```

The `resolve` command **only returns verified instruction text**. It reports
`manual_repository_fallback`, `execution_performed=false`, and no native loader
proof. The consuming Root/Child is responsible for checking current scope and
provider authorization before carrying out any operational steps. No skill code
is executed by this tool.

If the task is in ChatGPT Root without direct filesystem access, the skill
contract permits a GitHub connector-backed exact-revision read using an already
connected authorized account, but such a read must not be described as native
loading or complete local symlink validation.

## Multi-repository support (0.2.0-alpha.1)

The caller/Root declares a **bounded, explicit allowlist** of source repositories
with full immutable commits and validated skill-root layouts. A source may be the
associated repository or an independently checked-out plugin repository. This
is never a global GitHub repository scan and does not alter the task checkout.

Supported skill roots: `.agents/skills`, `skills` (standalone plugin root) and
`plugins/<plugin-name>/skills` (existing CloudCodeX and CloudRepo plugin source repositories).

Example `sources.json` supplied by the caller (absolute file path):

```json
{
  "sources": [
    {
      "source_id": "environment-discovery",
      "repository": "Tungsteno74/cloudcodex-environment-discovery",
      "commit": "<exact-full-commit-from-GitHub>",
      "skill_root": "plugins/cloudcodex-environment-discovery/skills",
      "provider": "github-public"
    },
    {
      "source_id": "direct-ci",
      "repository": "Tungsteno74/cloudrepo-environment-direct",
      "commit": "<exact-full-commit-from-GitHub>",
      "skill_root": "plugins/cloudrepo-environment-direct/skills",
      "provider": "github-public"
    }
  ]
}
```

```sh
python runtime/cli.py multi-discover --sources-file /absolute/path/sources.json
python runtime/cli.py multi-resolve \
  --sources-file /absolute/path/sources.json \
  --source-id direct-ci \
  --name github-actions-direct \
  --reference references/<approved-text-file>
```

`local-git` is also supported, with `checkout_root` set to the absolute path of
an **already present, clean checkout** that matches the pinned commit and GitHub
remote. The CLI does not clone, fetch, install, execute scripts or modify Git.

A third provider name, `github-connector`, is reserved for callers that inject
an *already authorized* GitHub JSON reader implementing the same bounded GET
interface. It may read private sources only with such an injected reader; the
standalone CLI never manufactures connector access and returns
`SOURCE_PROVIDER_UNAVAILABLE` when it is not wired. No OAuth tokens, browser
cookies or GitHub CLI credentials are read by the bridge.

For public GitHub repositories, the optional `github-public` adapter uses only
unauthenticated GET requests to the GitHub API for the exact commit, tree and
blob; it verifies blob integrity, rejects symlinks and bounded-resource errors,
and stops on 401/403/404 or incomplete source. The provider is injectable for
host-controlled read-only adapters. Network access remains contingent on the
actual executor's egress policy and GitHub API rate limits.

**Private repositories:** the unauthenticated CLI adapter cannot read them. A
Root/Child with an *already connected* GitHub connector may perform the
read-only pinned-commit/tree/blob workflow manually as
`connector_document_fallback`, preserving provenance. That is not evidence that
the CLI ran or that the source was registered natively. The adapter does not
copy connector credentials, create accounts or request broader permissions.

Duplicate skill names across permitted sources produce `AMBIGUOUS_SKILL` unless
`--source-id` selects one explicitly. All outcomes retain source repository,
commit, root, read method, `native_registration=not_tested_by_bridge`,
`execution_performed=false` and `authorization_granted=false`.

## Pending non-blocking diagnostics

- **TODO — Current Cloud native loading:** determine why repository-local skills
  are not exposed as authoritative `scope=repo` locators when the agent starts
  outside the associated checkout.
- **TODO — Python CLI in hosted task:** verify the packaged runtime is actually
  accessible/executable in Current Cloud. A successful manual or connector
  fallback is valid without this verification.
- **TODO — multi-repository live Current Cloud:** verify a freshly published
  Alpha loads both Bridge skills and resolves an approved external source via
  an authorized connector or enabled runtime; use the result before resuming
  the separately scoped three-gate Cloud E2E pipeline.

## Failure boundaries

- Bad or missing exact repository context: stop; do not recursively search
  unrelated workspaces.
- Wrong expected full SHA: `WRONG_CHECKOUT`.
- Symlinks, path traversal, invalid `SKILL.md` frontmatter or unbounded resources:
  blocked with an explicit code.
- Dirty repository: `discover` can report it, but `resolve` blocks by default.
- Native provider denial: do not use another account or manual fallback to
  bypass it; unavailable native plugin catalog alone is not a denial.
- Plug-in names colliding with repository skills: distinguish by provenance,
  never silently substitute plugin content.

## Testing

```sh
python -m unittest discover -s tests -v
python -m compileall -q runtime
```

The plugin is a private alpha and is **not** added to the public GSM marketplace
until independently validated and deliberately promoted. No changes to existing
CloudCodeX plugins, policies or GitHub Actions resources are required.

## Previous Cloud provisioning experiment

`cloudcodex-windows-bootstrap-alpha` (0.7.0-alpha.1) attempted to copy five pinned GitHub skill directories into Current Cloud `$HOME/.agents/skills` using `install_script`. Copies worked in writable test directories, but persistent installation and native skill discovery across Current Cloud tasks were not achieved. File copying alone does **not** register native skills; do not revive that approach without proof of both persistence and discovery.

## Parser, transport and host boundaries (0.2.0)

- The packaged Python CLI uses PyYAML >=6.0.2,<7 for type-safe YAML frontmatter
  and agent policy. It does not install that dependency, alter an environment or
  expose a native Cloud tool by itself; install requirements only through an
  approved host setup. A missing dependency returns YAML_PARSER_UNAVAILABLE.
- Multi-source resolution isolates the selected skill from invalid siblings;
  discovery of a complete source still validates all its skill manifests.
- GitHub public source reads reject HTTP redirects before following them.
  Executable Git blobs may be read, but no skill scripts are ever executed.
- Windows CLI JSON is ASCII-safe independently of the active terminal code page.
- These fixes do not demonstrate that Current Cloud exposes the plugin runtime
  or that the provider's native skill loader supports repository-local skills.


## Brand asset provenance (0.2.0)

The plugin icon reuses the unmodified exterior cloud silhouette, colors and
lighting of the Windows Bootstrap icon from:
`https://github.com/Tungsteno74/cloudcodex-windows-bootstrap/blob/main/plugins/cloudcodex-windows-bootstrap/assets/icon.png`.
The source PNG SHA-256 is
`0f3c54427464a5dc843c599814328057654d4250e174f578d0c342ce69383ea8`.
Only the internal Windows emblem is replaced with a book/skill manifest
connected to three Git repository nodes. The central background is reconstructed
inside the replaced emblem. Image dimensions remain 1254x1254 RGBA. The new
plugin identity is `cloudrepo-skill-bridge` and its author is `Tungsteno74`.
