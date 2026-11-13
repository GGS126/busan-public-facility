# API 및 규정 데이터 초안

작성일: 2026-11-05  
상태: 팀 검토용 초안

첫 통합 목표인 **시설 1곳의 ‘직접 조건 입력 → 예상요금과 계산 근거 표시’** 에 필요한 형식을 정리합니다.
김승일과 요청·응답 형식을, 왕연호와 규정 데이터 항목을, 김규성과 AI 조건 형식을 맞추기 위한 문서이며 확정된 명세는 아닙니다.

SDD v0.1의 API-06(3.3절), 핵심 데이터 형식(3.4절), 규칙 엔진 처리 규칙(3.5절)을 기준으로 SRS v0.2와 대조했으며, SDD와 달라지거나 SDD에 없어 추가한 내용은 [SDD 대비 추가 제안](#sdd-대비-추가-제안)에 모았습니다.
SRS에 항목별 필수 여부가 정의되어 있지 않으므로 아래의 필수 여부도 제안입니다.
**모든 시설·금액·규정·출처는 형식을 보여 주기 위한 가상 값입니다.** 실제 검증 데이터로 사용하지 않습니다.

## 요금 계산·비교 API (API-06)

```
POST /api/compare
```

- 시설 1곳이면 요금 상세(UC-004), 여러 곳이면 비교표(UC-005)로 표시합니다. 첫 통합은 시설 1곳으로 진행합니다.
- 형식은 JSON, 이름은 `snake_case`, 금액은 원 단위 정수입니다.
- 날짜는 `YYYY-MM-DD`, 시간은 `HH:MM`이며 한국 시간 기준입니다.
- 계산 결과는 규정상 예상요금이며 실제 예약 가능 여부를 뜻하지 않습니다.

### 요청

```json
{
  "facility_ids": ["F001"],
  "conditions": {
    "sport": "futsal",
    "districts": ["해운대구"],
    "date": "2026-11-07",
    "start_time": "18:00",
    "end_time": "20:00",
    "discount_types": ["multi_child"],
    "source": "direct"
  }
}
```

| 항목 | 필수 | 검증 |
|---|---|---|
| `facility_ids` | 예 | 1곳 이상, 등록된 시설 |
| `conditions.sport` | 예 | `GET /api/options`의 종목 |
| `conditions.districts` | 아니요 | 시설 검색(API-02)의 지역 필터. 빈 배열이면 부산 전체. 이 API의 계산에는 사용하지 않음 |
| `conditions.date` | 예 | 올바른 날짜, 지난 날짜 불가 |
| `conditions.start_time` | 예 | 올바른 시간 |
| `conditions.end_time` | 예 | `start_time`보다 늦은 시간, 자정까지 이용은 `24:00` |
| `conditions.headcount` | 아니요 | 1 이상의 정수. SRS의 입력 항목에 없어 인원당 요금 시설이 확인되면 화면에 추가 |
| `conditions.discount_types` | 아니요 | `GET /api/options`의 감면 유형, 없으면 빈 배열 |
| `conditions.source` | 예 | `direct` 또는 `llm` |

`conditions`는 직접 입력과 AI 추출이 함께 쓰는 검색 조건 형식이며, 시설 검색(API-02)에서도 같은 형식을 사용합니다.
AI 추출 조건도 사용자가 확인·수정한 뒤 같은 검증을 거치므로, AI 없이도 계산이 동작합니다.
감면은 유형 코드만 받고 증빙 번호 같은 개인정보는 받지 않습니다.

### 요금 상태

규정 누락과 서버 오류를 구분하기 위해, 계산을 끝까지 시도했으면 규정이 부족해도 `200`으로 응답합니다.

| `fee.status` | 의미 | 합계 |
|---|---|---|
| `calculated` | 모든 항목을 근거가 있는 규정으로 계산 | 금액 표시 |
| `needs_review` | 규정이 없거나 충돌해 일부 항목을 계산하지 못함 | 모두 `null` |

### 응답 예시 1: 계산 완료

기본요금 시간당 20,000원, 조명료 시간당 5,000원, 기본요금에만 50% 감면(선결제 후 환급)이고 이용 시간 전체가 조명 시간대에 해당하는 경우입니다.

```json
{
  "results": [
    {
      "facility_id": "F001",
      "facility_name": "예시 체육관",
      "fee": {
        "status": "calculated",
        "items": [
          { "type": "base", "amount": 40000, "rule_id": "R-F001-01", "source_id": "S-01" },
          { "type": "lighting", "amount": 10000, "rule_id": "R-F001-02", "source_id": "S-01" },
          { "type": "discount", "amount": -20000, "rule_id": "R-F001-05", "source_id": "S-02", "method": "prepay_refund" }
        ],
        "total": 30000,
        "payment_due": 50000,
        "expected_refund": 20000,
        "net_cost_after_refund": 30000,
        "review_items": []
      },
      "terms": {
        "booking_open": "이용일 30일 전 09:00부터",
        "cancel_deadline": "이용일 3일 전까지",
        "refund": "기한 내 취소 시 전액 환불",
        "source_id": "S-03"
      },
      "checklist": ["다자녀 가정 확인 서류"],
      "checklist_review_items": [],
      "sources": [
        { "source_id": "S-01", "url": "https://example.com/fee-rules", "checked_at": "2026-11-05", "license": "가상 데이터" },
        { "source_id": "S-02", "url": "https://example.com/discount-rules", "checked_at": "2026-11-05", "license": "가상 데이터" },
        { "source_id": "S-03", "url": "https://example.com/booking-rules", "checked_at": "2026-11-05", "license": "가상 데이터" }
      ]
    }
  ]
}
```

합계는 금액 항목에서 다음과 같이 계산합니다.

| 결과 | 계산 | 예시 |
|---|---|---|
| `payment_due` (최초 납부액) | `prepay_refund`를 제외한 모든 항목의 합 | 40,000 + 10,000 = 50,000 |
| `expected_refund` (예상 환급액) | `prepay_refund` 항목의 합의 절댓값 | 20,000 |
| `net_cost_after_refund` (환급 후 예상 부담액) | 최초 납부액 − 예상 환급액 | 50,000 − 20,000 = 30,000 |
| `total` | `net_cost_after_refund`와 같은 값 | 30,000 |

납부 시 바로 깎는 현장 감면은 `method: "onsite"`로 표시하며, 음수 금액이 최초 납부액에 반영됩니다.
조명료나 감면이 해당되지 않으면 `items`에서 제외합니다(UC-004). 적용 여부나 금액을 알 수 없는 항목만 `review_items`에 넣습니다.

### 응답 예시 2: 확인 필요

두 감면의 중복 적용 여부가 공식 자료에서 확인되지 않은 경우입니다.
SDD 3.5절에 따라 합계 대신 계산된 항목과 ‘확인 필요’ 항목을 나눠 반환하고, 사유와 공식 출처 링크를 표시할 수 있게 합니다.
감면이 미확인이면 부분 합계가 실제보다 높게 보일 수 있으므로 화면에도 부분 합계를 표시하지 않습니다.

```json
{
  "results": [
    {
      "facility_id": "F001",
      "facility_name": "예시 체육관",
      "fee": {
        "status": "needs_review",
        "items": [
          { "type": "base", "amount": 40000, "rule_id": "R-F001-01", "source_id": "S-01" },
          { "type": "lighting", "amount": 10000, "rule_id": "R-F001-02", "source_id": "S-01" }
        ],
        "total": null,
        "payment_due": null,
        "expected_refund": null,
        "net_cost_after_refund": null,
        "review_items": [
          {
            "code": "rule_missing",
            "target": "discount",
            "reason": "multi_child와 disabled 감면의 중복 적용 여부를 확인할 수 없습니다.",
            "source_id": "S-02"
          }
        ]
      },
      "terms": {
        "booking_open": "이용일 30일 전 09:00부터",
        "cancel_deadline": "이용일 3일 전까지",
        "refund": "기한 내 취소 시 전액 환불",
        "source_id": "S-03"
      },
      "checklist": ["다자녀 가정 확인 서류", "장애인 증명 서류"],
      "checklist_review_items": [],
      "sources": [
        { "source_id": "S-01", "url": "https://example.com/fee-rules", "checked_at": "2026-11-05", "license": "가상 데이터" },
        { "source_id": "S-02", "url": "https://example.com/discount-rules", "checked_at": "2026-11-05", "license": "가상 데이터" },
        { "source_id": "S-03", "url": "https://example.com/booking-rules", "checked_at": "2026-11-05", "license": "가상 데이터" }
      ]
    }
  ]
}
```

| `review_items[].code` | 상황 |
|---|---|
| `rule_missing` | 필요한 규정이 없거나 미확인 상태 |
| `rule_conflict` | 같은 조건에 적용되는 규정이 서로 충돌 |
| `rule_not_in_effect` | 이용일에 적용되는 규정이 없음 |

`review_items[].target`은 표의 행과 연결되도록 `base`, `lighting`, `discount` 중 하나로 표시합니다.
선택한 감면의 증빙서류를 확인하지 못하면 `checklist_review_items`에 `target: "checklist"`로 반환합니다. 빈 `checklist`는 필요한 서류가 없다는 뜻이며, 이 경우 요금 상태는 바뀌지 않습니다.
규정이 아예 없어 근거 출처가 없으면 `review_items[].source_id`에 시설의 `source_id`를 넣어 공식 출처 링크를 표시할 수 있게 합니다(AC-007).

`terms`의 값을 확인하지 못했으면 해당 값을 `null`로 반환하고, `terms.source_id`로 출처와 확인일을 표시합니다(FR-011).
첫 통합에서는 `fee`와 `sources`를 먼저 구현하고, `terms`와 `checklist`는 형식만 유지합니다.

### 오류 응답

요청을 처리할 수 없을 때만 오류로 응답합니다.

```json
{
  "error": {
    "code": "validation_error",
    "message": "입력값을 확인해 주세요.",
    "fields": [
      {
        "field": "conditions.end_time",
        "code": "invalid_time_range",
        "message": "종료 시간은 시작 시간보다 늦어야 합니다."
      }
    ]
  }
}
```

| HTTP 상태 | `code` | 상황 |
|---|---|---|
| 400 | `validation_error` | 필수값 누락, 형식 오류, 지난 날짜, 시작 ≥ 종료. `fields`에 항목별 오류 반환 |
| 404 | `facility_not_found` | 등록되지 않은 시설 |
| 500 | `internal_error` | 시설 데이터 조회 실패 등 서버 오류. 내부 정보는 응답에 넣지 않음 |

로그에는 API 키와 개인정보를 남기지 않으며, 감면 유형도 개인 정보를 드러낼 수 있으므로 기록하지 않습니다.

## API-06 입력 확장안

작성일: 2026-11-09  
상태: 팀 검토용 제안 (#7, #16)

PR #12의 실제 테니스장 3곳 규정을 대조한 결과, 위 요청 형식으로는 정답 사례를 계산할 수 없어 입력을 확장합니다.
이 절의 금액은 PR #12의 정답 사례를 기준으로 합니다.

| 규정 | 시설 | 현재 형식의 문제 |
|---|---|---|
| 감면 대상 인원에 비례한 감면 | 해운대수목원, 삼락생태공원 | 감면 유형만 받아 기본요금 전체를 감면함 |
| 예약 대표자가 대상일 때만 감면 | 구덕운동장 | 대표자 여부를 받지 않음 |
| 사용자가 고르는 선택 조명 | 해운대수목원, 삼락생태공원 | 조명 사용 시간을 받지 않음 |
| 지정 회차, 허용 이용시간 | 3곳 모두 | 선택할 수 없는 시간을 '확인 필요'로 잘못 안내함 |

### 확장된 요청

```json
{
  "facility_ids": ["busan_haeundae_arboretum_tennis"],
  "conditions": {
    "sport": "tennis",
    "districts": [],
    "date": "2026-11-11",
    "start_time": "07:00",
    "end_time": "09:00",
    "headcount": 4,
    "discounts": [
      { "type": "disabled", "count": 1, "holder": true },
      { "type": "multi_child", "count": 1, "holder": false }
    ],
    "optional_lighting_minutes": 0,
    "source": "direct"
  }
}
```

| 항목 | 필수 | 검증 |
|---|---|---|
| `conditions.headcount` | `discounts`가 있으면 예 | 1 이상의 정수. 예약 대표자를 포함한 전체 이용 인원 |
| `conditions.discounts` | 아니요 | 감면 대상자가 없으면 빈 배열 |
| `discounts[].type` | 예 | `GET /api/options`의 감면 유형, 항목 간 중복 불가 |
| `discounts[].count` | 예 | 1 이상의 정수. 이 유형의 감면 대상 인원 |
| `discounts[].holder` | 아니요 | 예약 대표자가 이 유형의 대상자이면 `true`, 기본값 `false`. `true`는 한 항목만 가능 |
| `conditions.optional_lighting_minutes` | 아니요 | 0 이상의 정수, 기본값 0. 이용 시간보다 길 수 없음 |

- `discounts[].count`의 합은 `headcount`를 넘을 수 없습니다. 대표자도 `count`에 포함합니다.
- `discount_types`는 `discounts`로 대체합니다. 한 사람에게는 감면 유형 하나만 적용한다고 보고, 서로 다른 사람의 유형은 함께 받을 수 있습니다.
- 입력은 인원수와 유형 코드뿐이며 이름·증빙 번호 같은 개인정보는 받지 않습니다.
- 위 항목을 위반하면 지금처럼 `400 validation_error`와 항목별 `fields`로 응답합니다.

### 감면 계산 방식

시설마다 감면 규정에 계산 방식(`basis`)을 두고, 같은 입력으로 시설별 규정에 맞게 계산합니다.

| `basis` | 계산 | 시설 |
|---|---|---|
| `per_eligible_person` | 기본요금 ÷ `headcount` × `count` × 감면율 | 해운대수목원, 삼락생태공원 |
| `holder_whole_fee` | 대표자가 대상(`holder: true`)이면 기본요금 × 감면율, 아니면 0원 | 구덕운동장 |
| `whole_fee` | 기본요금 × 감면율 (현재 엔진 방식) | 해당 시설 없음 |

| 사례 | 조건 | 감면액 |
|---|---|---|
| T06 해운대 평일 07~09시 | 8,000원, 4명 중 감면 대상 2명 | 8,000 ÷ 4 × 2 × 50% = 2,000원 환급 |
| S04 삼락 주말 15~17시 | 9,000원, 3명 중 1명 | 9,000 ÷ 3 × 1 × 50% = 1,500원 환급 |
| 구덕 대표자 대상 | 8,000원, 대표자 장애인 | 8,000 × 50% = 4,000원 환급 |
| 구덕 동반자만 대상 | 8,000원, 동반자 3명 | 0원 |

- 감면 유형별로 금액 항목(`type: "discount"`)을 하나씩 반환하고, 조명료는 세 시설 모두 감면 대상에서 제외합니다.
- 나눠 떨어지지 않는 금액은 규정의 `rounding`으로 처리하고, 끝전 기준이 없으면 '확인 필요'(`rule_missing`)로 반환합니다.
- `per_eligible_person`은 대표자 여부와 관계없이 인원으로 계산하고, `holder_whole_fee`는 `count`와 관계없이 대표자 여부로 계산합니다.

### 선택 조명

`optional_lighting_minutes`는 지정 회차 중 사용자가 조명을 켤 시간입니다. 필수 조명(해운대 20~22시 회차, 구덕 18시 이후)은 지금처럼 이용 시간으로 자동 계산합니다.

| 시설 | 선택 조명 규정 |
|---|---|
| 해운대수목원 | 07~20시 회차, 60분 10,000원 + 남은 10분마다 1,600원, 현장 결제 |
| 삼락생태공원 | 08~17시 회차, 60분 단위 올림 10,000원 |
| 구덕운동장 | 없음 (조명은 18시 이후 필수 부과) |

### 이용할 수 없는 시간

지정 회차와 다른 시간, 허용되지 않는 이용시간처럼 규정상 이용할 수 없는 조건은 계산하지 않고 `fee.status`를 `not_eligible`로 반환합니다.
[함께 정할 내용](#함께-정할-내용)의 `not_eligible` 제안을 구체화한 것입니다.

| `fee.status` | 의미 | 합계 |
|---|---|---|
| `not_eligible` | 규정상 이 조건으로 이용할 수 없음 | 모두 `null` |

| `review_items[].code` | 상황 | 예 |
|---|---|---|
| `slot_mismatch` | 지정 회차와 시간이 다름 | 해운대 09:00~10:00 |
| `duration_not_allowed` | 허용 이용시간이 아님 | 구덕 3시간 |
| `outside_hours` | 운영시간 밖 | 구덕 22:00 이후 |

여러 시설을 비교할 때 한 시설만 이용할 수 없을 수 있으므로 `400` 대신 시설별 결과로 반환합니다.
`review_items[].target`에는 `time`을 추가합니다.

### 다른 API에 미치는 영향

| 대상 | 변경 |
|---|---|
| 프론트엔드 (#16) | '감면 대상 인원' 입력을 유형별 `count`로 보내고, 대표자 여부와 선택 조명 시간 입력을 추가 |
| 자연어 추출 (#15) | 감면 유형만 추출하고 인원·대표자 여부는 사용자 확인 화면에서 입력. AI가 인원을 추정하지 않음 |
| `GET /api/options` | 변경 없음 |
| 규칙 엔진 | 감면 규정에 `basis`, 시설에 회차·허용 이용시간, 조명에 선택 조명 규정 추가 |

### 확인할 내용

| 담당 | 확인할 내용 |
|---|---|
| 김승일 | 유형별 인원 + 대표자 여부 입력을 화면에 넣을 수 있는지, `not_eligible` 표시 방법 |
| 왕연호 | 중증 장애인 보호자 1명을 `count`에 포함하는 것이 맞는지, 나눠 떨어지지 않을 때의 끝전 처리 기준과 정답 사례 |
| 김규성 | 자연어 추출 결과를 `discounts` 형식으로 넘기고 인원은 확인 화면에서 받는 방식이 괜찮은지 |
| 공통 | 해당 시설에 없는 선택 조명을 요청했을 때 0원으로 계산하고 안내할지, 확인 필요로 처리할지 |

## 규정 데이터 항목

저장 구조와 DB 종류는 이 항목을 기준으로 왕연호와 함께 정합니다.

**모르는 값은 추정해서 채우지 않고 `null`로 둡니다.** 규칙 엔진은 계산에 필요한 값이 `null`이면 `rule_missing`을 반환합니다.

규칙 엔진은 이용 시간을 요금 단위로 나누고, 단위마다 요일·시간대를 판단해 요금을 합산합니다.
조명료는 단위가 시설·계절별 조명 시간대와 겹치면 가산하므로 사용자가 따로 입력하지 않습니다.

### 시설

| 항목 | 설명 | 시기 |
|---|---|---|
| `facility_id`, `name` | 시설 식별자와 이름 | 첫 통합 |
| `source_id` | 시설 정보의 공식 출처 | 첫 통합 |
| `holidays` | 시설별로 두지 않고 백엔드의 공통 공휴일 목록(`backend/data/holidays_kr.json`)을 사용. 목록 기간 밖이면 공휴일 여부에 따라 요금이 달라질 때만 확인 필요 | 첫 통합 |
| `address`, `district` | 주소와 지역 | 검색 |
| `operating_hours`, `phone` | 운영시간과 연락처 | 검색 |
| `reservation_url` | 공식 예약 링크 | 준비사항 |

### 출처

| 항목 | 설명 | 예시 |
|---|---|---|
| `source_id` | 출처 식별자 | `S-01` |
| `url` | 공식 출처 URL | `https://example.com/fee-rules` |
| `checked_at` | 확인일, 필수 | `2026-11-05` |
| `license` | 이용허락범위와 출처표시 조건, 필수 | 값 형식은 함께 정할 내용 참고 |

### 요금 규정

| 항목 | 설명 | 예시 |
|---|---|---|
| `rule_id` | 규정 식별자 | `R-F001-02` |
| `facility_id`, `sport` | 적용 시설과 종목 | `F001`, `futsal` |
| `type` | 기본요금 또는 조명료 | `base`, `lighting` |
| `amount` | 단위당 금액 | `5000` |
| `unit_minutes` | 요금 단위 시간 | `60` |
| `partial_unit` | 단위 미만 처리 방식 | `round_up` |
| `day_types` | 적용 요일 구분. 모르면 `null`, 모든 요일이면 세 값을 모두 입력 | `["weekday", "weekend", "holiday"]` |
| `time_from`, `time_to` | 적용 시간대, 조명 시간대. 모르면 `null`, 종일이면 `00:00`, `24:00` | `18:00`, `22:00` |
| `months` | 적용 월, 계절 기준이 시설마다 다를 수 있어 월로 표시. 전체면 `null` | `[11, 12, 1, 2]` |
| `effective_from`, `effective_to` | 규정 적용 기간, 시행일을 시작일로 사용 | `2026-01-01`, `null` |
| `source_id` | 근거 출처 | `S-01` |

### 감면 규정

| 항목 | 설명 | 예시 |
|---|---|---|
| `rule_id`, `facility_id` | 규정 식별자와 적용 시설 | `R-F001-05` |
| `discount_type` | 감면 유형 코드 | `multi_child` |
| `rate` 또는 `fixed_amount` | 감면율 또는 감면액 | `0.5` |
| `applies_to` | 감면 대상 요금 | `base`, `base_and_lighting` |
| `method` | 현장 감면 또는 선결제 후 환급 | `onsite`, `prepay_refund` |
| `stackable` | 다른 감면과 중복 가능 여부, 미확인이면 `null` | `false` |
| `rounding` | 끝전 처리 방식 | `floor_10` |
| `required_documents` | 증빙서류, 체크리스트에 사용 | `["다자녀 가정 확인 서류"]` |
| `effective_from`, `effective_to` | 규정 적용 기간 | `2026-01-01`, `null` |
| `source_id` | 근거 출처 | `S-02` |

### 예약·취소·환불 규정

응답의 `terms`와 `checklist`에 사용합니다. 첫 통합의 계산에는 쓰지 않지만, 시설 조사 때 함께 확인해 두면 다시 조사하지 않아도 됩니다.

| 항목 | 설명 |
|---|---|
| `booking_open` | 예약 시작 시점 |
| `cancel_deadline` | 취소 가능 기한 |
| `refund` | 취소 시점별 환불 기준 |
| `restrictions` | 신청 제한과 주의사항 |
| `effective_from`, `effective_to` | 규정 적용 기간 |
| `source_id` | 근거 출처 |

### 계산 검증 사례

왕연호가 작성하는 정답 사례(AC-006)는 다음 형식이면 그대로 자동 테스트로 옮길 수 있습니다.
기본요금, 조명료, 감면, 선결제 후 환급, 규정 누락을 각각 1건 이상 포함합니다.

| 항목 | 설명 |
|---|---|
| `case_id` | 사례 식별자 |
| `facility_id` | 대상 시설 |
| `conditions` | 요청의 `conditions`와 같은 형식 |
| `expected_status` | `calculated` 또는 `needs_review` |
| `expected_fee` | `total`, `payment_due`, `expected_refund`, `net_cost_after_refund` |
| `calculation_note` | 공식 자료 기준 계산 과정 |
| `source_id` | 근거 출처 |

## SDD 대비 추가 제안

SDD에 정의되지 않아 이 문서에서 제안하는 내용입니다. 합의되면 SDD에도 반영합니다.

| 항목 | 제안 | 이유 |
|---|---|---|
| 요청 형식 | `facility_ids`와 `conditions`로 구분 | SDD는 ‘검색 조건 + 시설 ID 목록’만 정의 |
| `headcount` | 선택 항목으로 변경 | SDD 예시에는 있지만 SRS 입력 항목과 UI-01에 없음 |
| `facility_name` | 응답에 추가 | UI-05 비교표에 시설명 필요 |
| `terms.source_id` | 응답에 추가 | FR-011, AC-008은 규정 결과마다 출처와 확인일을 요구 |
| `checklist_review_items` | 응답에 추가 | 증빙서류 미확인과 서류 불필요를 구분(SDD 3.6) |
| 응답 묶음 | 시설별 결과를 `results` 배열로 반환 | SDD 예시는 시설 1곳의 결과만 표시 |
| 확인 필요 상태 | `needs_review`와 `review_items` 추가 | SDD는 `calculated`만 예시로 제시 |
| `source` 값 | `direct` 추가 | SDD 예시는 `llm`만 제시 |
| 현장 감면 | `method`에 `onsite` 추가 | SDD 예시는 `prepay_refund`만 제시 |
| 오류 응답 | 위의 오류 형식과 코드 | SDD는 오류 형식 통일만 명시 |
| 규정 항목 | `partial_unit`, `rounding`, `months`, `holidays` 등 구체화 | SDD 3.5절의 처리 규칙을 데이터로 표현 |
| `sources[].license` | 응답에 추가 | 데이터별 이용조건과 출처표시 조건 전달(NFR-006) |

## 담당자별 확인할 내용

### 김승일

1. 응답의 `fee`, `terms`, `checklist`, `sources`로 결과 화면을 그릴 수 있는지
2. 비교표의 시설명을 응답의 `facility_name`으로 표시해도 되는지
3. 금액 항목 표시에 `type` 외의 이름이나 계산식 문구가 필요한지
4. `needs_review`일 때 합계 대신 ‘확인 필요’와 사유를 표시하도록 UI-05 와이어프레임의 `00,000원 + 확인 필요`를 바꿔도 되는지
5. 입력 오류를 `fields`의 항목별로 표시할 수 있는지

### 왕연호

1. 조사 중인 시설의 규정을 위 항목으로 표현할 수 있는지, 빠진 항목은 없는지
2. 이용일 기준으로 유효한 규정을 조회할 수 있도록 적용 기간을 저장할 수 있는지
3. 감면 유형 코드 목록과 시설 간 공통 사용 가능 여부
4. 시간 단위 외의 요금(인원당, 회당)이나 장비 대여처럼 사용자가 선택하는 요금이 있는지. 있으면 항목과 요청 형식을 추가해야 합니다.
5. 운영시간 밖이나 휴관일 이용, 인원 제한 초과처럼 규정상 이용할 수 없는 경우가 어떻게 안내되어 있는지
6. ‘공공누리 유형 미표기’인 DATA-04, DATA-05의 이용조건을 어떻게 확인하고 기록할지

### 김규성

1. AI 추출 결과를 `conditions` 형식과 `source: "llm"`으로 만들 수 있는지
2. AI가 추출하지 못한 값을 API-01의 `need_more`와 어떻게 함께 전달할지
3. SDD의 AI 컴포넌트(COMP-03, 09, 11) 담당 제안을 현재 역할 배분에 맞춰 어떻게 나눌지
4. 첫 통합의 실행 환경에 필요한 정보

### 함께 정할 내용

| 항목 | 제안 |
|---|---|
| `total`과 `net_cost_after_refund` | 항상 같은 값이므로 하나로 합칠지 결정. SDD와 맞추기 위해 합의 전까지 둘 다 유지 |
| 이용할 수 없는 조건 | 운영시간 밖 등이 API-06에 직접 들어온 경우 `fee.status`에 `not_eligible`을 추가하고 사유를 반환 |
| 자정을 넘기는 이용 시간 | SDD의 시작 ≥ 종료 검증에 따라 첫 통합에서는 입력 오류로 처리 |
| 이용조건 미표기 데이터 | SRS 2.4는 이용조건을 확인하지 못한 데이터의 사용을 금지하고 SDD는 빈 값의 적재를 거부하므로, 확인 결과를 `license`에 기록하는 형식을 결정 |
| `checklist` 위치 | UI-06은 API-07을 호출하므로 API-06 응답에도 둘지 준비사항 단계에서 결정. 합의 전까지 SDD대로 유지 |

체크리스트 API(API-07)는 SDD를 바탕으로 이 문서의 형식에 맞춰 구체화합니다. 선택지 API(API-05)는 구현되어 있고, 시설 검색·상세 API는 아래 절에서 제안합니다.

## 시설 검색·상세 API (API-02, API-03)

작성일: 2026-11-09  
상태: 팀 검토용 제안 (#16)

조건에 맞는 후보 시설 목록(UI-03)과 시설 상세(UI-04)에 필요한 형식입니다(FR-003, FR-004, FR-011, FR-012).
프론트엔드에 하드코딩된 시설 목록·주소·예약 URL과 `facilitySlots.js`의 회차를 이 API로 대체합니다.
예시는 PR #12의 실제 시설 정보를 사용합니다.

### 시설 검색 (API-02)

```
POST /api/facilities/search
```

```json
{
  "conditions": {
    "sport": "tennis",
    "districts": [],
    "date": "2026-11-11",
    "start_time": "09:00",
    "end_time": "10:00",
    "source": "direct"
  }
}
```

`conditions`는 API-06과 같은 형식이고 같은 검증을 거칩니다. 검색에서는 다음 항목만 다르게 다룹니다.

| 항목 | 필수 | 검색에서의 처리 |
|---|---|---|
| `sport` | 예 | 이 종목의 요금 규정이 있는 시설만 반환 |
| `districts` | 아니요 | 지정한 지역의 시설만 반환. 빈 배열이면 부산 전체 |
| `date` | 예 | 이용일에 유효한 이용시간 규정으로 시간 선택지와 이용 가능 여부 판단 |
| `start_time`, `end_time` | 아니요 | 둘 다 있으면 시설별로 이용 가능 여부 판단, 없으면 판단 생략. 하나만 있으면 `400` |
| `headcount`, 감면 항목 | 아니요 | 검색에 쓰지 않음. 검색 → 비교로 같은 조건을 넘길 수 있게 받기만 함 |

종목·지역은 **목록에서 제외하는 조건**입니다. 날짜·시간은 목록에서 빼지 않고 시설별로 판단 결과를 붙입니다.
시간 때문에 시설이 사라지면 사용자가 "가능한 회차"를 알 수 없기 때문입니다(결과 없음 시 조건 완화 안내, UC-003).

#### 응답

```json
{
  "results": [
    {
      "facility_id": "busan_haeundae_arboretum_tennis",
      "name": "해운대수목원 테니스장",
      "sport": "tennis",
      "district": "해운대구",
      "address": "부산 해운대구 석대동 26",
      "time_check": {
        "status": "not_eligible",
        "review_items": [
          {
            "code": "slot_mismatch",
            "target": "time",
            "reason": "정해진 회차로만 예약할 수 있습니다. 가능한 회차: 07:00~09:00, 09:00~11:00, …",
            "source_id": "busan_reserve_619_2026h2"
          }
        ]
      },
      "time_options": {
        "selection": "fixed_slot",
        "slots": [
          { "start_time": "07:00", "end_time": "09:00" },
          { "start_time": "09:00", "end_time": "11:00" }
        ],
        "allowed_minutes": [],
        "open_time": null,
        "close_time": null,
        "source_id": "busan_reserve_619_2026h2"
      },
      "source_id": "busan_reserve_619_2026h2"
    }
  ],
  "alternatives": null,
  "sources": [
    {
      "source_id": "busan_reserve_619_2026h2",
      "url": "https://reserve.busan.go.kr/rent/view?resveGroupSn=531&progrmSn=619",
      "checked_at": "2026-11-06",
      "license": null
    }
  ]
}
```

| `time_check.status` | 의미 |
|---|---|
| `eligible` | 규정상 이 시간에 이용 가능. 실제 잔여석은 확인하지 않음 |
| `not_eligible` | 규정상 이 시간에 이용 불가. 사유는 API-06의 `slot_mismatch`, `duration_not_allowed`, `outside_hours`와 같음 |
| `unknown` | 이용일에 유효한 이용시간 규정이 없거나, 요청에 시간이 없어 판단하지 않음 |

- 정렬은 `eligible` → `unknown` → `not_eligible` 순서이고, 같은 상태 안에서는 시설명 순서입니다.
- `time_options`는 이용일에 유효한 이용시간 규정입니다. 규정이 없으면 `null`입니다. 프론트엔드는 이 값으로 회차·시간 선택지를 그립니다.
  - `fixed_slot`: `slots` 중에서 선택
  - `flexible`: `open_time`~`close_time` 안에서 `allowed_minutes` 길이로 선택
- 이용 가능 여부는 **규정상 판단**이며, 실제 예약 가능 여부(잔여석)는 제공하지 않습니다. 화면에 공식 예약 사이트 확인 안내를 함께 표시합니다.
- 요금은 계산하지 않습니다. 요금은 비교할 시설을 고른 뒤 API-06으로 계산합니다.

#### 결과 없음

종목·지역에 맞는 시설이 없으면 `200`과 빈 `results`를 반환합니다.
지역을 지정했는데 결과가 없으면, 같은 종목의 시설이 있는 다른 지역을 `alternatives`로 안내합니다.

```json
{
  "results": [],
  "alternatives": { "districts": ["사상구", "서구", "해운대구"] },
  "sources": []
}
```

종목 자체가 등록되지 않았으면 `GET /api/options`에 없는 값이므로 API-06처럼 `400 invalid_option`으로 응답합니다.

### 시설 상세 (API-03)

```
GET /api/facilities/{facility_id}?date=2026-11-11
```

`date`는 선택이며, 없으면 오늘(한국 시간) 기준으로 유효한 규정을 보여 줍니다. 지난 날짜는 `400`입니다.

```json
{
  "facility_id": "busan_gudeok_stadium_tennis",
  "name": "구덕운동장 테니스장",
  "sports": ["tennis"],
  "district": "서구",
  "address": "부산 서구 망양로 57 (서대신동3가, 구덕운동장)",
  "phone": "051-602-2215 / 051-602-2201",
  "operating_hours": { "open_time": "08:00", "close_time": "22:00", "note": "연중무휴(정기 휴무일 없음)" },
  "closure_note": "연중무휴(명절 등 별도 공지일 제외)",
  "booking_url": "https://reserve.busan.go.kr/rent/view?resveGroupSn=475&progrmSn=472",
  "time_options": [
    {
      "sport": "tennis",
      "selection": "flexible",
      "slots": [],
      "allowed_minutes": [60, 120],
      "open_time": "08:00",
      "close_time": "22:00",
      "source_id": "busan_reserve_472_2026winter"
    }
  ],
  "source_id": "busan_reserve_472_2026winter",
  "sources": [
    {
      "source_id": "busan_reserve_472_2026winter",
      "url": "https://reserve.busan.go.kr/rent/view?resveGroupSn=475&progrmSn=472",
      "checked_at": "2026-11-06",
      "license": null
    }
  ]
}
```

- 모르는 값은 `null`이며 화면에는 '확인 필요'로 표시합니다(FR-004).
- `booking_url`이 `null`이면 공식 예약 링크 대신 '공식 예약 링크 확인 필요'를 표시합니다(FR-012).
- 등록되지 않은 시설은 `404 facility_not_found`입니다.
- 요금·예약·취소 조건은 API-06이 맡고, 상세 API에는 넣지 않습니다.

### 필요한 데이터

| 항목 | PR #12 DB | 상태 |
|---|---|---|
| `name`, `address`, `phone`, `booking_url` | `facilities` | 있음 |
| `operating_hours` | `facilities.open_time`, `close_time`, `holiday_note` | 있음 |
| `closure_note` | `reservation_rules.closure_note` | 있음 |
| `time_options` | `time_selection_policies`, `pricing_rules`의 회차 | 있음. 백엔드 이용시간 규정(#19)으로 변환 |
| `district` | 없음 | **추가 필요**. 지역 필터와 `/api/options`의 지역 선택지에 사용 |
| `sources[].license` | 없음 | 확인 필요. 없으면 `null` |

시설 데이터 항목의 `reservation_url`은 DB와 프론트엔드에 맞춰 `booking_url`로 부릅니다.

### SDD와 다른 점

| 항목 | 제안 | 이유 |
|---|---|---|
| 검색 요청 | `{"conditions": {...}}` | API-06과 같은 조건 형식을 재사용 |
| `districts` | 선택 항목, 빈 배열이면 부산 전체 | 직접 입력 화면의 '부산 전체' 선택과 자연어 입력에서 지역을 말하지 않은 경우 |
| 시간 판단 | 목록에서 빼지 않고 `time_check`로 표시 | 결과 없음 대신 가능한 회차를 안내(UC-003 대안 흐름) |
| `time_options` | 검색·상세 응답에 추가 | 프론트엔드의 하드코딩된 회차 데이터 대체(#16) |
| 상세 `date` 파라미터 | 추가 | 동절기·하절기처럼 기간별로 다른 회차를 보여 줌 |
| `alternatives` | 결과 없음 응답에 추가 | 조건 완화 안내(UC-003) |

### 확인할 내용

| 담당 | 확인할 내용 |
|---|---|
| 김승일 | `time_check`·`time_options`로 시설 목록과 회차 선택 화면을 그릴 수 있는지, `alternatives` 안내 문구 |
| 왕연호 | `district` 컬럼 추가, `license`(이용허락범위) 기록 방법 |
| 김규성 | 자연어 추출에서 지역이 없을 때 `districts: []`(부산 전체)로 넘기는 방식 |
