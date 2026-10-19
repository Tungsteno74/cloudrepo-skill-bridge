"""Run offline unit and deterministic-package validation without provider writes."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from build_release import build

ROOT = Path(__file__).resolve().parents[1]


def run(arguments: list[str]) -> None:
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([sys.executable, "-X", "utf8", *arguments], cwd=ROOT, check=True, env=environment)


def main() -> int:
    try:
        run(["plugins/cloudrepo-skill-bridge/package-validation.py"])
        run(["-m", "unittest", "discover", "-s", "plugins/cloudrepo-skill-bridge/tests", "-v"])
        run(["-m", "compileall", "-q", "plugins/cloudrepo-skill-bridge/runtime"])
        with tempfile.TemporaryDirectory(prefix="cloudrepo-skill-bridge-") as temporary:
            first = build(ROOT, Path(temporary) / "first")
            second = build(ROOT, Path(temporary) / "second")
            if first["sha256"] != second["sha256"]:
                raise ValueError("Rebuild produced different archive bytes.")
        print(build(ROOT))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
