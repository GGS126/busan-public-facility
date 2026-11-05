# API 및 규정 데이터 초안

작성일: 2026-11-05  
상태: 팀 검토용 초안

첫 통합 목표인 **시설 1곳의 ‘직접 조건 입력 → 예상요금과 계산 근거 표시’** 에 필요한 형식을 정리합니다.
김승일과 요청·응답 형식을, 왕연호와 규정 데이터 항목을, 김규성과 AI 조건 형식을 맞추기 위한 문서이며 확정된 명세는 아닙니다.

SDD를 확인하지 않고 작성했으므로 경로와 이름은 SDD의 API 초안과 대조해 조정합니다.
**모든 시설명·금액·규정·URL은 형식을 보여 주기 위한 가상 값입니다.** 실제 검증 데이터로 사용하지 않습니다.

## 예상요금 계산 API

```
POST /api/estimates
```

- 형식은 JSON, 이름은 `snake_case`, 금액은 원 단위 정수입니다.
- 날짜는 `YYYY-MM-DD`, 시간은 `HH:MM`이며 한국 시간 기준입니다.
- 계산 결과는 규정상 예상요금이며 실제 예약 가능 여부를 뜻하지 않습니다.

### 요청

```json
{
  "facility_id": "sample-gym-01",
  "conditions": {
    "sport": "badminton",
    "usage_date": "2026-12-12",
    "start_time": "14:00",
    "end_time": "16:00",
    "headcount": 4,
    "discount_types": ["DISABLED"]
  }
}
```

| 항목 | 필수 | 검증 |
|---|---|---|
| `facility_id` | 예 | 등록된 시설 |
| `conditions.sport` | 예 | 시설에서 제공하는 종목 |
| `conditions.usage_date` | 예 | 올바른 날짜 |
| `conditions.start_time` | 예 | 올바른 시간 |
| `conditions.end_time` | 예 | `start_time`보다 늦은 시간 |
| `conditions.headcount` | 예 | 1 이상의 정수 |
| `conditions.discount_types` | 아니요 | 정의된 감면 유형 코드, 없으면 빈 배열 |

`conditions`는 직접 입력과 AI 추출이 함께 쓰는 공통 형식입니다.
AI 추출 조건도 사용자가 확인·수정한 뒤 같은 형식과 검증을 거치므로, AI 없이도 계산이 동작합니다.
지역은 시설 검색에만 필요하므로 이 API에서는 받지 않습니다.
감면은 유형 코드만 받고 증빙 번호 같은 개인정보는 받지 않습니다.

### 응답 상태

규정 누락과 서버 오류를 구분하기 위해, 계산을 끝까지 시도했으면 규정이 부족해도 `200`으로 응답합니다.

| `status` | 의미 | `summary` |
|---|---|---|
| `CONFIRMED` | 모든 항목을 근거가 있는 규정으로 계산 | 금액 표시 |
| `NEEDS_REVIEW` | 규정이 없거나 충돌해 일부 항목을 계산하지 못함 | 모든 금액 `null` |

### 응답 예시 1: 계산 완료

평일·주말 공통 기본요금 시간당 10,000원, 주말 추가요금 시간당 2,000원, 기본요금에만 50% 감면(선결제 후 환급)인 경우입니다.

```json
{
  "status": "CONFIRMED",
  "facility": { "id": "sample-gym-01", "name": "예시 체육관" },
  "summary": {
    "initial_payment": 24000,
    "expected_refund": 10000,
    "final_burden": 14000
  },
  "line_items": [
    {
      "type": "BASE_FEE",
      "label": "기본요금",
      "calculation": "10,000원 × 2시간",
      "amount": 20000,
      "timing": "INITIAL",
      "basis": {
        "rule_id": "fee-base-01",
        "source_url": "https://example.com/fee-rules",
        "checked_at": "2026-11-05"
      }
    },
    {
      "type": "SURCHARGE",
      "label": "주말 추가요금",
      "calculation": "2,000원 × 2시간",
      "amount": 4000,
      "timing": "INITIAL",
      "basis": {
        "rule_id": "fee-weekend-01",
        "source_url": "https://example.com/fee-rules",
        "checked_at": "2026-11-05"
      }
    },
    {
      "type": "DISCOUNT",
      "label": "장애인 감면 (기본요금 50%)",
      "calculation": "20,000원 × 50%",
      "amount": -10000,
      "timing": "REFUND",
      "basis": {
        "rule_id": "discount-disabled-01",
        "source_url": "https://example.com/discount-rules",
        "checked_at": "2026-11-05"
      }
    }
  ],
  "review_items": []
}
```

