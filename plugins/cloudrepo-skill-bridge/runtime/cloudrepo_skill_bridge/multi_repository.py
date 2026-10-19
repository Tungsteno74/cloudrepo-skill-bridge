"""Bounded multi-repository discovery over immutable Git object snapshots.

A source is explicitly scoped to a repository, full revision and skill root.
Providers only read committed Git objects and never run instructions.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .bridge import (
    _MAX_REFERENCES,
    _MAX_SKILLS,
    _MAX_TREE_ENTRIES,
    _REFERENCE_MAX_BYTES,
    _RESOURCE_TOTAL_MAX_BYTES,
    _SKILL_MAX_BYTES,
    _implicit_policy,
    _parse_frontmatter,
)
from .errors import BridgeError
from .models import SkillDescriptor, TextResource
from .repository import inspect_repository

_REPO_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SKILL_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SHA = re.compile(r"[a-fA-F0-9]{40}(?:[a-fA-F0-9]{24})?\Z")
_SOURCE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_PLUGIN_SKILLS = re.compile(r"plugins/[a-z0-9]+(?:-[a-z0-9]+)*/skills\Z")
_MAX_SOURCES = 8
_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_CATALOG_BYTES = 64 * 1024


def _safe_root(value: str) -> bool:
    return value in (".agents/skills", "skills") or bool(_PLUGIN_SKILLS.fullmatch(value))


def _git_blob_id(raw: bytes, object_id: str) -> str:
    """Compute the Git object ID with the repository's observed digest width."""
    content = b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    if len(object_id) == 40:
        return hashlib.sha1(content).hexdigest()
    if len(object_id) == 64:
        return hashlib.sha256(content).hexdigest()
    raise BridgeError("GIT_OBJECT_INVALID", "Invalid immutable Git object identifier")


@dataclass(frozen=True)
class SourceSpec:
    """One explicitly approved immutable skill source; never auto-enumerated."""

    source_id: str
    repository: str
    commit: str
    skill_root: str
    provider: str
    checkout_root: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not _SOURCE_ID.fullmatch(self.source_id):
            raise BridgeError("SOURCE_INVALID", "Invalid source identifier")
        if not isinstance(self.repository, str) or not _REPO_NAME.fullmatch(self.repository):
            raise BridgeError("SOURCE_INVALID", "Repository must be owner/repository")
        if not isinstance(self.commit, str) or not _SHA.fullmatch(self.commit):
            raise BridgeError("SOURCE_INVALID", "Source commit must be a full Git object ID")
        if not isinstance(self.skill_root, str) or not _safe_root(self.skill_root):
            raise BridgeError("SOURCE_INVALID", "Unsupported skill root outside trusted layouts")
        if not isinstance(self.provider, str) or self.provider not in ("local-git", "github-public", "github-connector"):
            raise BridgeError("SOURCE_INVALID", "Unsupported source provider")
        if self.provider == "local-git":
            if not isinstance(self.checkout_root, str) or not Path(self.checkout_root).is_absolute():
                raise BridgeError("SOURCE_INVALID", "Local source needs an absolute checkout root")
        elif self.checkout_root is not None:
            raise BridgeError("SOURCE_INVALID", "Remote source must not specify a local checkout")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "repository": self.repository,
            "commit": self.commit.lower(),
            "skill_root": self.skill_root,
            "provider": self.provider,
        }


@dataclass(frozen=True)
class GitEntry:
    """A tree entry from a pinned commit, not a working-tree filesystem path."""

    path: str
    object_id: str
    mode: str
    size: Optional[int] = None


class GitSnapshot(Protocol):
    """Adapter contract for reading authorized, immutable Git trees."""

    @property
    def entries(self) -> Mapping[str, GitEntry]:
        ...

    def read_blob(self, entry: GitEntry, limit: int) -> bytes:
        ...


class GitProvider(Protocol):
    def open(self, source: SourceSpec) -> GitSnapshot:
        ...


class JsonFetcher(Protocol):
    """Provider API shape; the host can inject an already authorized reader."""

    def get_json(self, path: str) -> Mapping[str, Any]:
        ...


class RejectGitHubRedirect(HTTPRedirectHandler):
    """Reject any redirect before urllib attempts the destination request."""

    def redirect_request(self, request, response, code, reason, headers, new_url):
        raise BridgeError(
            "SOURCE_REDIRECT_BLOCKED",
            "GitHub API redirects are not allowed for pinned source reads",
        )


_GITHUB_OPENER = build_opener(RejectGitHubRedirect())


