"""Immutable outputs produced by the repository skill bridge."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RepositoryInfo:
    root: str
    head: str
    clean: bool
    remote_identity: Optional[str]
    repository_id: Optional[str]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SkillDescriptor:
    name: str
    description: str
    relative_path: str
    skill_sha256: str
    metadata_present: bool
    implicit_invocation_allowed: Optional[bool]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TextResource:
    relative_path: str
    sha256: str
    content: str

    def as_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class SkillResolution:
    repository: RepositoryInfo
    skill: SkillDescriptor
    instructions: TextResource
    references: List[TextResource]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": "ready_for_manual_execution",
            "provenance": "repository_filesystem",
            "activation": "manual_repository_fallback",
            "native_registration": "not_tested_by_bridge",
            "execution_performed": False,
            "authorization_granted": False,
            "repository": self.repository.as_dict(),
            "skill": self.skill.as_dict(),
            "instructions": self.instructions.as_dict(),
            "references": [reference.as_dict() for reference in self.references],
        }
