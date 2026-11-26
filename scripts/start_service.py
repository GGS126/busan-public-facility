"""Rebuild the checked-in facility data and serve frontend/API as one service."""

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    frontend = ROOT / "frontend" / "dist"
    if not (frontend / "index.html").is_file():
        raise SystemExit("프론트 빌드가 없습니다. frontend에서 npm ci 및 npm run build를 실행하세요.")
    try:
        port = int(os.getenv("PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit("PORT는 1~65535 범위의 정수여야 합니다.") from None

    os.environ.update(
        RULE_DATA_SOURCE="sqlite",
        FRONTEND_DIST_PATH=str(frontend),
        PYTHONIOENCODING="utf-8",
    )
    # No user data is stored in SQLite. Rebuild it on every restart/redeploy.
    subprocess.run([sys.executable, str(ROOT / "database" / "build_db.py")], cwd=ROOT, check=True)
    os.chdir(ROOT / "backend")
    os.execv(sys.executable, [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", str(port), "--workers", "1",
    ])


if __name__ == "__main__":
    main()