class GitHubPublicFetcher:
    """Unauthenticated GitHub GET adapter. No tokens, redirects to other hosts or writes."""

    def get_json(self, path: str) -> Mapping[str, Any]:
        if not path.startswith("repos/") or ".." in path or "\\" in path:
            raise BridgeError("SOURCE_INVALID", "Invalid GitHub REST resource")
        url = "https://api.github.com/" + path
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "CloudRepo-SkillBridge/0.2",
            },
        )
        try:
            with _GITHUB_OPENER.open(request, timeout=15) as response:
                # A successful response should never change origin.
                if response.geturl().split("/", 3)[:3] != ["https:", "", "api.github.com"]:
                    raise BridgeError("SOURCE_READ_FAILED", "GitHub source redirect was rejected")
                raw = response.read(_MAX_JSON_BYTES + 1)
        except HTTPError as exc:
            if exc.code in (403, 429) and exc.headers.get("X-RateLimit-Remaining") == "0":
                raise BridgeError("RATE_LIMITED", "GitHub read quota was exceeded") from exc
            if exc.code in (401, 403):
                raise BridgeError("SOURCE_ACCESS_DENIED", "GitHub access was denied") from exc
            if exc.code == 429:
                raise BridgeError("RATE_LIMITED", "GitHub read quota was exceeded") from exc
            if exc.code == 404:
                raise BridgeError("SOURCE_NOT_FOUND", "Requested GitHub source is unavailable") from exc
            raise BridgeError("SOURCE_READ_FAILED", "GitHub source read failed") from exc
        except (TimeoutError, URLError) as exc:
            raise BridgeError("SOURCE_READ_FAILED", "GitHub source is unreachable") from exc
        if len(raw) > _MAX_JSON_BYTES:
            raise BridgeError("SOURCE_TOO_LARGE", "GitHub response exceeded the bounded limit")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise BridgeError("SOURCE_INVALID", "GitHub returned an invalid JSON response") from exc
        if not isinstance(value, dict):
            raise BridgeError("SOURCE_INVALID", "Unexpected GitHub response shape")
        return value


