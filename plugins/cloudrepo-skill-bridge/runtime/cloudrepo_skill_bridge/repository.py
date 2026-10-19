"""Resolve explicit local Git repository identity without changing Git state."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from .errors import BridgeError
from .models import RepositoryInfo

_COMMIT_PATTERN = re.compile(r"[a-fA-F0-9]{40,64}\Z")
_REPO_PART = re.compile(r"[a-zA-Z0-9_.-]+\Z")


def _git(repository_root: Path, *arguments: str) -> str:
    try:
        process = subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise BridgeError("GIT_UNAVAILABLE", "Git is unavailable or timed out") from exc

    if process.returncode != 0:
        raise BridgeError("GIT_READ_FAILED", "Unable to read Git repository state")
    return process.stdout.strip()


def _remote_identity(remote: str) -> Optional[str]:
    """Extract host/owner/repository for common HTTPS, SSH and scp remotes."""
    value = remote.strip()
    if value.startswith("git@") and ":" in value:
        host, path = value.split(":", 1)
        hostname = host.split("@", 1)[1]
    else:
        uri = urlsplit(value)
        hostname = uri.hostname or ""
        path = uri.path
    parts = [part for part in path.removesuffix(".git").split("/") if part]
    if not hostname or len(parts) != 2:
        return None
    if not all(_REPO_PART.fullmatch(part) for part in parts):
        return None
    return f"{hostname.lower()}/{parts[0]}/{parts[1]}"


def inspect_repository(
    root: Path,
    expected_commit: Optional[str] = None,
    expected_repository: Optional[str] = None,
) -> RepositoryInfo:
    """Inspect the exact associated checkout rather than searching nearby trees."""
    if not root.is_absolute():
        raise BridgeError("ABSOLUTE_ROOT_REQUIRED", "Repository root must be absolute")
    resolved = root.resolve(strict=False)
    if not resolved.is_dir():
        raise BridgeError("REPOSITORY_UNAVAILABLE", "Associated repository does not exist")

    git_root = Path(_git(resolved, "rev-parse", "--show-toplevel")).resolve()
    if git_root != resolved:
        raise BridgeError(
            "REPOSITORY_ROOT_MISMATCH",
            "Requested directory is not the root of the associated Git repository",
        )
    head = _git(resolved, "rev-parse", "HEAD").lower()
    if not _COMMIT_PATTERN.fullmatch(head):
        raise BridgeError("GIT_HEAD_INVALID", "Git returned an invalid HEAD identifier")
    if expected_commit is not None:
        if not _COMMIT_PATTERN.fullmatch(expected_commit):
            raise BridgeError("EXPECTED_COMMIT_INVALID", "Expected commit is not a full hash")
        if head != expected_commit.lower():
            raise BridgeError("WRONG_CHECKOUT", "HEAD does not match the expected commit")

    clean = not _git(resolved, "status", "--porcelain", "--untracked-files=all")
    remote_result = subprocess.run(
        ["git", "-C", str(resolved), "remote", "get-url", "origin"],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        stdin=subprocess.DEVNULL,
    )
    remote = remote_result.stdout.strip() if remote_result.returncode == 0 else None
    identity = _remote_identity(remote) if remote else None

    if expected_repository:
        parts = expected_repository.split("/")
        if len(parts) not in (2, 3) or not all(
            _REPO_PART.fullmatch(part) for part in parts
        ):
            raise BridgeError("EXPECTED_REPOSITORY_INVALID", "Invalid repository identity")
        if identity is None:
            raise BridgeError("REPOSITORY_ID_UNVERIFIED", "Repository remote identity is not verifiable")
        expected_id = expected_repository.lower()
        actual_id = identity.lower()
        if len(parts) == 2:
            if "/".join(actual_id.split("/")[-2:]) != expected_id:
                raise BridgeError("WRONG_REPOSITORY", "The associated repository identity differs")
        elif actual_id != expected_id:
            raise BridgeError("WRONG_REPOSITORY", "The associated repository identity differs")

    return RepositoryInfo(
        root=str(resolved),
        head=head,
        clean=clean,
        remote_identity=identity,
        repository_id=identity,
    )
