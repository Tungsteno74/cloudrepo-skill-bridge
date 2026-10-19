"""Multi-source integration, independent provider and security regression tests."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
from cloudrepo_skill_bridge import BridgeError  # noqa: E402
from cloudrepo_skill_bridge.multi_repository import (  # noqa: E402
    GitHubProvider, GitHubPublicFetcher, LocalGitProvider,
    MultiCloudRepoSkillBridge, SourceSpec, load_sources,
)


def git_blob(raw: bytes) -> str:
    data = b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw
    return hashlib.sha1(data).hexdigest()


class Fixture(unittest.TestCase):
    """Create two isolated immutable Git repos with different source layouts."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="cloudcodex-multirepo-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.a, self.a_sha = self.init_repo("alpha", "alpha-skill", ".agents/skills")
        self.b, self.b_sha = self.init_repo("beta", "beta-skill", "plugins/beta-plugin/skills")

    def git(self, folder: Path, *args: str) -> str:
        process = subprocess.run(
            ["git", "-C", str(folder), *args],
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        return process.stdout.strip()

    def init_repo(self, repo: str, skill: str, skill_root: str):
        folder = self.folder / repo
        directory = folder / skill_root / skill
        (directory / "references").mkdir(parents=True)
        (directory / "agents").mkdir()
        (directory / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: >-\n  The test skill.\n---\n\n# Test\nRead marker.\n", encoding="utf-8"
        )
        (directory / "references" / "marker.txt").write_text(
            f"MARKER-{repo.upper()}\n", encoding="utf-8"
        )
        (directory / "agents" / "openai.yaml").write_text(
            "policy:\n  allow_implicit_invocation: true\n", encoding="utf-8"
        )
        self.git(folder, "init", "-q", "--initial-branch=main")
        self.git(folder, "config", "user.name", "Fixture")
        self.git(folder, "config", "user.email", "fixture@example.invalid")
        self.git(folder, "remote", "add", "origin", f"https://github.com/Tungsteno74/{repo}.git")
        self.git(folder, "add", "-A")
        self.git(folder, "commit", "-qm", "seed")
        return folder, self.git(folder, "rev-parse", "HEAD")

    def sources(self):
        return [
            SourceSpec("project", "Tungsteno74/alpha", self.a_sha, ".agents/skills", "local-git", str(self.a)),
            SourceSpec("plugin", "Tungsteno74/beta", self.b_sha, "plugins/beta-plugin/skills", "local-git", str(self.b)),
        ]

    def assert_code(self, callback, code):
        with self.assertRaises(BridgeError) as context:
            callback()
        self.assertEqual(context.exception.code, code)

    def test_multi_source_discovery(self):
        actual = MultiCloudRepoSkillBridge(self.sources()).discover()
        self.assertEqual(actual["native_registration"], "not_tested_by_bridge")
        self.assertEqual([s["source_id"] for s in actual["sources"]], ["project", "plugin"])
        self.assertEqual([[e["name"] for e in s["skills"]] for s in actual["sources"]], [["alpha-skill"], ["beta-skill"]])
        self.assertEqual(actual["sources"][1]["skills"][0]["relative_path"],
                         "plugins/beta-plugin/skills/beta-skill/SKILL.md")

    def test_remote_plugin_layout_from_second_checkout_resolves(self):
        result = MultiCloudRepoSkillBridge(self.sources()).resolve(
            "beta-skill", references=["references/marker.txt"]
        )
        self.assertEqual(result["activation"], "manual_remote_repository_fallback")
        self.assertEqual(result["source"]["repository"], "Tungsteno74/beta")
        self.assertEqual(result["references"][0]["content"], "MARKER-BETA\n")
        self.assertFalse(result["authorization_granted"])
        self.assertFalse(result["execution_performed"])
        self.assertEqual(self.git(self.a, "status", "--porcelain"), "")
        self.assertEqual(self.git(self.b, "status", "--porcelain"), "")

    def test_discriminator_avoids_scanning_unselected_sources(self):
        spec = self.sources()[1]
        self.assertEqual(
            MultiCloudRepoSkillBridge(self.sources()).resolve("beta-skill", source_id=spec.source_id)["skill"]["name"],
            "beta-skill",
        )
        self.assert_code(lambda: MultiCloudRepoSkillBridge(self.sources()).resolve("beta-skill", source_id="missing"), "SOURCE_NOT_FOUND")

    def test_blocks_ambiguous_names_across_sources(self):
        # Add a second skill with an identical name and re-pin the new commit.
        same = self.b / "plugins/beta-plugin/skills/alpha-skill"
        same.mkdir()
        (same / "SKILL.md").write_text("---\nname: alpha-skill\ndescription: Test\n---\n", encoding="utf-8")
        self.git(self.b, "add", "-A")
        self.git(self.b, "commit", "-qm", "add collision")
        other = SourceSpec("plugin", "Tungsteno74/beta", self.git(self.b, "rev-parse", "HEAD"), "plugins/beta-plugin/skills", "local-git", str(self.b))
        bridge = MultiCloudRepoSkillBridge((self.sources()[0], other))
        self.assert_code(lambda: bridge.resolve("alpha-skill"), "AMBIGUOUS_SKILL")
        self.assertEqual(bridge.resolve("alpha-skill", source_id="project")["source"]["source_id"], "project")

    def test_rejects_unpinned_or_conflicting_checkout(self):
        items = self.sources()
        wrong = SourceSpec("plugin", "Tungsteno74/beta", "f" * 40, "plugins/beta-plugin/skills", "local-git", str(self.b))
        self.assert_code(lambda: MultiCloudRepoSkillBridge((wrong,)).discover(), "WRONG_CHECKOUT")
        wrong_repo = SourceSpec("plugin", "Tungsteno74/not-beta", self.b_sha, "plugins/beta-plugin/skills", "local-git", str(self.b))
        self.assert_code(lambda: MultiCloudRepoSkillBridge((wrong_repo,)).discover(), "WRONG_REPOSITORY")
        (self.b / "README.md").write_text("dirty", encoding="utf-8")
        self.assert_code(lambda: MultiCloudRepoSkillBridge((items[1],)).discover(), "DIRTY_REPOSITORY")

    def test_rejects_source_path_traversal_and_invalid_provider(self):
        for bad in ("../skills", "/tmp/skills", "other/skills", "plugins/../skills", "plugins/bridge/../../../skills"):
            with self.subTest(path=bad):
                self.assert_code(lambda: SourceSpec("bad", "Tungsteno74/alpha", self.a_sha, bad, "local-git", str(self.a)), "SOURCE_INVALID")
        self.assert_code(lambda: SourceSpec("bad", "Tungsteno74/alpha", self.a_sha, "skills", "arbitrary", str(self.a)), "SOURCE_INVALID")
        self.assert_code(lambda: SourceSpec("bad", "Tungsteno74/alpha", "main", "skills", "local-git", str(self.a)), "SOURCE_INVALID")
        self.assert_code(lambda: SourceSpec("bad", "Tungsteno74/alpha", self.a_sha, "skills", "github-public", str(self.a)), "SOURCE_INVALID")
        self.assert_code(lambda: SourceSpec("bad", "Tungsteno74/alpha", self.a_sha, "skills", "local-git", "relative"), "SOURCE_INVALID")

    def test_rejects_non_github_remote_identity(self):
        self.git(self.b, "remote", "set-url", "origin", "https://untrusted.example/Tungsteno74/beta.git")
        self.assert_code(
            lambda: MultiCloudRepoSkillBridge((self.sources()[1],)).discover(),
            "WRONG_REPOSITORY",
        )

    def test_source_catalog_rejects_wrong_field_types(self):
        catalog = self.folder / "invalid-sources.json"
        source = self.sources()[0]
        entry = dict(source_id=12, repository=source.repository, commit=source.commit,
                     skill_root=source.skill_root, provider=source.provider,
                     checkout_root=source.checkout_root)
        catalog.write_text(json.dumps({"sources": [entry]}), encoding="utf-8")
        self.assert_code(lambda: load_sources(catalog), "SOURCE_INVALID")

    def test_rejects_ambiguous_source_ids(self):
        first, second = self.sources()
        self.assert_code(lambda: MultiCloudRepoSkillBridge((first, first)), "DUPLICATE_SOURCE")
        self.assert_code(lambda: MultiCloudRepoSkillBridge(tuple()), "SOURCE_CATALOG_INVALID")
        self.assert_code(lambda: MultiCloudRepoSkillBridge((first,) * 9), "SOURCE_CATALOG_INVALID")

    def test_rejects_untrusted_reference_paths(self):
        bridge = MultiCloudRepoSkillBridge(self.sources())
        for bad in ("../../README.md", "references/../../../x", "/etc/passwd", ".agents/skills", "references\\marker.txt", "references//marker.txt"):
            with self.subTest(path=bad):
                self.assert_code(lambda: bridge.resolve("beta-skill", references=[bad]), "UNSAFE_REFERENCE")
        self.assert_code(lambda: bridge.resolve("beta-skill", references=["references/marker.txt"] * 2), "DUPLICATE_REFERENCE")
        self.assert_code(lambda: bridge.resolve("beta-skill", references=["references/missing.txt"]), "RESOURCE_NOT_FOUND")

    def test_rejects_git_symlink_without_following(self):
        link = self.b / "plugins/beta-plugin/skills/beta-skill/references/reference.txt"
        try:
            link.symlink_to(self.b / "README.md")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlink unsupported: {exc}")
        self.git(self.b, "add", "-A")
        self.git(self.b, "commit", "-qm", "symlink")
        current = SourceSpec("plugin", "Tungsteno74/beta", self.git(self.b, "rev-parse", "HEAD"), "plugins/beta-plugin/skills", "local-git", str(self.b))
        self.assert_code(lambda: MultiCloudRepoSkillBridge((current,)).discover(), "UNSAFE_SYMLINK")

    def test_cli_multi_local_full_cycle(self):
        catalog = self.folder / "sources.json"
        catalog.write_text(json.dumps({"sources": [dict(
            source_id=source.source_id, repository=source.repository,
            commit=source.commit, skill_root=source.skill_root,
            provider=source.provider, checkout_root=source.checkout_root,
        ) for source in self.sources()]}), encoding="utf-8")
        base = [sys.executable, str(ROOT / "runtime/cli.py")]
        discover = subprocess.run(base + ["multi-discover", "--sources-file", str(catalog)], capture_output=True, text=True, check=True)
        result = json.loads(discover.stdout)
        self.assertEqual(len(result["sources"]), 2)
        resolve = subprocess.run(base + ["multi-resolve", "--sources-file", str(catalog), "--name", "beta-skill", "--source-id", "plugin", "--reference", "references/marker.txt"], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(resolve.stdout)["references"][0]["content"], "MARKER-BETA\n")
        wrong = subprocess.run(base + ["multi-resolve", "--sources-file", str(catalog), "--name", "beta-skill", "--source-id", "unlisted"], capture_output=True, text=True)
        self.assertEqual(wrong.returncode, 2)
        self.assertEqual(json.loads(wrong.stdout)["code"], "SOURCE_NOT_FOUND")

    def test_catalog_declares_no_global_discovery(self):
        catalog = self.folder / "sources.json"
        catalog.write_text(json.dumps({"sources": [{"source_id": "one", "repository": "Tungsteno74/alpha", "commit": self.a_sha,
                "skill_root": ".agents/skills", "provider": "local-git", "checkout_root": str(self.a)}]}), encoding="utf-8")
        self.assertEqual(len(load_sources(catalog)), 1)
        catalog.write_text(json.dumps({"sources": [{"source_id": "one", "repository": "Tungsteno74/alpha", "commit": self.a_sha,
                "skill_root": ".agents/skills", "provider": "local-git", "checkout_root": str(self.a), "token": "secret"}]}))
        self.assert_code(lambda: load_sources(catalog), "SOURCE_CATALOG_INVALID")
        catalog.write_text("{" + "x" * 65536)
        self.assert_code(lambda: load_sources(catalog), "SOURCE_CATALOG_INVALID")


class FakeGitHub:
    """Simulate a GitHub connector / HTTP transport without any network calls."""

    def __init__(self, repository="Tungsteno74/example", commit="a" * 40, skill="example-plugin-skill"):
        self.repository = repository
        self.commit = commit
        self.skill = skill
        self.tree_sha = "b" * 40
        self.contents: Dict[str, bytes] = {}
        root = f"plugins/example-plugin/skills/{skill}"
        self.contents[root + "/SKILL.md"] = (f"---\nname: {skill}\ndescription: >-\n  Remote instruction.\n---\n\n# Procedure\nRead the marker.\n").encode()
        self.contents[root + "/references/marker.txt"] = b"REMOTE-MARKER-ORIGIN\n"
        self.contents[root + "/agents/openai.yaml"] = b"policy:\n  allow_implicit_invocation: true\n"
        self.modes: Dict[str, str] = {}
        self.truncated = False
        self.private = False
        self.tamper = False
        self.reported_repo = None
        self.reported_commit = None
        self.calls = []

    def get_json(self, path: str) -> Mapping[str, object]:
        self.calls.append(path)
        prefix = "repos/" + self.repository
        if path == prefix:
            return {"full_name": self.reported_repo or self.repository, "private": self.private}
        if path == prefix + "/git/commits/" + self.commit:
            return {"sha": self.reported_commit or self.commit, "tree": {"sha": self.tree_sha}}
        if path == prefix + "/git/trees/" + self.tree_sha + "?recursive=1":
            entries = [{"path": name, "mode": self.modes.get(name, "100644"), "type": "blob", "sha": git_blob(blob), "size": len(blob)} for name, blob in self.contents.items()]
            return {"sha": self.tree_sha, "truncated": self.truncated, "tree": entries}
        if path.startswith(prefix + "/git/blobs/"):
            oid = path.rsplit("/", 1)[-1]
            for blob in self.contents.values():
                if git_blob(blob) == oid:
                    b = (b"X" + blob[1:]) if self.tamper else blob
                    return {"sha": oid, "encoding": "base64", "content": base64.b64encode(b).decode(), "size": len(b)}
        raise AssertionError("Unexpected or unpinned GitHub request: " + path)


class GitHubProviderTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGitHub()
        self.source = SourceSpec("external", self.fake.repository, self.fake.commit, "plugins/example-plugin/skills", "github-public")

    def bridge(self):
        return MultiCloudRepoSkillBridge((self.source,), providers={"github-public": GitHubProvider(self.fake)})

    def assert_code(self, fn, code):
        with self.assertRaises(BridgeError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_github_connector_adapter_end_to_end(self):
        b = self.bridge()
        result = b.discover()
        self.assertEqual(result["sources"][0]["skills"][0]["name"], self.fake.skill)
        resolved = b.resolve(self.fake.skill, references=["references/marker.txt"])
        self.assertEqual(resolved["references"][0]["content"], "REMOTE-MARKER-ORIGIN\n")
        self.assertEqual(resolved["source"]["repository"], self.fake.repository)
        self.assertEqual(resolved["native_registration"], "not_tested_by_bridge")
        self.assertEqual(resolved["activation"], "manual_remote_repository_fallback")
        self.assertTrue(all("/git/" in path or path == "repos/" + self.fake.repository for path in self.fake.calls))
        self.assertIn(self.fake.commit, self.fake.calls[1])

    def test_wrong_commit_or_repo_is_blocked(self):
        self.fake.reported_repo = "Tungsteno74/different"
        self.assert_code(lambda: self.bridge().discover(), "WRONG_REPOSITORY")
        self.fake.reported_repo = None
        self.fake.reported_commit = "f" * 40
        self.assert_code(lambda: self.bridge().discover(), "WRONG_CHECKOUT")

    def test_private_repo_rejected_by_public_adapter(self):
        self.fake.private = True
        self.assert_code(lambda: self.bridge().discover(), "SOURCE_ACCESS_DENIED")

    def test_authorized_private_connector_adapter_reads_exact_source(self):
        self.fake.private = True
        target = SourceSpec("private", self.fake.repository, self.fake.commit,
                            "plugins/example-plugin/skills", "github-connector")
        result = MultiCloudRepoSkillBridge(
            (target,), providers={"github-connector": GitHubProvider(self.fake, allow_private=True)}
        ).resolve(self.fake.skill, references=["references/marker.txt"])
        self.assertEqual(result["source"]["provider"], "github-connector")
        self.assertEqual(result["references"][0]["content"], "REMOTE-MARKER-ORIGIN\n")
        self.assertFalse(result["execution_performed"])

    def test_private_source_does_not_fall_back_to_public_unauthenticated(self):
        target = SourceSpec("private", self.fake.repository, self.fake.commit,
                            "plugins/example-plugin/skills", "github-connector")
        self.assert_code(lambda: MultiCloudRepoSkillBridge((target,)).discover(), "SOURCE_PROVIDER_UNAVAILABLE")
        self.assert_code(lambda: GitHubProvider(allow_private=True), "SOURCE_PROVIDER_UNAVAILABLE")

    def test_truncated_tree_blocked(self):
        self.fake.truncated = True
        self.assert_code(lambda: self.bridge().discover(), "SOURCE_TREE_INCOMPLETE")

    def test_git_tree_symlink_refused(self):
        root = f"plugins/example-plugin/skills/{self.fake.skill}"
        self.fake.modes[root + "/references/marker.txt"] = "120000"
        self.assert_code(lambda: self.bridge().discover(), "UNSAFE_SYMLINK")

    def test_git_blob_integrity_checked(self):
        self.fake.tamper = True
        self.assert_code(lambda: self.bridge().resolve(self.fake.skill), "GIT_OBJECT_MISMATCH")

    def test_provider_access_denial_stops_resolution(self):
        class Denied:
            def get_json(self, path):
                raise BridgeError("SOURCE_ACCESS_DENIED", "Provider denied access")
        b = MultiCloudRepoSkillBridge((self.source,), providers={"github-public": GitHubProvider(Denied())})
        self.assert_code(lambda: b.resolve(self.fake.skill), "SOURCE_ACCESS_DENIED")

    def test_reference_not_in_tree_rejected(self):
        self.assert_code(lambda: self.bridge().resolve(self.fake.skill, references=["references/absent.txt"]), "RESOURCE_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
