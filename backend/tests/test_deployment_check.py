"""The deployment smoke check must fail safely, including with Python -O."""
import importlib.util
import io
from http.client import RemoteDisconnected
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_deployment.py"
spec = importlib.util.spec_from_file_location("check_deployment", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def response(data, content_type="application/json"):
    result = io.BytesIO(data.encode())
    result.headers = {"Content-Type": content_type}
    result.status = 200
    return result


def success_responses():
    return [
        response('{"status":"ok","facility_count":8}'),
        response('<div id="root"></div><script src="/assets/app.js"></script>', "text/html"),
        response("javascript"),
        response('{"sports":[{"code":"tennis"}]}'),
    ]


@pytest.mark.parametrize("first", [
    response("not JSON"),
    RemoteDisconnected("starting"),
    HTTPError("http://localhost/api/health", 503, "starting", {}, None),
])
def test_starting_service_can_recover(monkeypatch, first):
    opening = Mock(side_effect=[first, *success_responses()])
    monkeypatch.setattr(checker, "urlopen", opening)
    monkeypatch.setattr(checker.time, "sleep", lambda _: None)
    checker.check("http://localhost", 3)
    assert opening.call_count == 5


def test_wrong_health_route_fails_without_retry(monkeypatch):
    opening = Mock(side_effect=HTTPError("http://localhost/api/health", 404, "", {}, None))
    monkeypatch.setattr(checker, "urlopen", opening)
    with pytest.raises(RuntimeError, match="HTTP 404"):
        checker.check("http://localhost", 60)
    assert opening.call_count == 1


def test_startup_retry_stops_at_deadline(monkeypatch):
    monkeypatch.setattr(checker, "urlopen", Mock(side_effect=RemoteDisconnected()))
    monkeypatch.setattr(checker.time, "monotonic", Mock(side_effect=[0, 2]))
    with pytest.raises(RuntimeError, match="시간 초과"):
        checker.check("http://localhost", 1)


def test_optimized_python_still_rejects_invalid_frontend():
    # Assertions in the test itself remain active; production checks run under -O.
    code = """
import importlib.util, io, sys
spec=importlib.util.spec_from_file_location("check",sys.argv[1])
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
class Response(io.BytesIO):
    headers={"Content-Type":"text/html"}
responses=iter([Response(b'{"status":"ok","facility_count":8}'),Response(b'no React root')])
module.urlopen=lambda *a,**k:next(responses)
module.check("http://localhost",1)
"""
    result = subprocess.run([sys.executable, "-O", "-c", code, str(SCRIPT)],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "RuntimeError" in result.stderr
