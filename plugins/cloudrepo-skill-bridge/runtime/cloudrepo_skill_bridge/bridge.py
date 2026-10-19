"""Bounded, read-only repository skill discovery and materialization."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .errors import BridgeError
from .models import RepositoryInfo, SkillDescriptor, SkillResolution, TextResource
from .repository import inspect_repository
from .yaml_support import load_mapping

_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SKILL_MAX_BYTES = 256 * 1024
_REFERENCE_MAX_BYTES = 256 * 1024
_RESOURCE_TOTAL_MAX_BYTES = 1024 * 1024
_MAX_SKILLS = 100
_MAX_REFERENCES = 10
_MAX_TREE_ENTRIES = 500


def _validate_tree(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise BridgeError("UNSAFE_SKILL_PATH", "Skill directory is missing or a symlink")
    count = 0
    for base, folders, files in os.walk(directory, followlinks=False):
        count += len(folders) + len(files)
        if count > _MAX_TREE_ENTRIES:
            raise BridgeError("SKILL_TREE_TOO_LARGE", "Skill tree contains too many entries")
        for name in folders + files:
            if (Path(base) / name).is_symlink():
                raise BridgeError("UNSAFE_SYMLINK", "Symlink found in a skill tree")


def _read_text(path: Path, limit: int) -> Tuple[str, str, int]:
    if path.is_symlink() or not path.is_file():
        raise BridgeError("RESOURCE_NOT_FOUND", "Required skill resource is absent or unsafe")
    size = path.stat().st_size
    if size > limit:
        raise BridgeError("RESOURCE_TOO_LARGE", "Skill resource exceeds its size limit")
    raw = path.read_bytes()
    if len(raw) > limit:
        raise BridgeError("RESOURCE_TOO_LARGE", "Skill resource exceeds its size limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BridgeError("RESOURCE_NOT_UTF8", "Skill resource is not UTF-8") from exc
    return text, hashlib.sha256(raw).hexdigest(), len(raw)


def _parse_frontmatter(skill_text: str, expected_name: str) -> str:
    """Validate YAML frontmatter with real scalar types and indentation rules."""
    lines = skill_text.splitlines()
    if len(lines) < 4 or lines[0] != "---":
        raise BridgeError("MANIFEST_INVALID", "SKILL.md must begin with YAML frontmatter")
    try:
        closing = lines[1:180].index("---") + 1
    except ValueError as exc:
        raise BridgeError("MANIFEST_INVALID", "SKILL.md frontmatter is not closed") from exc

    values = load_mapping("\n".join(lines[1:closing]), "MANIFEST_INVALID")
    if values.get("name") != expected_name or not isinstance(values.get("name"), str):
        raise BridgeError("MANIFEST_INVALID", "SKILL.md name differs from skill directory")
    description = values.get("description")
    if not isinstance(description, str) or not description.strip():
        raise BridgeError("MANIFEST_INVALID", "SKILL.md description must be nonempty text")
    return description.strip()[:512]


def _implicit_policy(metadata: str) -> Optional[bool]:
    """Read a boolean policy as YAML; absence differs from explicit False."""
    values = load_mapping(metadata, "METADATA_INVALID")
    if "policy" not in values:
        return None
    policy = values["policy"]
    if not isinstance(policy, dict):
        raise BridgeError("METADATA_INVALID", "Policy must be a YAML mapping")
    if set(policy) - {"products", "allow_implicit_invocation"}:
        raise BridgeError("METADATA_INVALID", "Unknown policy fields")
    products = policy.get("products")
    if products is not None and (
        not isinstance(products, list)
        or any(not isinstance(value, str) or value not in {"CHAT", "CODEX", "HERMES"}
               for value in products)
    ):
        raise BridgeError("METADATA_INVALID", "Invalid policy product list")
    setting = policy.get("allow_implicit_invocation")
    if setting is not None and type(setting) is not bool:
        raise BridgeError("METADATA_INVALID", "Implicit invocation must be a YAML boolean")
    return setting


class CloudRepoSkillBridge:
    """Resolve explicitly associated Git checkout skills without executing them."""

    def __init__(
        self,
        repository_root: Path,
        *,
        expected_commit: Optional[str] = None,
        expected_repository: Optional[str] = None,
    ) -> None:
        self.repository: RepositoryInfo = inspect_repository(
            repository_root,
            expected_commit=expected_commit,
            expected_repository=expected_repository,
        )
        self._root = Path(self.repository.root)
        self._skills = self._root / ".agents" / "skills"

    def discover(self) -> List[SkillDescriptor]:
        """Discover bounded skill descriptors; never invoke code or mutate Git."""
        parents = (self._root / ".agents", self._skills)
        if any(p.is_symlink() for p in parents):
            raise BridgeError("UNSAFE_SYMLINK", "Repository skill root contains a symlink")
        if not self._skills.is_dir():
            return []
        directories = sorted(self._skills.iterdir(), key=lambda path: path.name)
        if len(directories) > _MAX_SKILLS:
            raise BridgeError("TOO_MANY_SKILLS", "Too many repository skill entries")
        descriptors = []
        for directory in directories:
            if directory.is_symlink():
                raise BridgeError("UNSAFE_SYMLINK", "Repository skill entry is a symlink")
            if not directory.is_dir() or not _NAME.fullmatch(directory.name):
                raise BridgeError("SKILL_ENTRY_INVALID", "Unexpected repository skill entry")
            _validate_tree(directory)
            source, digest, _ = _read_text(directory / "SKILL.md", _SKILL_MAX_BYTES)
            description = _parse_frontmatter(source, directory.name)
            metadata = directory / "agents" / "openai.yaml"
            implicit = None
            if metadata.exists():
                metadata_text, _, _ = _read_text(metadata, _REFERENCE_MAX_BYTES)
                implicit = _implicit_policy(metadata_text)
            descriptors.append(
                SkillDescriptor(
                    name=directory.name,
                    description=description,
                    relative_path=f".agents/skills/{directory.name}/SKILL.md",
                    skill_sha256=digest,
                    metadata_present=metadata.exists(),
                    implicit_invocation_allowed=implicit,
                )
            )
        return descriptors

    def resolve(
        self,
        name: str,
        *,
        references: Sequence[str] = (),
        allow_dirty: bool = False,
    ) -> SkillResolution:
        """Read explicitly requested instructions for an agent; do not execute them."""
        if not _NAME.fullmatch(name):
            raise BridgeError("INVALID_SKILL_NAME", "Skill name must be canonical")
        if not self.repository.clean and not allow_dirty:
            raise BridgeError(
                "DIRTY_REPOSITORY",
                "Refusing to resolve potentially uncommitted skill instructions",
            )
        if len(references) > _MAX_REFERENCES:
            raise BridgeError("TOO_MANY_REFERENCES", "Requested too many reference files")
        catalog = {descriptor.name: descriptor for descriptor in self.discover()}
        descriptor = catalog.get(name)
        if descriptor is None:
            raise BridgeError("SKILL_NOT_FOUND", "Skill not found in the associated repository")
        directory = self._skills / name
        _validate_tree(directory)
        source, digest, total = _read_text(directory / "SKILL.md", _SKILL_MAX_BYTES)
        if digest != descriptor.skill_sha256:
            raise BridgeError("SKILL_CHANGED", "Skill source changed during resolution")
        content = TextResource(descriptor.relative_path, digest, source)
        resolved_references = []
        seen = set()
        for reference in references:
            path = Path(reference)
            raw_parts = reference.split("/")
            if (
                not reference
                or "\\" in reference
                or path.is_absolute()
                or any(part in (".", "..", "") for part in raw_parts)
                or raw_parts[0] not in ("references", "assets", "agents")
            ):
                raise BridgeError("UNSAFE_REFERENCE", "Reference must remain within the skill root")
            normalized = path.as_posix()
            if normalized in seen:
                raise BridgeError("DUPLICATE_REFERENCE", "Duplicate skill reference")
            seen.add(normalized)
            target = directory / path
            try:
                target.resolve(strict=True).relative_to(directory.resolve(strict=True))
            except (FileNotFoundError, ValueError) as exc:
                raise BridgeError("UNSAFE_REFERENCE", "Reference escapes its skill directory") from exc
            text, sha, size = _read_text(target, _REFERENCE_MAX_BYTES)
            total += size
            if total > _RESOURCE_TOTAL_MAX_BYTES:
                raise BridgeError("RESOURCE_BUDGET_EXCEEDED", "Requested resources exceed size budget")
            resolved_references.append(
                TextResource(f".agents/skills/{name}/{normalized}", sha, text)
            )
        latest = inspect_repository(self._root)
        if latest.head != self.repository.head or (self.repository.clean and not latest.clean):
            raise BridgeError("REPOSITORY_CHANGED", "Repository changed during resolution")
        return SkillResolution(self.repository, descriptor, content, resolved_references)
