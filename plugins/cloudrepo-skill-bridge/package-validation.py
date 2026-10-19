"""Validate the CloudRepo Skill Bridge package and its stable identity."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "runtime"))

from cloudrepo_skill_bridge.bridge import _parse_frontmatter, _implicit_policy
from cloudrepo_skill_bridge.errors import BridgeError
from cloudrepo_skill_bridge.yaml_support import load_mapping


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    portable = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    legacy = json.loads(
        (root / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
    )
    apps = json.loads((root / ".app.json").read_text(encoding="utf-8"))

    name = "cloudrepo-skill-bridge"
    require(
        portable["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "Invalid plugin schema",
    )
    require(portable["name"] == legacy["name"] == name, "Plugin identity mismatch")
    require(portable["version"] == legacy["version"], "Plugin version mismatch")
    require(
        portable["extensions"]["com.openai"]["interface"] == legacy["interface"],
        "Portable and Codex interface metadata differ",
    )
    require(legacy["skills"] == "./skills", "Invalid legacy skill root")
    require(
        portable["extensions"]["com.openai"]["apps"] == legacy["apps"] == "./.app.json",
        "GitHub app declaration differs",
    )
    require(apps["apps"]["github"]["required"] is False, "App must remain optional")
    require(
        re.fullmatch(r"0[.]2[.]0", portable["version"]) is not None,
        "Unexpected release version format",
    )
    interface = legacy["interface"]
    require(
        interface.get("displayName") == "CloudRepo Skill Bridge",
        "Visible CloudRepo identity is inconsistent",
    )
    require(
        interface.get("shortDescription") == "Resolve multi-repo skills",
        "Unexpected CloudRepo short description",
    )
    require(
        interface.get("logo") == interface.get("composerIcon") == "./assets/icon.png",
        "Plugin icon references are inconsistent",
    )
    icon = (root / "assets/icon.png").read_bytes()
    require(
        len(icon) <= 5 * 1024 * 1024 and
        icon[:8] == bytes.fromhex("89504E470D0A1A0A") and
        icon[12:16] == b"IHDR",
        "Plugin icon is missing or invalid",
    )
    import struct
    width, height = struct.unpack(">II", icon[16:24])
    require(
        width == height and 48 <= width <= 4096,
        "Plugin icon must be a square of supported dimensions",
    )
    require(
        isinstance(interface.get("capabilities"), list)
        and all(isinstance(value, str) and value.strip()
                for value in interface["capabilities"]),
        "Invalid capabilities",
    )
    require(
        isinstance(interface.get("defaultPrompt"), str)
        and interface["defaultPrompt"].strip(),
        "Missing default prompt",
    )

    names = ("cloudrepo-skill-discovery", "cloudrepo-skill-invoke")
    for skill_name in names:
        directory = root / "skills" / skill_name
        manifest = directory / "SKILL.md"
        require(manifest.is_file(), "Missing skill " + skill_name)
        _parse_frontmatter(manifest.read_text(encoding="utf-8"), skill_name)

        metadata = directory / "agents/openai.yaml"
        require(metadata.is_file(), "Missing agent metadata for " + skill_name)
        contents = metadata.read_text(encoding="utf-8")
        parsed = load_mapping(contents, "METADATA_INVALID")
        _implicit_policy(contents)
        visual = parsed.get("interface")
        require(isinstance(visual, dict), "Missing skill interface metadata")
        for key in ("display_name", "short_description"):
            require(
                isinstance(visual.get(key), str) and bool(visual[key].strip()),
                "Invalid skill interface " + key,
            )
        if "default_prompt" in visual:
            require(
                isinstance(visual["default_prompt"], str)
                and bool(visual["default_prompt"].strip()),
                "Invalid skill default_prompt",
            )
        policy = parsed.get("policy", {})
        require(
            isinstance(policy, dict)
            and policy.get("allow_implicit_invocation") is True,
            "Implicit invocation must remain enabled",
        )
        refs = directory / "references"
        require(refs.is_dir(), "Missing skill references for " + skill_name)
        text = manifest.read_text(encoding="utf-8")
        for relative in re.findall(r"\]\(([^)]+)\)", text):
            if "://" in relative or relative.startswith("#"):
                continue
            candidate = (directory / relative.split("#", 1)[0]).resolve()
            try:
                candidate.relative_to(directory.resolve())
            except ValueError as exc:
                raise ValueError("Skill reference escapes its directory") from exc
            require(candidate.is_file(), "Missing skill reference " + relative)

    cli = (root / "runtime/cli.py").read_text(encoding="utf-8")
    require(
        "multi-discover" in cli and "multi-resolve" in cli,
        "Multi-source CLI support missing",
    )
    require("ensure_ascii=True" in cli, "CLI output is not encoding-independent")
    require(
        (root / "runtime/cloudrepo_skill_bridge/multi_repository.py").is_file(),
        "Missing multi-source implementation",
    )
    require(
        (root / "runtime/cloudrepo_skill_bridge/yaml_support.py").is_file(),
        "Missing YAML reader",
    )
    requirements = (root / "runtime/requirements.txt").read_text(encoding="utf-8")
    require("PyYAML" in requirements, "Undeclared YAML dependency")

    for resource in root.rglob("*"):
        require(not resource.is_symlink(), "Symlink in plugin archive")
        if resource.is_file() and resource.suffix in {".md", ".yaml", ".json", ".py", ".txt"}:
            resource.read_text(encoding="utf-8")

    print("PLUGIN_LAYOUT_VALID")


if __name__ == "__main__":
    try:
        main()
    except (BridgeError, ValueError, KeyError, TypeError, OSError) as exc:
        print("PLUGIN_LAYOUT_INVALID: " + str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