금액은 `timing` 기준으로 다음과 같이 계산합니다.

| 결과 | 계산 | 예시 |
|---|---|---|
| `initial_payment` (최초 납부액) | `INITIAL` 항목의 합 | 20,000 + 4,000 = 24,000 |
| `expected_refund` (예상 환급액) | `REFUND` 항목의 합의 절댓값 | 10,000 |
| `final_burden` (환급 후 예상 부담액) | 최초 납부액 − 예상 환급액 | 24,000 − 10,000 = 14,000 |

납부 시 바로 깎는 감면은 음수 금액에 `timing: "INITIAL"`로 표현하며, 최초 납부액에 반영됩니다.

### 응답 예시 2: 확인 필요

감면 두 건의 중복 적용 여부가 공식 자료에서 확인되지 않은 경우입니다.
계산된 항목과 근거는 보여 주되, 불완전한 합계를 확정 금액처럼 표시하지 않도록 합계는 `null`로 둡니다.

```json
{
  "status": "NEEDS_REVIEW",
  "facility": { "id": "sample-gym-01", "name": "예시 체육관" },
  "summary": {
    "initial_payment": null,
    "expected_refund": null,
    "final_burden": null
  },
  "line_items": [
    {
      "type": "BASE_FEE",
      "label": "기본요금",
      "calculation": "10,000원 × 2시간",
      "amount": 20000,
      "timing": "INITIAL",
      "basis": {
        "rule_id": "fee-base-01",
        "source_url": "https://example.com/fee-rules",
        "checked_at": "2026-11-05"
      }
    }
  ],
  "review_items": [
    {
      "code": "RULE_MISSING",
      "target": "discount_types",
      "reason": "DISABLED와 MULTI_CHILD 감면의 중복 적용 여부를 확인할 수 없습니다."
    }
  ]
}
```

| `review_items[].code` | 상황 |
|---|---|
| `RULE_MISSING` | 필요한 규정이 없거나 미확인 상태 |
| `RULE_CONFLICT` | 같은 조건에 적용되는 규정이 서로 충돌 |
| `RULE_NOT_IN_EFFECT` | 이용일에 적용되는 규정이 없음 |

### 오류 응답

