"""Regressions for the confirmed 2026-10-19 Bridge compliance findings."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.request
import urllib.response
from email.message import Message
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from cloudrepo_skill_bridge.bridge import _implicit_policy, _parse_frontmatter
from cloudrepo_skill_bridge.errors import BridgeError
from cloudrepo_skill_bridge import yaml_support
from cloudrepo_skill_bridge.multi_repository import (
    GitHubProvider,
    GitHubPublicFetcher,
    MultiCloudRepoSkillBridge,
    RejectGitHubRedirect,
    SourceSpec,
)

from test_multi_repository import FakeGitHub


class TypedYamlRegressions(unittest.TestCase):
    def test_one_space_folded_description_is_valid(self) -> None:
        text = (
            "---\nname: github-actions-direct\ndescription: >-\n"
            " Plan safe Windows CI for an exact revision.\n"
            " Use existing GitHub permissions.\n---\n"
        )
        self.assertIn(
            "Plan safe Windows CI",
            _parse_frontmatter(text, "github-actions-direct"),
        )

    def test_invalid_description_types_and_yaml_fail_closed(self) -> None:
        for description in ("null", "[one, two]", "[unterminated"):
            with self.subTest(description=description):
                text = (
                    "---\nname: example-skill\ndescription: "
                    + description + "\n---\n"
                )
                with self.assertRaises(BridgeError) as caught:
                    _parse_frontmatter(text, "example-skill")
                self.assertEqual(caught.exception.code, "MANIFEST_INVALID")

    def test_duplicate_keys_are_rejected(self) -> None:
        source = (
            "---\nname: example-skill\nname: example-skill\n"
            "description: Read only\n---\n"
        )
        with self.assertRaises(BridgeError) as caught:
            _parse_frontmatter(source, "example-skill")
        self.assertEqual(caught.exception.code, "MANIFEST_INVALID")

    def test_false_policy_variants_are_preserved(self) -> None:
        variants = (
            "policy:\n  allow_implicit_invocation: false # disabled\n",
            "policy: {allow_implicit_invocation: false}\n",
            "policy:\n    allow_implicit_invocation: false\n",
        )
        for document in variants:
            with self.subTest(document=document):
                self.assertIs(_implicit_policy(document), False)

    def test_invalid_boolean_or_duplicate_policy_is_rejected(self) -> None:
        variants = (
            "policy:\n  allow_implicit_invocation: 'false'\n",
            "policy:\n  allow_implicit_invocation: 0\n",
            "policy:\n  allow_implicit_invocation: true\n"
            "  allow_implicit_invocation: false\n",
            "policy: [allow_implicit_invocation]\n",
            "policy:\n  allow_implicit_invocation: true\nbroken: [unterminated\n",
        )
        for document in variants:
            with self.subTest(document=document):
                with self.assertRaises(BridgeError) as caught:
                    _implicit_policy(document)
                self.assertEqual(caught.exception.code, "METADATA_INVALID")

    def test_missing_yaml_dependency_has_named_error(self) -> None:
        with patch.object(yaml_support, "yaml", None):
            with self.assertRaises(BridgeError) as caught:
                _parse_frontmatter(
                    "---\nname: example-skill\ndescription: valid\n---\n",
                    "example-skill",
                )
        self.assertEqual(caught.exception.code, "YAML_PARSER_UNAVAILABLE")


class GitObjectRegressions(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeGitHub()
        self.source = SourceSpec(
            "approved-source",
            self.fake.repository,
            self.fake.commit,
            "plugins/example-plugin/skills",
            "github-public",
        )

    def _bridge(self) -> MultiCloudRepoSkillBridge:
        return MultiCloudRepoSkillBridge(
            (self.source,),
            providers={"github-public": GitHubProvider(self.fake)},
        )

    def test_executable_regular_support_file_is_not_executed(self) -> None:
        path = (
            "plugins/example-plugin/skills/"
            + self.fake.skill
            + "/references/helper.py"
        )
        self.fake.contents[path] = b"raise RuntimeError('SHOULD_NOT_RUN')\n"
        self.fake.modes[path] = "100755"
        outcome = self._bridge().resolve(
            self.fake.skill, references=["references/helper.py"]
        )
        self.assertEqual(outcome["execution_performed"], False)
        self.assertIn("SHOULD_NOT_RUN", outcome["references"][0]["content"])
        self.assertIn(self.fake.skill, [s["name"] for s in
                                     self._bridge().discover()["sources"][0]["skills"]])

    def test_git_symlink_is_still_rejected(self) -> None:
        path = (
            "plugins/example-plugin/skills/"
            + self.fake.skill
            + "/references/helper.py"
        )
        self.fake.contents[path] = b"../../untrusted\n"
        self.fake.modes[path] = "120000"
        for operation in (lambda: self._bridge().discover(),
                          lambda: self._bridge().resolve(self.fake.skill)):
            with self.assertRaises(BridgeError) as caught:
                operation()
            self.assertEqual(caught.exception.code, "UNSAFE_SYMLINK")

    def test_malformed_sibling_does_not_block_target_resolution(self) -> None:
        sibling = "plugins/example-plugin/skills/broken-sibling/SKILL.md"
        self.fake.contents[sibling] = (
            b"---\nname: broken-sibling\ndescription: null\n---\n"
        )
        target = self._bridge().resolve(self.fake.skill)
        self.assertEqual(target["status"], "ready_for_manual_execution")
        with self.assertRaises(BridgeError) as caught:
            self._bridge().discover()
        self.assertEqual(caught.exception.code, "MANIFEST_INVALID")


class RedirectRegressions(unittest.TestCase):
    def test_cross_origin_redirect_is_not_followed(self) -> None:
        seen = []

        class FakeTransport(urllib.request.BaseHandler):
            handler_order = 100

            def https_open(self, request):
                seen.append(request.full_url)
                headers = Message()
                headers["Location"] = "https://not-approved.invalid/attack"
                response = urllib.response.addinfourl(
                    io.BytesIO(b""), headers, request.full_url, 302
                )
                response.msg = "Found"
                return response

        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            FakeTransport(),
            RejectGitHubRedirect(),
        )
        from cloudrepo_skill_bridge import multi_repository

        with patch.object(multi_repository, "_GITHUB_OPENER", opener):
            with self.assertRaises(BridgeError) as caught:
                GitHubPublicFetcher().get_json(
                    "repos/Tungsteno74/test",
                )
        self.assertEqual(caught.exception.code, "SOURCE_REDIRECT_BLOCKED")
        self.assertEqual(seen, ["https://api.github.com/repos/Tungsteno74/test"])


class ValidationRegressions(unittest.TestCase):
    def test_cloudrepo_branding_preserves_backward_compatibility(self) -> None:
        import struct

        portable = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        legacy = json.loads(
            (ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            portable["name"],
            "cloudrepo-skill-bridge",
        )
        self.assertEqual(portable["name"], legacy["name"])
        self.assertEqual(portable["version"], legacy["version"])
        new_interface = portable["extensions"]["com.openai"]["interface"]
        self.assertEqual(new_interface, legacy["interface"])
        self.assertEqual(new_interface["displayName"], "CloudRepo Skill Bridge")
        self.assertEqual(new_interface["logo"], "./assets/icon.png")
        self.assertEqual(new_interface["composerIcon"], "./assets/icon.png")
        self.assertIn(
            "$cloudrepo-skill-discovery",
            new_interface["defaultPrompt"],
        )
        self.assertIn("$cloudrepo-skill-invoke", new_interface["defaultPrompt"])
        icon = (ROOT / "assets/icon.png").read_bytes()
        self.assertEqual(icon[:8], bytes.fromhex("89504E470D0A1A0A"))
        self.assertEqual(struct.unpack(">II", icon[16:24]), (1254, 1254))
        binding = json.loads((ROOT / ".app.json").read_text(encoding="utf-8"))
        self.assertIs(binding["apps"]["github"]["required"], False)

    def test_validator_rejects_malformed_yaml(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bridge-validator-regression-") as tmp:
            candidate = Path(tmp) / "plugin"
            shutil.copytree(
                ROOT,
                candidate,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            metadata = candidate / "skills/cloudrepo-skill-discovery/agents/openai.yaml"
            with metadata.open("a", encoding="utf-8") as stream:
                stream.write("\nbroken: [unterminated\n")
            result = subprocess.run(
                [sys.executable, "package-validation.py"],
                cwd=candidate,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PLUGIN_LAYOUT_INVALID", result.stderr)

    def test_cli_json_is_ascii_safe_under_cp1252(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bridge-cli-encoding-") as tmp:
            repo = Path(tmp) / "repository"
            directory = repo / ".agents/skills/audit-skill"
            directory.mkdir(parents=True)
            (directory / "SKILL.md").write_text(
                "---\nname: audit-skill\ndescription: Valid\n---\n"
                "Direction: \u2192\n",
                encoding="utf-8",
            )

            def git(*args: str) -> str:
                result = subprocess.run(
                    ["git", "-C", str(repo), *args],
                    capture_output=True,
                    check=True,
                    text=True,
                )
                return result.stdout.strip()

            git("init", "-q")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            git("remote", "add", "origin", "https://github.com/Tungsteno74/audit.git")
            git("add", ".")
            git("commit", "-qm", "fixture")
            revision = git("rev-parse", "HEAD")
            env = dict(os.environ, PYTHONIOENCODING="cp1252")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "runtime/cli.py"),
                    "resolve",
                    "--repository-root",
                    str(repo),
                    "--expected-repository",
                    "Tungsteno74/audit",
                    "--expected-commit",
                    revision,
                    "--name",
                    "audit-skill",
                ],
                env=env,
                capture_output=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout.decode("ascii"))
            self.assertIn("\u2192", payload["instructions"]["content"])


if __name__ == "__main__":
    unittest.main()
