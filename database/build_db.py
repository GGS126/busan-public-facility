"""공식 규정 JSON에서 SQLite DB를 새로 생성합니다.

실행 예: python database/build_db.py
"""
import argparse
import os
from pathlib import Path
import tempfile

from load import load_many

ROOT = Path(__file__).resolve().parent
DEFAULT_FILES = [
    ROOT / 'seed.json',
    ROOT / 'samrak_winter_2026_2027.json',
    ROOT / 'gudeok_winter_2026_2027.json',
]


def build(db_path=ROOT / 'facilities.sqlite3', data_paths=None):
    """기존 DB와 무관하게 새 DB를 만든 뒤 검증 성공 시에만 교체합니다."""
    db_path = Path(db_path)
    inputs = [Path(p) for p in (DEFAULT_FILES if data_paths is None else data_paths)]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=db_path.parent) as tmp:
        staged_db = Path(tmp) / 'new.sqlite3'
        load_many(inputs, staged_db)
        try:
            os.replace(staged_db, db_path)
        except PermissionError as exc:
            raise PermissionError(
                f'기존 DB 파일을 교체할 수 없습니다: {db_path}. '
                'SQLite Viewer 등에서 열린 DB 연결을 닫고 재실행하세요.'
            ) from exc
    return db_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='JSON 원본에서 DB 새로 생성')
    parser.add_argument('--db', type=Path, default=ROOT / 'facilities.sqlite3')
    parser.add_argument('--data', nargs='+', type=Path,
                        help='기본값: 현재 등록된 시설 JSON 3개')
    args = parser.parse_args()
    result = build(args.db, args.data)
    print('DB 생성 및 무결성 검사 완료:', result)
