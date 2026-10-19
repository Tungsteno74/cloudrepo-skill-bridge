"""Read-only repository skill discovery and instruction resolution."""

from .bridge import CloudRepoSkillBridge
from .errors import BridgeError
from .models import RepositoryInfo, SkillDescriptor, SkillResolution
from .multi_repository import MultiCloudRepoSkillBridge, SourceSpec

__all__ = (
    "BridgeError",
    "MultiCloudRepoSkillBridge",
    "RepositoryInfo",
    "CloudRepoSkillBridge",
    "SkillDescriptor",
    "SkillResolution",
    "SourceSpec",
)
