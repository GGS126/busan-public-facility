from test_engine import MONDAY, base_rule, conditions, discount_rule, facility

from app.compare import compare_facility


def source_ids(result) -> list[str]:
    return [source.source_id for source in result.sources]


def test_known_documents_listed_without_review():
    rules = facility(discount_rules=[discount_rule(required_documents=["서류"])])
    result = compare_facility(rules, conditions(discounts=["multi_child"]))

    assert result.checklist == ["서류"]
    assert result.checklist_review_items == []


def test_no_documents_required_is_not_a_review():
    rules = facility(discount_rules=[discount_rule(required_documents=[])])
    result = compare_facility(rules, conditions(discounts=["multi_child"]))

    assert result.checklist == []
    assert result.checklist_review_items == []


def test_unknown_documents_are_reported_with_source_and_keep_fee():
    rules = facility(discount_rules=[discount_rule(required_documents=None)])
    result = compare_facility(rules, conditions(discounts=["multi_child"]))

    assert result.fee.status == "calculated"
    assert result.checklist == []
    review = result.checklist_review_items[0]
    assert (review.code, review.target, review.source_id) == ("rule_missing", "checklist", "S-02")
    assert "S-02" in source_ids(result)


def test_discount_without_rule_points_checklist_to_facility_source():
    result = compare_facility(facility(), conditions(discounts=["multi_child"]))

    assert result.checklist_review_items[0].source_id == "S-00"
    assert "S-00" in source_ids(result)


def test_every_discount_document_keeps_its_source():
    rules = facility(
        [base_rule(source_id="S-00")],
        [
            discount_rule(source_id="S-01", required_documents=["첫째 서류"]),
            discount_rule(rule_id="DISC2", discount_type="disabled", source_id="S-02", required_documents=["둘째 서류"]),
        ],
    )
    result = compare_facility(rules, conditions(discounts=["multi_child", "disabled"]))

    assert result.fee.status == "needs_review"
    assert result.checklist == ["첫째 서류", "둘째 서류"]
    assert source_ids(result) == ["S-00", "S-01", "S-02"]


def test_no_discount_selected_gives_empty_checklist():
    rules = facility(discount_rules=[discount_rule(required_documents=None)])
    result = compare_facility(rules, conditions())

    assert result.checklist == []
    assert result.checklist_review_items == []


def test_holiday_source_listed_when_date_is_holiday():
    result = compare_facility(facility(holidays=[MONDAY]), conditions(day=MONDAY))

    assert "S-HOLIDAY" in source_ids(result)


def test_holiday_source_not_listed_on_ordinary_day():
    result = compare_facility(facility(), conditions(day=MONDAY))

    assert "S-HOLIDAY" not in source_ids(result)
