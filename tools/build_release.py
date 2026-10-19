"""Build a deterministic, standalone CloudRepo Skill Bridge archive."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "plugins" / "cloudrepo-skill-bridge"
SKIP = {"__pycache__", ".pytest_cache", ".git"}


def package_files(package: Path) -> list[Path]:
    """List safe regular package files in portable archive order."""
    files: list[Path] = []
    for path in sorted(package.rglob("*"), key=lambda item: item.relative_to(package).as_posix()):
        relative = path.relative_to(package)
        if SKIP.intersection(relative.parts) or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError("Symlinks are not distributable: " + relative.as_posix())
        if not path.is_file():
            continue
        if path.name == ".env" or path.suffix.lower() in {".key", ".pem", ".pfx"}:
            raise ValueError("Credential-like file is not distributable: " + relative.as_posix())
        files.append(path)
    if not files:
        raise ValueError("Plugin package is empty.")
    return files


def archive_bytes(package: Path, destination: Path) -> str:
    """Create a ZIP with fixed metadata, then return its SHA-256."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in package_files(package):
                entry = zipfile.ZipInfo(path.relative_to(package).as_posix(), (1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_STORED
                archive.writestr(entry, path.read_bytes())
        if zipfile.ZipFile(temporary).testzip() is not None:
            raise ValueError("Archive CRC verification failed.")
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        temporary.replace(destination)
        return digest
    finally:
        if temporary.exists():
            temporary.unlink()


def source_revision(root: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "not_observed"


def build(root: Path = ROOT, output: Path | None = None) -> dict[str, object]:
    package = root / "plugins" / "cloudrepo-skill-bridge"
    manifest = json.loads((package / "plugin.json").read_text(encoding="utf-8"))
    if manifest["name"] != package.name or not re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"]):
        raise ValueError("Unexpected package identity or version.")
    output = output or root / "dist"
    archive_name = f"{manifest['name']}-{manifest['version']}.zip"
    digest = archive_bytes(package, output / archive_name)
    report = {"plugin": manifest["name"], "version": manifest["version"], "archive": archive_name,
              "sha256": digest, "source_revision": source_revision(root), "file_count": len(package_files(package))}
    with (output / "SHA256SUMS").open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"{digest}  {archive_name}\n")
    with (output / "release-manifest.json").open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
