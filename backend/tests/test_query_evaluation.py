"""Guard evaluation conclusions against false passes and date-dependent fixtures."""
import importlib.util
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_query_parse.py"
spec = importlib.util.spec_from_file_location("query_evaluation", SCRIPT)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def test_fields_matching_does_not_hide_wrong_status_or_missing_question():
    case = {"id": "missing", "expected": {"status": "need_more",
            "conditions": {"sport": "tennis"}, "missing_fields": ["date"]}}
    result = {"status": "ok", "conditions": {"sport": "tennis"}, "missing_fields": []}
    row = evaluation.evaluate(case, result)
    assert all(row["field_matches"].values())
    assert not row["passed"]


def test_privacy_block_is_not_counted_as_seven_correct_extracted_fields():
    case = {"id": "privacy", "expected": {"status": "llm_failed", "conditions": {},
            "missing_fields": [], "block_reason": "personal_information"}}
    row = evaluation.evaluate(case, {"status": "llm_failed", "conditions": {}, "missing_fields": [],
                                     "message": "개인정보를 빼고 다시 입력하거나 직접 입력해 주세요."})
    assert row["passed"]
    assert row["field_matches"] == {}


def test_provider_failure_is_not_a_successful_privacy_block():
    case = {"id": "privacy", "expected": {"status": "llm_failed", "conditions": {},
            "missing_fields": [], "block_reason": "personal_information"}}
    row = evaluation.evaluate(case, {"status": "llm_failed", "conditions": {}, "missing_fields": [],
                                     "message": "조건을 추출하지 못했습니다. 직접 입력해 주세요."})
    assert not row["passed"]


def test_relative_date_expectations_cross_month_without_expiring():
    case = {"query": "{tomorrow}", "raw": {"date": "{day_after}"}}
    assert evaluation.materialize(case, date(2026, 11, 30)) == {
        "query": "2026-12-01", "raw": {"date": "2026-12-02"}}


def test_small_sample_p95_uses_nearest_rank():
    assert evaluation.percentile([10, 20, 200, 30], .95) == 200


@pytest.mark.parametrize("status,result", [(503, {}), (404, {}), (200, []), (200, None)])
def test_invalid_http_or_response_stops_the_evaluation(status, result):
    case = {"expected": {"status": "ok"}}
    actual = evaluation.api_result(Mock(status_code=status, json=Mock(return_value=result)))
    assert evaluation.stop_after_response(case, actual, status, {"privacy_block_match": True})


def test_privacy_provider_failure_stops_remaining_requests():
    case = {"expected": {"status": "llm_failed", "block_reason": "personal_information"}}
    assert evaluation.stop_after_response(case, {"status": "llm_failed"}, 200,
                                         {"privacy_block_match": False})
