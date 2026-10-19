#!/usr/bin/env python3
"""Deterministic, read-only repository skill discovery and resolution CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from cloudrepo_skill_bridge import BridgeError, CloudRepoSkillBridge
from cloudrepo_skill_bridge.multi_repository import MultiCloudRepoSkillBridge, load_sources


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("discover", "resolve", "multi-discover", "multi-resolve"),
        help="Read-only discovery or resolution operation",
    )
    parser.add_argument(
        "--repository-root", type=Path,
        help="Absolute checkout root for the associated-repository commands",
    )
    parser.add_argument("--expected-commit", help="Full expected Git HEAD SHA")
    parser.add_argument("--expected-repository", help="Expected GitHub owner/repository identity")
    parser.add_argument("--sources-file", type=Path, help="Explicit authorized-source catalog for multi-* commands")
    parser.add_argument("--source-id", help="Source discriminator for multi-resolve")
    parser.add_argument("--name", help="Canonical skill name (resolve commands only)")
    parser.add_argument(
        "--reference", action="append", default=[],
        help="Read an explicitly selected text reference within the chosen skill",
    )
    parser.add_argument(
        "--allow-dirty", action="store_true",
        help="Allow dirty associated checkout only with caller approval; not for multi-*",
    )
    return parser


def run(arguments: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = build_parser()
    args = parser.parse_args(arguments)
    multi = args.command.startswith("multi-")
    if args.command.endswith("discover") and (args.name or args.reference or args.allow_dirty or args.source_id):
        parser.error("name, references, allow-dirty and source-id require a resolve command")
    if args.command.endswith("resolve") and not args.name:
        parser.error("resolve requires --name")

    if multi:
        if args.sources_file is None:
            parser.error("multi-* commands require --sources-file")
        if args.repository_root or args.expected_commit or args.expected_repository or args.allow_dirty:
            parser.error("multi-* commands use --sources-file; no associated checkout arguments")
        bridge = MultiCloudRepoSkillBridge(load_sources(args.sources_file))
        if args.command == "multi-discover":
            return bridge.discover()
        return bridge.resolve(args.name, source_id=args.source_id, references=args.reference)

    if args.sources_file or args.source_id:
        parser.error("associated-repository commands do not accept --sources-file or --source-id")
    if args.repository_root is None:
        parser.error("associated-repository commands require --repository-root")
    bridge = CloudRepoSkillBridge(
        args.repository_root,
        expected_commit=args.expected_commit,
        expected_repository=args.expected_repository,
    )
    if args.command == "discover":
        return {
            "status": "ok",
            "provenance": "repository_filesystem",
            "native_registration": "not_tested_by_bridge",
            "execution_performed": False,
            "repository": bridge.repository.as_dict(),
            "skills": [skill.as_dict() for skill in bridge.discover()],
        }
    return bridge.resolve(
        args.name,
        references=args.reference,
        allow_dirty=args.allow_dirty,
    ).as_dict()


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        result = run(argv)
    except BridgeError as exc:
        print(json.dumps({"status": "blocked", "code": exc.code, "reason": str(exc)}))
        return 2
    except OSError:
        print(json.dumps({"status": "blocked", "code": "IO_ERROR", "reason": "Unable to read a required local resource"}))
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
