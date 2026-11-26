"""Run the same database/backend checks locally and in CI, without live AI calls."""

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = os.environ.copy()
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", RULE_DATA_SOURCE="sample")
    # Automated checks inject fake extractors. Never pass a developer's live key to tests.
    env.pop("GEMINI_API_KEY", None)
    env.pop("GEMINI_MODEL", None)
    # Use only this checkout's modules, rather than a developer's external PYTHONPATH.
    env["PYTHONPATH"] = os.pathsep.join(str(ROOT / folder) for folder in ("backend", "database"))

    checks = [
        (ROOT, ["database/build_db.py"]),
        (ROOT, ["database/audit_checks.py"]),
        (ROOT / "backend", ["-m", "pytest", "-q"]),
    ]
    # PR #32 adds database/test_*.py. Include these once present in the checked-out code.
    database_tests = sorted((ROOT / "database").glob("test_*.py"))
    if database_tests:
        checks.append((ROOT, ["-m", "pytest", "-q", *[str(path.relative_to(ROOT)) for path in database_tests]]))

    for cwd, args in checks:
        print(f"\n[{cwd.relative_to(ROOT) or '.'}] python {' '.join(args)}", flush=True)
        result = subprocess.run([sys.executable, *args], cwd=cwd, env=env, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
