"""Run the same database/backend checks locally and in CI, without live AI calls."""

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    # The runner itself also prints Korean messages before spawning UTF-8 children.
    # Hosted Windows defaults to cp1252, unlike Korean developers' local consoles.
    for stream in (sys.stdout, sys.stderr):
        configure = getattr(stream, "reconfigure", None)
        if configure is not None:
            configure(encoding="utf-8")
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
    # Include database regression tests present in this checkout.
    database_tests = sorted((ROOT / "database").glob("test_*.py"))
    if database_tests:
        checks.append((ROOT, ["-m", "pytest", "-q", *[str(path.relative_to(ROOT)) for path in database_tests]]))

    print("검사 전 백엔드·SQLite 뷰어를 종료하세요. 실제 규정 DB를 재생성합니다.", flush=True)
    for cwd, args in checks:
        print(f"\n[{cwd.relative_to(ROOT)}] python {' '.join(args)}", flush=True)
        result = subprocess.run([sys.executable, *args], cwd=cwd, env=env, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
