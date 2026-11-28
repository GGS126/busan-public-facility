"""Check a deployed frontend/API without credentials or live Gemini requests."""

import argparse
from http.client import HTTPException
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen


def check(base_url: str, timeout: int) -> None:
    base = base_url.rstrip("/") + "/"
    if urlsplit(base).scheme not in {"http", "https"}:
        raise ValueError("http 또는 https 주소를 입력하세요.")
    if timeout <= 0:
        raise ValueError("대기 시간은 0보다 커야 합니다.")
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urlopen(urljoin(base, "api/health"), timeout=5) as response:
                health = json.load(response)
            if not isinstance(health, dict) or health.get("status") != "ok" or not isinstance(
                health.get("facility_count"), int
            ) or health["facility_count"] < 1:
                raise ValueError("시설 규정이 로드되지 않았습니다.")
            break
        except HTTPError as error:
            if 400 <= error.code < 500:
                raise RuntimeError(f"health 검사 실패: HTTP {error.code}") from None
        except (URLError, TimeoutError, ConnectionError, HTTPException, json.JSONDecodeError, UnicodeDecodeError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("서비스 준비 시간 초과") from None
        time.sleep(1)

    with urlopen(base, timeout=10) as response:
        if "text/html" not in response.headers.get("Content-Type", ""):
            raise RuntimeError("화면 HTML 응답이 아닙니다.")
        html = response.read().decode("utf-8")
    if 'id="root"' not in html:
        raise RuntimeError("React 화면이 없습니다.")
    assets = re.findall(r'(?:src|href)="(/assets/[^"?]+)', html)
    if not assets:
        raise RuntimeError("빌드된 화면 리소스가 없습니다.")
    for path in assets:
        with urlopen(urljoin(base, path), timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("화면 리소스 응답이 200이 아닙니다.")
    with urlopen(urljoin(base, "api/options"), timeout=10) as response:
        options = json.load(response)
    if not isinstance(options, dict) or not options.get("sports"):
        raise RuntimeError("실제 API 선택지가 없습니다.")
    print("PASS: health, frontend HTML/assets and API options share one origin")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="예: http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=60, help="서버 기동 대기 시간(초)")
    args = parser.parse_args()
    check(args.base_url, args.timeout)
