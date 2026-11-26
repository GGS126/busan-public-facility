"""취소·미이용 시 예상 환불(COMP-07). 요금 계산 결과와 이용일에 유효한 환불 규정으로 계산한다.

환불액은 온라인으로 먼저 낸 금액에 환불률을 곱한 값이다. 실제로 낸 금액이나 끝전 처리를 알 수 없으면
금액을 추정하지 않고 확인 필요로 둔다.

금액을 확정하는 기준은 DB 계층의 query_api.user_cancellation_refund(#32)와 같다. 금액은 사용자 취소이면서
일반 취소가 가능한 시점이고, 감면 없이 온라인 선결제액만 있을 때만 낸다.
"""

from app.models import CancelRefund, Cancellation, Conditions, FacilityRules, FeeResult, RefundRule, ReviewItem


def estimate_cancel_refund(
    rules: FacilityRules, conditions: Conditions, cancellation: Cancellation, fee: FeeResult
) -> CancelRefund:
    days_before = (conditions.date - cancellation.cancel_date).days if cancellation.cancel_date else None
    rule, problem = _matching_rule(rules, conditions, cancellation, days_before)

    def needs_review(code: str, reason: str) -> CancelRefund:
        source_id = rule.source_id if rule is not None else rules.source_on(conditions.date)
        return CancelRefund(
            status="needs_review",
            reason=cancellation.reason,
            days_before=days_before,
            rate_percent=rule.rate_percent if rule is not None and rule.confirmed else None,
            refund_amount=None,
            cost_after_refund=None,
            note=rule.note if rule is not None else None,
            source_id=rule.source_id if rule is not None else None,
            review_items=[ReviewItem(code=code, target="refund", reason=reason, source_id=source_id)],
        )

    if rule is None:
        return needs_review(*problem)
    if not rule.confirmed or rule.rate_percent is None:
        return needs_review("rule_missing", "환불률을 공식 자료로 확인하지 못했습니다. 공식 안내를 확인해 주세요.")
    # 우천·불가항력은 시설이 실제 사유를 확인해야 환불이 정해지므로, 환불률과 신청 방법만 안내한다(#32와 같은 기준).
    if cancellation.reason != "user_cancel":
        return needs_review(
            "facility_check_required",
            "우천·불가항력 환불은 시설이 사유를 확인한 뒤 정해집니다. 신청 방법에 따라 시설에 확인해 주세요.",
        )
    # 일반 취소를 받지 않는 시점(예: 당일)은 취소 자체가 안 되므로 환불액을 확정하지 않는다.
    if not rule.cancel_allowed:
        return needs_review("cancel_not_allowed", "이 시점에는 일반 취소를 받지 않아 환불액을 확정하지 않습니다.")

    # 휴장·회차 불일치 등으로 예약할 수 없는 조건이면 환불받을 예약도 없다. 이유는 fee.review_items에 있다.
    if fee.status == "not_eligible":
        return needs_review("amount_unverified", "이 조건으로는 예약할 수 없어 환불액을 계산하지 않습니다.")
    # 환불은 실제로 먼저 낸 금액을 기준으로 한다. 다음 금액이 섞이면 돌려받는 범위를 알 수 없다.
    if fee.status != "calculated" or fee.online_prepay is None:
        return needs_review("amount_unverified", "이용료가 확정되지 않아 환불액을 계산할 수 없습니다.")
    if fee.payment_unverified or fee.onsite_payment:
        return needs_review(
            "amount_unverified", "현장 결제액이나 결제 방식을 확인하지 못한 금액의 환불 기준이 확인되지 않았습니다."
        )
    if conditions.discount_selections:
        return needs_review("amount_unverified", "감면을 받는 예약을 취소할 때의 결제·반환 기준이 확인되지 않았습니다.")

    paid = fee.online_prepay
    if paid * rule.rate_percent % 100:
        return needs_review("amount_unverified", "환불액의 원 미만 끝전 처리 기준이 확인되지 않았습니다.")
    refund = paid * rule.rate_percent // 100
    return CancelRefund(
        status="calculated",
        reason=cancellation.reason,
        days_before=days_before,
        rate_percent=rule.rate_percent,
        refund_amount=refund,
        cost_after_refund=paid - refund,
        note=rule.note,
        source_id=rule.source_id,
        review_items=[],
    )


def _matching_rule(
    rules: FacilityRules, conditions: Conditions, cancellation: Cancellation, days_before: int | None
) -> tuple[RefundRule | None, tuple[str, str] | None]:
    """(적용할 규정, 규정을 고르지 못한 이유). 같은 사유에 해당하는 규정이 여럿이면 하나를 고르지 않는다."""
    if not rules.refund_rules:
        return None, ("rule_missing", "이 시설의 환불 규정을 확인할 수 없습니다. 공식 안내를 확인해 주세요.")
    if not any(rule.in_effect(conditions.date) for rule in rules.refund_rules):
        return None, ("rule_not_in_effect", "이용일에 유효한 환불 규정이 없습니다. 공식 안내를 확인해 주세요.")
    matched = [
        rule
        for rule in rules.refund_rules
        if rule.in_effect(conditions.date)
        and rule.reason == cancellation.reason
        and (days_before is None or rule.covers(days_before))
    ]
    if not matched:
        if days_before is None:
            when = "이 사유"
        elif days_before == 0:
            when = "당일 취소"
        else:
            when = f"이용일 {days_before}일 전 취소"
        return None, ("rule_missing", f"{when}의 환불 규정을 확인할 수 없습니다. 공식 안내를 확인해 주세요.")
    if len(matched) > 1:
        return None, ("rule_conflict", "같은 취소 조건에 해당하는 환불 규정이 여럿입니다. 공식 안내를 확인해 주세요.")
    return matched[0], None
