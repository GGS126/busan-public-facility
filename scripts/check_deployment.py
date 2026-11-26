"""Check a deployed frontend/API without credentials or live Gemini requests."""

import argparse
import json
import re
import time
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen


def check(base_url: str, timeout: int) -> None:
    base = base_url.rstrip("/") + "/"
    if urlsplit(base).scheme not in {"http", "https"}:
        raise ValueError("http 또는 https 주소를 입력하세요.")
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urlopen(urljoin(base, "api/health"), timeout=5) as response:
                health = json.load(response)
            if health.get("status") != "ok" or health.get("facility_count", 0) < 1:
                raise ValueError("시설 규정이 로드되지 않았습니다.")
            break
        except (URLError, TimeoutError, ConnectionError):
            if time.monotonic() >= deadline:
                raise RuntimeError("서비스 준비 시간 초과") from None
            time.sleep(1)

    with urlopen(base, timeout=10) as response:
        assert "text/html" in response.headers.get("Content-Type", ""), "화면 HTML 응답이 아닙니다."
        html = response.read().decode("utf-8")
    assert 'id="root"' in html, "React 화면이 없습니다."
    assets = re.findall(r'(?:src|href)="(/assets/[^"?]+)', html)
    assert assets, "빌드된 화면 리소스가 없습니다."
    for path in assets:
        with urlopen(urljoin(base, path), timeout=10) as response:
            assert response.status == 200
    with urlopen(urljoin(base, "api/options"), timeout=10) as response:
        options = json.load(response)
    assert options.get("sports"), "실제 API 선택지가 없습니다."
    print("PASS: health, frontend HTML/assets and API options share one origin")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="예: http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=int, default=60, help="서버 기동 대기 시간(초)")
    args = parser.parse_args()
    check(args.base_url, args.timeout)
