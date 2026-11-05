# API 및 규정 데이터 초안

작성일: 2026-11-05  
상태: 팀 검토용 초안

첫 통합 목표인 **시설 1곳의 ‘직접 조건 입력 → 예상요금과 계산 근거 표시’** 에 필요한 형식을 정리합니다.
김승일과 요청·응답 형식을, 왕연호와 규정 데이터 항목을, 김규성과 AI 조건 형식을 맞추기 위한 문서이며 확정된 명세는 아닙니다.

SDD v0.1의 API-06(3.3절), 핵심 데이터 형식(3.4절), 규칙 엔진 처리 규칙(3.5절)을 기준으로 하며, SDD에 없어 추가하거나 구체화한 내용은 [SDD 대비 추가 제안](#sdd-대비-추가-제안)에 모았습니다.
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
    "headcount": 10,
    "discount_types": ["multi_child"],
    "source": "direct"
  }
}
```

| 항목 | 필수 | 검증 |
|---|---|---|
| `facility_ids` | 예 | 1곳 이상, 등록된 시설 |
| `conditions.sport` | 예 | `GET /api/options`의 종목 |
| `conditions.districts` | 아니요 | 시설 검색(API-02)에서 필수, 이 API의 계산에는 사용하지 않음 |
| `conditions.date` | 예 | 올바른 날짜, 지난 날짜 불가 |
| `conditions.start_time` | 예 | 올바른 시간 |
| `conditions.end_time` | 예 | `start_time`보다 늦은 시간 |
| `conditions.headcount` | 예 | 1 이상의 정수 |
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
        "refund": "기한 내 취소 시 전액 환불"
      },
      "checklist": ["다자녀 가정 확인 서류"],
      "sources": [
        { "source_id": "S-01", "url": "https://example.com/fee-rules", "checked_at": "2026-11-05" },
        { "source_id": "S-02", "url": "https://example.com/discount-rules", "checked_at": "2026-11-05" }
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

### 응답 예시 2: 확인 필요

두 감면의 중복 적용 여부가 공식 자료에서 확인되지 않은 경우입니다.
SDD 3.5절에 따라 합계 대신 계산된 항목과 ‘확인 필요’ 항목을 나눠 반환하고, 사유와 공식 출처 링크를 표시할 수 있게 합니다.

```json
{
  "results": [
    {
      "facility_id": "F001",
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
        "refund": "기한 내 취소 시 전액 환불"
      },
      "checklist": ["다자녀 가정 확인 서류", "장애인 증명 서류"],
      "sources": [
        { "source_id": "S-01", "url": "https://example.com/fee-rules", "checked_at": "2026-11-05" },
        { "source_id": "S-02", "url": "https://example.com/discount-rules", "checked_at": "2026-11-05" }
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

`terms`의 값을 확인하지 못했으면 해당 값을 `null`로 반환합니다.
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

## 규정 데이터 항목

저장 구조와 DB 종류는 이 항목을 기준으로 왕연호와 함께 정합니다.

**모르는 값은 추정해서 채우지 않고 `null`로 둡니다.** 규칙 엔진은 계산에 필요한 값이 `null`이면 `rule_missing`을 반환합니다.

규칙 엔진은 이용 시간을 요금 단위로 나누고, 단위마다 요일·시간대를 판단해 요금을 합산합니다.
조명료는 단위가 시설·계절별 조명 시간대와 겹치면 가산하므로 사용자가 따로 입력하지 않습니다.

### 시설

| 항목 | 설명 | 시기 |
|---|---|---|
| `facility_id`, `name` | 시설 식별자와 이름 | 첫 통합 |
| `sports` | 제공 종목 | 첫 통합 |
| `address`, `district` | 주소와 지역 | 검색 |
| `operating_hours`, `phone` | 운영시간과 연락처 | 검색 |
| `reservation_url` | 공식 예약 링크 | 준비사항 |

### 출처

| 항목 | 설명 | 예시 |
|---|---|---|
| `source_id` | 출처 식별자 | `S-01` |
| `url` | 공식 출처 URL | `https://example.com/fee-rules` |
| `checked_at` | 확인일, 필수 | `2026-11-05` |
| `license` | 데이터 이용조건, 필수 | 공공누리 제1유형 |

### 요금 규정

| 항목 | 설명 | 예시 |
|---|---|---|
| `rule_id` | 규정 식별자 | `R-F001-02` |
| `facility_id`, `sport` | 적용 시설과 종목 | `F001`, `futsal` |
| `type` | 기본요금 또는 조명료 | `base`, `lighting` |
| `amount` | 단위당 금액 | `5000` |
| `unit_minutes` | 요금 단위 시간 | `60` |
| `partial_unit` | 단위 미만 처리 방식 | `round_up` |
| `day_types` | 적용 요일 구분 | `["weekend"]` |
| `time_from`, `time_to` | 적용 시간대, 조명 시간대 | `18:00`, `22:00` |
| `seasons` | 적용 계절, 전체면 `null` | `["winter"]` |
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
| 응답 묶음 | 시설별 결과를 `results` 배열로 반환 | SDD 예시는 시설 1곳의 결과만 표시 |
| 확인 필요 상태 | `needs_review`와 `review_items` 추가 | SDD는 `calculated`만 예시로 제시 |
| `source` 값 | `direct` 추가 | SDD 예시는 `llm`만 제시 |
| 현장 감면 | `method`에 `onsite` 추가 | SDD 예시는 `prepay_refund`만 제시 |
| 오류 응답 | 위의 오류 형식과 코드 | SDD는 오류 형식 통일만 명시 |
| 규정 항목 | `partial_unit`, `rounding`, `seasons` 등 구체화 | SDD 3.5절의 처리 규칙을 데이터로 표현 |

## 담당자별 확인할 내용

### 김승일

1. 응답의 `fee`, `terms`, `checklist`, `sources`로 결과 화면을 그릴 수 있는지
2. 시설명 표시를 위해 응답에 `name`을 넣을지, 시설 검색·상세 결과를 사용할지
3. 금액 항목 표시에 `type` 외의 이름이나 계산식 문구가 필요한지
4. `needs_review`일 때 합계 대신 ‘확인 필요’와 사유를 표시하는 방식이 괜찮은지
5. 입력 오류를 `fields`의 항목별로 표시할 수 있는지

### 왕연호

1. 조사 중인 시설의 규정을 위 항목으로 표현할 수 있는지, 빠진 항목은 없는지
2. 이용일 기준으로 유효한 규정을 조회할 수 있도록 적용 기간을 저장할 수 있는지
3. 감면 유형 코드 목록과 시설 간 공통 사용 가능 여부
4. 시간 단위 외의 요금(인원당, 회당)이나 장비 대여처럼 사용자가 선택하는 요금이 있는지. 있으면 항목과 요청 형식을 추가해야 합니다.
5. 운영시간 밖이나 휴관일 이용, 인원 제한 초과처럼 규정상 이용할 수 없는 경우가 어떻게 안내되어 있는지

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

시설 검색·상세·선택지·체크리스트 API(API-02, 03, 05, 07)는 첫 통합 후 SDD를 바탕으로 이 문서의 형식에 맞춰 구체화합니다.