@dataclass
class _GitHubSnapshot:
    source: SourceSpec
    reader: JsonFetcher
    entries: Mapping[str, GitEntry]

    def read_blob(self, entry: GitEntry, limit: int) -> bytes:
        if entry.size is not None and entry.size > limit:
            raise BridgeError("RESOURCE_TOO_LARGE", "Skill resource exceeds its size limit")
        owner, name = self.source.repository.split("/")
        route = "repos/{}/{}/git/blobs/{}".format(owner, name, entry.object_id)
        data = self.reader.get_json(route)
        if not isinstance(data, Mapping):
            raise BridgeError("SOURCE_INVALID", "GitHub blob response is not a JSON object")
        if data.get("sha") != entry.object_id or data.get("encoding") != "base64":
            raise BridgeError("GIT_OBJECT_MISMATCH", "Unexpected GitHub blob response")
        encoded = data.get("content")
        if not isinstance(encoded, str) or len(encoded) > (limit * 4 // 3 + 4096):
            raise BridgeError("RESOURCE_TOO_LARGE", "GitHub blob payload exceeded its limit")
        try:
            raw = base64.b64decode(encoded, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise BridgeError("RESOURCE_INVALID", "GitHub blob has invalid base64 content") from exc
        if len(raw) > limit or (entry.size is not None and len(raw) != entry.size):
            raise BridgeError("RESOURCE_TOO_LARGE", "Unexpected GitHub blob size")
        if _git_blob_id(raw, entry.object_id) != entry.object_id:
            raise BridgeError("GIT_OBJECT_MISMATCH", "GitHub blob integrity verification failed")
        return raw


class GitHubProvider:
    """Immutable GitHub source; private repos require an authorized injected reader."""

    def __init__(self, reader: Optional[JsonFetcher] = None, *, allow_private: bool = False) -> None:
        if allow_private and reader is None:
            raise BridgeError("SOURCE_PROVIDER_UNAVAILABLE", "Private source requires an authorized reader")
        self._reader = reader if reader is not None else GitHubPublicFetcher()
        self._allow_private = allow_private

    def open(self, source: SourceSpec) -> GitSnapshot:
        if source.provider not in ("github-public", "github-connector"):
            raise BridgeError("SOURCE_INVALID", "Provider type mismatch")
        if source.provider == "github-connector" and not self._allow_private:
            raise BridgeError("SOURCE_PROVIDER_UNAVAILABLE", "No authorized connector reader was supplied")
        owner, name = source.repository.split("/")
        prefix = "repos/{}/{}".format(owner, name)
        metadata = self._reader.get_json(prefix)
        if not isinstance(metadata, Mapping):
            raise BridgeError("SOURCE_INVALID", "GitHub repository response is invalid")
        if str(metadata.get("full_name", "")).lower() != source.repository.lower():
            raise BridgeError("WRONG_REPOSITORY", "GitHub repository identity differs")
        private = metadata.get("private")
        if not isinstance(private, bool):
            raise BridgeError("SOURCE_INVALID", "GitHub visibility is not verified")
        if private and (not self._allow_private or source.provider != "github-connector"):
            raise BridgeError("SOURCE_ACCESS_DENIED", "Private GitHub source needs an authorized connector")
        commit = self._reader.get_json(prefix + "/git/commits/" + source.commit.lower())
        if not isinstance(commit, Mapping):
            raise BridgeError("SOURCE_INVALID", "GitHub commit response is invalid")
        if str(commit.get("sha", "")).lower() != source.commit.lower():
            raise BridgeError("WRONG_CHECKOUT", "GitHub source revision differs")
        tree_ref = commit.get("tree")
        tree_sha = tree_ref.get("sha") if isinstance(tree_ref, Mapping) else None
        if not isinstance(tree_sha, str) or not _SHA.fullmatch(tree_sha):
            raise BridgeError("SOURCE_INVALID", "GitHub commit lacks a valid tree")
        response = self._reader.get_json(prefix + "/git/trees/" + tree_sha + "?recursive=1")
        if not isinstance(response, Mapping) or response.get("sha") != tree_sha:
            raise BridgeError("GIT_OBJECT_MISMATCH", "GitHub tree did not match pinned commit")
        if response.get("truncated") is not False:
            raise BridgeError("SOURCE_TREE_INCOMPLETE", "GitHub Git tree is truncated or incomplete")
        tree = response.get("tree")
        if not isinstance(tree, list):
            raise BridgeError("SOURCE_INVALID", "GitHub tree response is malformed")
        entries: Dict[str, GitEntry] = {}
        prefix_path = source.skill_root + "/"
        for item in tree:
            if not isinstance(item, dict):
                raise BridgeError("SOURCE_INVALID", "Invalid GitHub tree entry")
            path = item.get("path")
            if not isinstance(path, str) or not path.startswith(prefix_path):
                continue
            if item.get("type") == "tree":
                continue
            if item.get("type") != "blob":
                raise BridgeError("SOURCE_INVALID", "Unsupported GitHub source object")
            if not _SHA.fullmatch(str(item.get("sha", ""))):
                raise BridgeError("SOURCE_INVALID", "GitHub file object ID is invalid")
            size = item.get("size")
            if size is not None and (not isinstance(size, int) or size < 0):
                raise BridgeError("SOURCE_INVALID", "Invalid GitHub source file size")
            if path in entries:
                raise BridgeError("SOURCE_INVALID", "Duplicate GitHub tree paths")
            entries[path] = GitEntry(path, str(item["sha"]), str(item.get("mode", "")), size)
            if len(entries) > _MAX_TREE_ENTRIES * _MAX_SKILLS:
                raise BridgeError("SOURCE_TOO_LARGE", "Too many GitHub skill tree entries")
        return _GitHubSnapshot(source, self._reader, entries)


@dataclass
class _LocalSnapshot:
    source: SourceSpec
    root: Path
    entries: Mapping[str, GitEntry]

    def read_blob(self, entry: GitEntry, limit: int) -> bytes:
        if entry.size is not None and entry.size > limit:
            raise BridgeError("RESOURCE_TOO_LARGE", "Git object is too large")
        try:
            size_check = subprocess.run(
                ["git", "-C", str(self.root), "cat-file", "-s", entry.object_id],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, timeout=10, check=False,
            )
            if size_check.returncode != 0 or not size_check.stdout.strip().isdigit():
                raise BridgeError("GIT_READ_FAILED", "Unable to inspect pinned Git object size")
            if int(size_check.stdout.strip()) > limit:
                raise BridgeError("RESOURCE_TOO_LARGE", "Pinned Git object exceeds size limit")
            result = subprocess.run(
                ["git", "-C", str(self.root), "cat-file", "blob", entry.object_id],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BridgeError("GIT_READ_FAILED", "Unable to read pinned Git blob") from exc
        raw = result.stdout
        if result.returncode != 0 or len(raw) > limit or _git_blob_id(raw, entry.object_id) != entry.object_id:
            raise BridgeError("GIT_OBJECT_MISMATCH", "Pinned local blob was not verified")
        return raw


class LocalGitProvider:
    """Read only committed Git objects from an explicitly approved checkout."""

    def open(self, source: SourceSpec) -> GitSnapshot:
        if source.provider != "local-git" or source.checkout_root is None:
            raise BridgeError("SOURCE_INVALID", "Provider type mismatch")
        root = Path(source.checkout_root)
        observed = inspect_repository(root, expected_commit=source.commit, expected_repository=source.repository)
        if observed.repository_id is None or not observed.repository_id.lower().startswith("github.com/"):
            raise BridgeError("WRONG_REPOSITORY", "Local source is not from the expected GitHub host")
        if not observed.clean:
            raise BridgeError("DIRTY_REPOSITORY", "External source checkout is not clean")
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "ls-tree", "-r", "-z", source.commit, "--", source.skill_root],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BridgeError("GIT_READ_FAILED", "Unable to inspect pinned Git tree") from exc
        if result.returncode != 0 or len(result.stdout) > _MAX_JSON_BYTES:
            raise BridgeError("SOURCE_READ_FAILED", "Pinned local tree could not be read")
        entries: Dict[str, GitEntry] = {}
        for record in result.stdout.split(b"\0"):
            if not record:
                continue
            try:
                header, path = record.decode("utf-8").split("\t", 1)
                mode, kind, oid = header.split(" ")
            except (ValueError, UnicodeDecodeError) as exc:
                raise BridgeError("SOURCE_INVALID", "Invalid local Git tree record") from exc
            if not path.startswith(source.skill_root + "/") or kind != "blob" or not _SHA.fullmatch(oid):
                raise BridgeError("SOURCE_INVALID", "Unexpected Git tree entry")
            if path in entries:
                raise BridgeError("SOURCE_INVALID", "Duplicate Git tree entry")
            entries[path] = GitEntry(path, oid, mode)
            if len(entries) > _MAX_TREE_ENTRIES * _MAX_SKILLS:
                raise BridgeError("SOURCE_TOO_LARGE", "External Git tree contains too many files")
        return _LocalSnapshot(source, Path(observed.root), entries)


class MultiCloudRepoSkillBridge:
    """Discover/resolve authorized skill sources without mixing provenance."""

    def __init__(
        self,
        sources: Sequence[SourceSpec],
        *,
        providers: Optional[Mapping[str, GitProvider]] = None,
    ) -> None:
        if not sources or len(sources) > _MAX_SOURCES:
            raise BridgeError("SOURCE_CATALOG_INVALID", "Source catalog must contain 1-8 entries")
        names = [source.source_id for source in sources]
        if len(names) != len(set(names)):
            raise BridgeError("DUPLICATE_SOURCE", "Source identifiers must be unique")
        self._sources = tuple(sources)
        self._providers = providers if providers is not None else {
            "local-git": LocalGitProvider(),
            "github-public": GitHubProvider(),
        }
        self._opened: Dict[str, GitSnapshot] = {}

    def _open(self, source: SourceSpec) -> GitSnapshot:
        if source.source_id not in self._opened:
            provider = self._providers.get(source.provider)
            if provider is None:
                raise BridgeError("SOURCE_PROVIDER_UNAVAILABLE", "Authorized source provider is unavailable")
            self._opened[source.source_id] = provider.open(source)
        return self._opened[source.source_id]

    @staticmethod
    def _read_text(snapshot: GitSnapshot, entry: GitEntry, limit: int) -> Tuple[str, str, int]:
        if entry.mode == "120000":
            raise BridgeError("UNSAFE_SYMLINK", "Skill resource is a Git symlink")
        if entry.mode not in ("100644", "100755"):
            raise BridgeError("UNSAFE_FILE_MODE", "Skill resource is not a regular Git blob")
        raw = snapshot.read_blob(entry, limit)
        if len(raw) > limit:
            raise BridgeError("RESOURCE_TOO_LARGE", "Skill resource exceeds its limit")
        try:
            data = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BridgeError("RESOURCE_NOT_UTF8", "Skill resource is not UTF-8") from exc
        return data, hashlib.sha256(raw).hexdigest(), len(raw)

    def _discover_source(self, source: SourceSpec) -> List[SkillDescriptor]:
        snapshot = self._open(source)
        prefix = source.skill_root + "/"
        names = set()
        entries_per_skill: Dict[str, int] = {}
        for path, entry in snapshot.entries.items():
            if not path.startswith(prefix):
                continue
            parts = path[len(prefix):].split("/")
            if len(parts) < 2 or not _SKILL_NAME.fullmatch(parts[0]):
                raise BridgeError("SKILL_ENTRY_INVALID", "Invalid external skill tree entry")
            skill = parts[0]
            names.add(skill)
            entries_per_skill[skill] = entries_per_skill.get(skill, 0) + 1
            if entry.mode == "120000":
                raise BridgeError("UNSAFE_SYMLINK", "External skill tree contains a Git symlink")
            if entry.mode not in ("100644", "100755"):
                raise BridgeError("UNSAFE_FILE_MODE", "External skill tree contains a non-regular object")
            if entries_per_skill[skill] > _MAX_TREE_ENTRIES:
                raise BridgeError("SKILL_TREE_TOO_LARGE", "External skill tree exceeds entry count limit")
            if len(names) > _MAX_SKILLS:
                raise BridgeError("TOO_MANY_SKILLS", "Too many external skills")
        descriptors = []
        for name in sorted(names):
            root = prefix + name + "/"
            manifest = snapshot.entries.get(root + "SKILL.md")
            if manifest is None:
                raise BridgeError("MANIFEST_INVALID", "External skill is missing SKILL.md")
            source_text, digest, _ = self._read_text(snapshot, manifest, _SKILL_MAX_BYTES)
            description = _parse_frontmatter(source_text, name)
            metadata = snapshot.entries.get(root + "agents/openai.yaml")
            implicit = None
            if metadata is not None:
                meta_text, _, _ = self._read_text(snapshot, metadata, _REFERENCE_MAX_BYTES)
                implicit = _implicit_policy(meta_text)
            descriptors.append(
                SkillDescriptor(
                    name=name,
                    description=description,
                    relative_path=root + "SKILL.md",
                    skill_sha256=digest,
                    metadata_present=metadata is not None,
                    implicit_invocation_allowed=implicit,
                )
            )
        return descriptors

    def _descriptor_for_name(
        self, source: SourceSpec, name: str,
    ) -> Optional[SkillDescriptor]:
        """Validate only the requested skill, isolating malformed siblings."""
        snapshot = self._open(source)
        root = source.skill_root + "/" + name + "/"
        entries = [
            entry for path, entry in snapshot.entries.items() if path.startswith(root)
        ]
        if not entries:
            return None
        if len(entries) > _MAX_TREE_ENTRIES:
            raise BridgeError("SKILL_TREE_TOO_LARGE", "Target skill exceeds entry count limit")
        for entry in entries:
            if entry.mode == "120000":
                raise BridgeError("UNSAFE_SYMLINK", "Target skill contains a Git symlink")
            if entry.mode not in ("100644", "100755"):
                raise BridgeError("UNSAFE_FILE_MODE", "Target skill contains a non-regular object")
        manifest = snapshot.entries.get(root + "SKILL.md")
        if manifest is None:
            raise BridgeError("MANIFEST_INVALID", "Target skill is missing SKILL.md")
        source_text, digest, _ = self._read_text(snapshot, manifest, _SKILL_MAX_BYTES)
        description = _parse_frontmatter(source_text, name)
        metadata = snapshot.entries.get(root + "agents/openai.yaml")
        implicit = None
        if metadata is not None:
            metadata_text, _, _ = self._read_text(
                snapshot, metadata, _REFERENCE_MAX_BYTES,
            )
            implicit = _implicit_policy(metadata_text)
        return SkillDescriptor(
            name=name,
            description=description,
            relative_path=root + "SKILL.md",
            skill_sha256=digest,
            metadata_present=metadata is not None,
            implicit_invocation_allowed=implicit,
        )

    def discover(self) -> Dict[str, Any]:
        """List immutable sources and descriptors, preserving source attribution."""
        return {
            "status": "ok",
            "provenance": "pinned_git_repository_sources",
            "native_registration": "not_tested_by_bridge",
            "execution_performed": False,
            "sources": [
                {**source.as_dict(), "skills": [item.as_dict() for item in self._discover_source(source)]}
                for source in self._sources
            ],
        }

    @staticmethod
    def _safe_reference(path: str) -> str:
        if not isinstance(path, str) or not path or "\\" in path or path.startswith("/"):
            raise BridgeError("UNSAFE_REFERENCE", "Reference path must be relative and safe")
        parts = path.split("/")
        if any(x in ("", ".", "..") for x in parts) or parts[0] not in ("references", "assets", "agents"):
            raise BridgeError("UNSAFE_REFERENCE", "Reference must remain inside the skill root")
        return "/".join(parts)

    def resolve(
        self,
        name: str,
        *,
        source_id: Optional[str] = None,
        references: Sequence[str] = (),
    ) -> Dict[str, Any]:
        """Read pinned source documents only; never register or execute a skill."""
        if not _SKILL_NAME.fullmatch(name):
            raise BridgeError("INVALID_SKILL_NAME", "Invalid skill name")
        if len(references) > _MAX_REFERENCES:
            raise BridgeError("TOO_MANY_REFERENCES", "Too many requested skill references")
        chosen = tuple(s for s in self._sources if source_id is None or s.source_id == source_id)
        if not chosen:
            raise BridgeError("SOURCE_NOT_FOUND", "Specified source is not in the authorized catalog")
        matches = []
        for source in chosen:
            descriptor = self._descriptor_for_name(source, name)
            if descriptor is not None:
                matches.append((source, descriptor))
        if not matches:
            raise BridgeError("SKILL_NOT_FOUND", "No matching skill in authorized sources")
        if len(matches) > 1:
            raise BridgeError("AMBIGUOUS_SKILL", "Skill exists in multiple sources; select source_id")
        source, descriptor = matches[0]
        snapshot = self._open(source)
        entry = snapshot.entries.get(descriptor.relative_path)
        if entry is None:
            raise BridgeError("SOURCE_CHANGED", "Skill disappeared from immutable source snapshot")
        text, digest, total = self._read_text(snapshot, entry, _SKILL_MAX_BYTES)
        if digest != descriptor.skill_sha256:
            raise BridgeError("SOURCE_CHANGED", "Skill content changed across reads")
        documents = []
        seen = set()
        prefix = source.skill_root + "/" + name + "/"
        for ref in references:
            path = self._safe_reference(ref)
            if path in seen:
                raise BridgeError("DUPLICATE_REFERENCE", "Duplicate external skill reference")
            seen.add(path)
            resource_path = prefix + path
            resource = snapshot.entries.get(resource_path)
            if resource is None:
                raise BridgeError("RESOURCE_NOT_FOUND", "External skill reference is missing")
            data, sha, size = self._read_text(snapshot, resource, _REFERENCE_MAX_BYTES)
            total += size
            if total > _RESOURCE_TOTAL_MAX_BYTES:
                raise BridgeError("RESOURCE_BUDGET_EXCEEDED", "Resolved resources exceed size budget")
            documents.append(TextResource(resource_path, sha, data).as_dict())
        return {
            "status": "ready_for_manual_execution",
            "source": source.as_dict(),
            "skill": descriptor.as_dict(),
            "instructions": TextResource(descriptor.relative_path, digest, text).as_dict(),
            "references": documents,
            "provenance": "pinned_git_repository_source",
            "activation": "manual_remote_repository_fallback",
            "native_registration": "not_tested_by_bridge",
            "execution_performed": False,
            "authorization_granted": False,
        }


def load_sources(path: Path) -> List[SourceSpec]:
    """Load caller-supplied, bounded source declarations. Not an auth grant."""
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise BridgeError("SOURCE_CATALOG_INVALID", "Source catalog must be a regular absolute file")
    if path.stat().st_size > _MAX_CATALOG_BYTES:
        raise BridgeError("SOURCE_CATALOG_INVALID", "Source catalog exceeds allowed size")
    try:
        raw = json.loads(path.read_text("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise BridgeError("SOURCE_CATALOG_INVALID", "Source catalog is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {"sources"} or not isinstance(raw["sources"], list):
        raise BridgeError("SOURCE_CATALOG_INVALID", "Source catalog requires a sources array")
    sources = []
    for entry in raw["sources"]:
        if not isinstance(entry, dict):
            raise BridgeError("SOURCE_CATALOG_INVALID", "Invalid source record")
        allowed = {"source_id", "repository", "commit", "skill_root", "provider", "checkout_root"}
        required = {"source_id", "repository", "commit", "skill_root", "provider"}
        if set(entry) - allowed or not required.issubset(entry):
            raise BridgeError("SOURCE_CATALOG_INVALID", "Source record has invalid or missing fields")
        try:
            sources.append(SourceSpec(**entry))
        except TypeError as exc:
            raise BridgeError("SOURCE_CATALOG_INVALID", "Source record fields are invalid") from exc
    return sources