요청을 처리할 수 없을 때만 오류로 응답합니다.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "입력값을 확인해 주세요.",
    "fields": [
      {
        "field": "conditions.end_time",
        "code": "INVALID_TIME_RANGE",
        "message": "종료 시간은 시작 시간보다 늦어야 합니다."
      }
    ]
  }
}
```

| HTTP 상태 | `code` | 상황 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 필수값 누락, 형식 오류. `fields`에 항목별 오류 반환 |
| 404 | `FACILITY_NOT_FOUND` | 등록되지 않은 시설 |
| 500 | `INTERNAL_ERROR` | 서버 오류. 내부 정보는 응답에 넣지 않음 |

로그에는 API 키와 개인정보를 남기지 않으며, 감면 유형도 개인 정보를 드러낼 수 있으므로 기록하지 않습니다.

## 규정 데이터 항목

첫 통합에는 ‘첫 통합’ 표시 항목이 필요합니다. 저장 구조와 DB 종류는 이 항목을 기준으로 왕연호와 함께 정합니다.

**모르는 값은 추정해서 채우지 않고 `null`로 둡니다.** 규칙 엔진은 계산에 필요한 값이 `null`이면 `RULE_MISSING`을 반환합니다.

### 시설

| 항목 | 설명 | 시기 |
|---|---|---|
| `id`, `name` | 시설 식별자와 이름 | 첫 통합 |
| `sports` | 제공 종목 | 첫 통합 |
| `address`, `region` | 주소와 지역, 검색에 사용 | 검색 |
| `reservation_url` | 공식 예약 링크 | 준비사항 |
| `data_terms` | 데이터 이용조건 | 첫 통합 |

### 요금 규정

| 항목 | 설명 | 예시 |
|---|---|---|
| `id` | 규정 식별자 | `fee-weekend-01` |
| `facility_id`, `sport` | 적용 시설과 종목 | `badminton` |
| `type` | 기본요금 또는 추가요금 | `BASE_FEE`, `SURCHARGE` |
| `unit` | 요금 단위 | `PER_HOUR`, `PER_PERSON`, `PER_SESSION` |
| `amount` | 단위당 금액 | `2000` |
| `day_types` | 적용 요일 구분 | `WEEKEND` |
| `time_from`, `time_to` | 적용 시간대, 전일이면 `null` | `18:00` |
| `effective_from`, `effective_to` | 규정 적용 기간, 종료일이 없으면 `effective_to`는 `null` | `2026-01-01` |
| `source_url`, `checked_at` | 공식 출처와 확인일 | `2026-11-05` |

### 감면 규정

| 항목 | 설명 | 예시 |
|---|---|---|
| `id`, `facility_id` | 규정 식별자와 적용 시설 | `discount-disabled-01` |
| `discount_type` | 감면 유형 코드 | `DISABLED` |
| `rate` 또는 `fixed_amount` | 감면율 또는 감면액 | `0.5` |
| `applies_to` | 감면 대상 요금 | `BASE_FEE` |
| `method` | 납부 시 차감 또는 선결제 후 환급 | `IMMEDIATE`, `REFUND` |
| `stackable` | 다른 감면과 중복 가능 여부, 미확인이면 `null` | `false` |
| `rounding` | 끝전 처리 방식 | `FLOOR_10` |
| `required_documents` | 증빙서류, 준비사항에 사용 | `["복지카드"]` |
| `effective_from`, `effective_to` | 규정 적용 기간 | `2026-01-01` |
| `source_url`, `checked_at` | 공식 출처와 확인일 | `2026-11-05` |

### 예약·취소·환불 규정 (비교 단계)

첫 통합의 계산에는 쓰지 않지만, 시설 조사 때 함께 확인해 두면 다시 조사하지 않아도 됩니다.

| 항목 | 설명 |
|---|---|
| `reservation_opens` | 예약 시작 시점 |
| `cancel_deadline` | 취소 가능 기한 |
| `refund_rules` | 취소 시점별 환불 비율 |
| `restrictions` | 신청 제한과 주의사항 |
| `source_url`, `checked_at` | 공식 출처와 확인일 |

### 계산 검증 사례

왕연호가 작성하는 정답 사례는 다음 형식이면 그대로 자동 테스트로 옮길 수 있습니다.
기본요금, 추가요금, 감면, 선결제 후 환급, 규정 누락을 각각 1건 이상 포함합니다.

| 항목 | 설명 |
|---|---|
| `case_id` | 사례 식별자 |
| `conditions` | 요청의 `conditions`와 같은 형식 |
| `expected_status` | `CONFIRMED` 또는 `NEEDS_REVIEW` |
| `expected_summary` | 최초 납부액, 예상 환급액, 환급 후 예상 부담액 |
| `calculation_note` | 공식 자료 기준 계산 과정 |
| `source_url`, `checked_at` | 공식 출처와 확인일 |

## 담당자별 확인할 내용

### 김승일

1. 응답의 `summary`, `line_items`, `review_items`로 결과 화면을 그릴 수 있는지
2. `NEEDS_REVIEW`일 때 합계 대신 ‘확인 필요’와 사유를 표시하는 방식이 괜찮은지
3. 입력 오류를 `fields`의 항목별로 표시할 수 있는지
4. 종목과 감면 유형 선택지를 화면에 고정할지, 별도 API로 받을지

### 왕연호

1. 조사 중인 시설의 규정을 위 항목으로 표현할 수 있는지, 빠진 항목은 없는지
2. 이용일 기준으로 규정을 조회할 수 있도록 적용 기간을 저장할 수 있는지
3. 감면 유형 코드 목록과 시설 간 공통 사용 가능 여부
4. 조명·장비 대여처럼 사용자가 선택하는 요금이 있는지. 있으면 요청에 선택 항목을 추가해야 합니다.
5. 운영시간 밖이나 휴관일 이용, 인원 제한 초과처럼 규정상 이용할 수 없는 경우가 어떻게 안내되어 있는지

### 김규성

1. AI 추출 결과를 `conditions` 형식으로 만들 수 있는지
2. AI가 추출하지 못한 값을 어떻게 전달할지. 예를 들어 값을 비워 사용자 확인 화면에서 채우게 할지
3. 첫 통합의 실행 환경에 필요한 정보

### 함께 정할 내용

| 항목 | 제안 |
|---|---|
| 이용할 수 없는 조건 | `status`에 `NOT_ELIGIBLE`을 추가하고 사유를 반환 |
| 과거 날짜 | 입력 오류로 처리 |
| 자정을 넘기는 이용 시간 | 첫 통합에서는 입력 오류로 처리 |

시설 검색·상세·비교·준비사항 API는 첫 통합 후 SDD 초안을 바탕으로 이 문서의 형식에 맞춰 추가합니다.
