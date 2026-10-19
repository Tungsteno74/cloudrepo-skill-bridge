"""Offline behavioral, safety and provenance tests for the bridge."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BRIDGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BRIDGE_ROOT / "runtime"))

from cloudrepo_skill_bridge import BridgeError, CloudRepoSkillBridge  # noqa: E402


class RepositoryFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="repo-skill-bridge-test-")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.repo = self.workspace / "fixture"
        self.repo.mkdir()
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.git("remote", "add", "origin", "https://github.com/Tungsteno74/fixture.git")
        self.make_skill("example-skill", implicit=False)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "test: seed repository skill")
        self.head = self.git("rev-parse", "HEAD")

    def git(self, *args: str) -> str:
        process = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
        )
        return process.stdout.strip()

    def make_skill(self, name: str, *, implicit: bool = False) -> None:
        skill = self.repo / ".agents" / "skills" / name
        (skill / "references").mkdir(parents=True, exist_ok=True)
        (skill / "agents").mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: >-\n  Test read-only procedure.\n---\n"
            "\n# Test skill\nRead the marker; change nothing.\n",
            encoding="utf-8",
        )
        (skill / "agents" / "openai.yaml").write_text(
            "interface:\n  display_name: Test\n"
            "policy:\n"
            f"  allow_implicit_invocation: {str(implicit).lower()}\n",
            encoding="utf-8",
        )
        (skill / "references" / "marker.txt").write_text(
            "PROBE-FIXTURE-SECRET-FROM-DISK\n", encoding="utf-8"
        )

    def bridge(self, *, expected_repository: str = "Tungsteno74/fixture") -> CloudRepoSkillBridge:
        return CloudRepoSkillBridge(
            self.repo,
            expected_commit=self.head,
            expected_repository=expected_repository,
        )

    def assert_blocked(self, operation, expected_code: str) -> None:
        with self.assertRaises(BridgeError) as raised:
            operation()
        self.assertEqual(raised.exception.code, expected_code)

    def test_discovery_returns_canonical_provenance(self) -> None:
        bridge = self.bridge()
        entries = bridge.discover()
        self.assertEqual([item.name for item in entries], ["example-skill"])
        self.assertEqual(entries[0].implicit_invocation_allowed, False)
        self.assertTrue(entries[0].metadata_present)
        self.assertEqual(bridge.repository.repository_id, "github.com/Tungsteno74/fixture")
        self.assertTrue(bridge.repository.clean)

    def test_resolve_returns_text_without_executing(self) -> None:
        resolution = self.bridge().resolve(
            "example-skill", references=["references/marker.txt"]
        ).as_dict()
        self.assertEqual(resolution["activation"], "manual_repository_fallback")
        self.assertEqual(resolution["native_registration"], "not_tested_by_bridge")
        self.assertFalse(resolution["execution_performed"])
        self.assertFalse(resolution["authorization_granted"])
        self.assertIn("PROBE-FIXTURE-SECRET-FROM-DISK", resolution["references"][0]["content"])
        self.assertEqual(resolution["repository"]["head"], self.head)
        self.assertNotIn("https://", json.dumps(resolution["repository"]))
        self.assertFalse(self.git("status", "--porcelain"))

    def test_rejects_wrong_commit(self) -> None:
        self.assert_blocked(
            lambda: CloudRepoSkillBridge(self.repo, expected_commit="0" * 40),
            "WRONG_CHECKOUT",
        )

    def test_rejects_wrong_repository_identity(self) -> None:
        self.assert_blocked(lambda: self.bridge(expected_repository="Other/fixture"), "WRONG_REPOSITORY")

    def test_rejects_parent_path_not_actual_git_root(self) -> None:
        self.assert_blocked(lambda: CloudRepoSkillBridge(self.workspace), "GIT_READ_FAILED")

    def test_rejects_invalid_names_and_paths(self) -> None:
        bridge = self.bridge()
        for invalid in ("../example-skill", "Example-Skill", "a/b", "", "x\\y"):
            with self.subTest(invalid=invalid):
                self.assert_blocked(lambda: bridge.resolve(invalid), "INVALID_SKILL_NAME")
        self.assert_blocked(lambda: bridge.resolve("unknown-skill"), "SKILL_NOT_FOUND")

    def test_rejects_reference_path_traversal(self) -> None:
        bridge = self.bridge()
        for path in ("../AGENTS.md", "/etc/passwd", "references/../../x", "./references/marker.txt", "references\\marker.txt"):
            with self.subTest(path=path):
                self.assert_blocked(
                    lambda: bridge.resolve("example-skill", references=[path]),
                    "UNSAFE_REFERENCE",
                )

    def test_rejects_duplicate_references(self) -> None:
        self.assert_blocked(
            lambda: self.bridge().resolve("example-skill", references=["references/marker.txt"] * 2),
            "DUPLICATE_REFERENCE",
        )

    def test_rejects_dirty_repository_by_default(self) -> None:
        (self.repo / "README.md").write_text("uncommitted\n", encoding="utf-8")
        bridge = self.bridge()
        self.assertFalse(bridge.repository.clean)
        self.assert_blocked(lambda: bridge.resolve("example-skill"), "DIRTY_REPOSITORY")
        self.assertEqual(bridge.resolve("example-skill", allow_dirty=True).skill.name, "example-skill")

    def test_detects_invalid_frontmatter(self) -> None:
        (self.repo / ".agents/skills/example-skill/SKILL.md").write_text(
            "---\nname: different-skill\ndescription: test\n---\n", encoding="utf-8"
        )
        self.assert_blocked(lambda: self.bridge().discover(), "MANIFEST_INVALID")

    def test_rejects_unsafe_symlink_in_skill_tree(self) -> None:
        target = self.repo / ".agents/skills/example-skill/references/escape"
        try:
            target.symlink_to(self.repo / "README.md")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlinks not available: {exc}")
        self.assert_blocked(lambda: self.bridge().discover(), "UNSAFE_SYMLINK")

    def test_rejects_oversized_skill(self) -> None:
        (self.repo / ".agents/skills/example-skill/SKILL.md").write_text(
            "X" * 300000, encoding="utf-8"
        )
        self.assert_blocked(lambda: self.bridge().discover(), "RESOURCE_TOO_LARGE")

    def test_keeps_optional_metadata_optional(self) -> None:
        (self.repo / ".agents/skills/example-skill/agents/openai.yaml").unlink()
        entry = self.bridge().discover()[0]
        self.assertFalse(entry.metadata_present)
        self.assertIsNone(entry.implicit_invocation_allowed)

    def test_does_not_expose_embedded_token_in_remote(self) -> None:
        self.git("remote", "set-url", "origin", "https://token-should-not-leak@github.com/Tungsteno74/fixture.git")
        report = self.bridge().repository.as_dict()
        self.assertEqual(report["remote_identity"], "github.com/Tungsteno74/fixture")
        self.assertNotIn("token-should-not-leak", json.dumps(report))

    def test_cli_json_discover_and_resolve(self) -> None:
        command = [
            sys.executable,
            str(BRIDGE_ROOT / "runtime" / "cli.py"),
            "discover",
            "--repository-root", str(self.repo),
            "--expected-commit", self.head,
            "--expected-repository", "Tungsteno74/fixture",
        ]
        found = subprocess.run(command, capture_output=True, text=True, check=True)
        data = json.loads(found.stdout)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(len(data["skills"]), 1)
        self.assertEqual(data["native_registration"], "not_tested_by_bridge")
        to_resolve = command.copy()
        to_resolve[2] = "resolve"
        to_resolve.extend(["--name", "example-skill", "--reference", "references/marker.txt"])
        resolved = subprocess.run(to_resolve, capture_output=True, text=True, check=True)
        outcome = json.loads(resolved.stdout)
        self.assertEqual(outcome["status"], "ready_for_manual_execution")
        self.assertEqual(len(outcome["references"]), 1)

    def test_valid_implicit_metadata_still_requires_explicit_resolve(self) -> None:
        (self.repo / ".agents/skills/example-skill/agents/openai.yaml").write_text(
            "policy:\n  allow_implicit_invocation: true\n", encoding="utf-8"
        )
        entry = self.bridge().discover()[0]
        self.assertTrue(entry.implicit_invocation_allowed)
        self.assertEqual(self.bridge().resolve("example-skill", allow_dirty=True).skill.name, "example-skill")

    def test_rejects_reference_symlink(self) -> None:
        target = self.repo / ".agents/skills/example-skill/references/escape.txt"
        try:
            target.symlink_to(self.repo / ".agents/skills/example-skill/references/marker.txt")
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        self.assert_blocked(
            lambda: self.bridge().resolve("example-skill", references=["references/escape.txt"], allow_dirty=True),
            "UNSAFE_SYMLINK",
        )

    def test_rejects_missing_reference_file(self) -> None:
        self.assert_blocked(
            lambda: self.bridge().resolve("example-skill", references=["references/not-here.txt"]),
            "UNSAFE_REFERENCE",
        )

    def test_rejects_nested_skill_root_symlink(self) -> None:
        path = self.repo / ".agents/skills"
        other = self.repo / ".agents/real-skills"
        path.rename(other)
        try:
            path.symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        self.assert_blocked(lambda: self.bridge().discover(), "UNSAFE_SYMLINK")

    def test_rejects_duplicate_implicit_metadata_flags(self) -> None:
        (self.repo / ".agents/skills/example-skill/agents/openai.yaml").write_text(
            "policy:\n  allow_implicit_invocation: true\n  allow_implicit_invocation: false\n",
            encoding="utf-8",
        )
        self.assert_blocked(lambda: self.bridge().discover(), "METADATA_INVALID")

    def test_empty_root_and_deterministic_discovery(self) -> None:
        import shutil
        shutil.rmtree(self.repo / ".agents")
        self.assertEqual(self.bridge().discover(), [])

    def test_rejects_absolute_root_missing(self) -> None:
        self.assert_blocked(lambda: CloudRepoSkillBridge(Path(".")), "ABSOLUTE_ROOT_REQUIRED")

    def test_cli_error_contract(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(BRIDGE_ROOT / "runtime/cli.py"), "discover",
             "--repository-root", str(self.repo), "--expected-commit", "0" * 40],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["code"], "WRONG_CHECKOUT")


class PluginInvocationPolicyTests(unittest.TestCase):
    """Ensure implicit resolver visibility never relaxes execution controls."""

    def test_both_bridge_skills_allow_implicit_selection(self) -> None:
        for name in ("cloudrepo-skill-discovery", "cloudrepo-skill-invoke"):
            with self.subTest(skill=name):
                metadata = (BRIDGE_ROOT / "skills" / name / "agents/openai.yaml").read_text("utf-8")
                self.assertEqual(metadata.count("allow_implicit_invocation: true"), 1)
                self.assertNotIn("allow_implicit_invocation: false", metadata)

    def test_plugin_default_prompt_is_preserved_across_source_extensions(self) -> None:
        portable = json.loads((BRIDGE_ROOT / "plugin.json").read_text("utf-8"))
        codex = json.loads((BRIDGE_ROOT / ".codex-plugin/plugin.json").read_text("utf-8"))
        main_prompt = portable["extensions"]["com.openai"]["interface"]["defaultPrompt"]
        self.assertEqual(main_prompt, codex["interface"]["defaultPrompt"])
        self.assertIn("$cloudrepo-skill-discovery", main_prompt)
        self.assertIn("$cloudrepo-skill-invoke", main_prompt)

    def test_implicit_resolver_preserves_execution_authorization(self) -> None:
        invocation = (BRIDGE_ROOT / "skills/cloudrepo-skill-invoke/SKILL.md").read_text("utf-8")
        contract = (
            BRIDGE_ROOT / "skills/cloudrepo-skill-invoke/references/invocation-contract.md"
        ).read_text("utf-8")
        self.assertIn("Root and Child may select", invocation)
        self.assertIn("An explicit request from the end user", contract)
        self.assertIn("Resolving skill instructions is **not** authorization to execute them", contract)
        self.assertIn("401/403", invocation)


if __name__ == "__main__":
    unittest.main()
