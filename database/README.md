# 부산 공공 체육시설 DB 구성 및 저장 내용

이 DB는 부산 공공 체육시설의 **시설 정보, 이용시간, 기본요금, 추가 옵션, 감면, 예약, 환불 규정**을 관리합니다. 시설별 규정은 적용기간 및 출처와 연결되어 있으며, 현재 **테니스장 3곳**의 원본 JSON이 포함되어 있으며, SQLite DB는 아래 방법으로 생성합니다.

## 등록 시설과 시간 선택 방식

| 시설 | 시간 선택 | 기본요금 기준 | 주요 특징 |
| --- | --- | --- | --- |
| 해운대수목원 테니스장 | 지정된 8개 회차 중 선택 | 평일·주말/공휴일 및 회차별 요금 | 20:00~22:00 회차의 필수 조명료는 회차 요금에 포함 |
| 삼락생태공원 테니스장 | 동절기 지정 4개 회차 중 선택 | 평일·주말 및 회차별 요금 | 동절기(2026.10.01~2027.03.31) 기준 |
| 구덕운동장 테니스장 | 08:00~22:00 범위에서 자유 시작, 최대 2시간 | 2시간 8,000원(1시간·90분 요금 확인 필요) | 18:00~22:00 야간 조명료 별도 |

## 주요 테이블과 저장 내용

| 테이블 | 저장 내용 |
| --- | --- |
| `facilities` | 시설명, 종목, 주소, 연락처, 운영시간, 예약 링크 |
| `sources` | 규정의 원본 출처, 확인일 및 확인된 이용허락범위(`license`) |
| `rule_sets` | 시설별 요금·규정 적용기간; 다른 규정 테이블을 연결하는 기준 |
| `pricing_rules` | 고정 회차의 시작·종료시간 및 요금, 자유 시간 선택 시설의 이용시간별 요금 |
| `time_selection_policies` | `fixed_slot`(지정 회차)과 `flexible_interval`(자유 시작시간), 이용시간 제한 |
| `option_categories` | 여러 시설에서 공통으로 쓰는 추가 옵션 종류(현재: 조명) |
| `facility_options` | 시설마다 다른 옵션 적용시간·필수/선택 여부·요금·계산 방식 |
| `discount_categories` | 공통 감면 대상자 분류 12종 |
| `facility_discounts` | 시설별 감면 대상, 감면율, 계산 기준, 조명료 제외 여부, 증빙 조건 |
| `reservation_rules` | 예약 신청 가능일 범위, 온라인 취소 가능 기한, 기존 휴장 안내 원문 |
| `closure_rules` | 규정 적용기간과 출처에 연결된 정기 휴장 규칙(고정 양력일·명절 코드·특정 날짜) |
| `refund_rules` | 취소 사유·이용일 전 취소 시점별 환불률과 반환신청 조건 |

## 시설별 주요 계산 규정

**기본요금:** 해운대수목원과 삼락생태공원은 `pricing_rules`에 저장된 회차와 정확히 일치하는 시간만 이용할 수 있습니다. 구덕운동장은 지정 회차가 없지만, 현재 공식 근거가 확보된 기본요금은 120분(8,000원)만 계산합니다. 60분·90분은 `needs_review`로 처리합니다. 평일·주말/공휴일 금액은 규칙별로 구분되어 있습니다.

**추가 옵션:** `option_categories`에는 옵션 종류만, `facility_options`에는 시설별 계산 규칙을 저장합니다. 현재 조명 규정은 다음과 같습니다.

- **해운대수목원:** 20시 이전 선택 조명 사용은 60분 10,000원과 추가 10분당 1,600원 기준. 20:00~22:00 회차의 필수 조명료 20,000원은 기본 회차 총요금에 포함되므로 중복 부과하지 않습니다.
- **삼락생태공원:** 조명 사용시간을 60분 단위로 올림하여 시간당 10,000원 적용.
- **구덕운동장:** 동절기 18:00~22:00 중 이용시간과 겹치는 야간 시간에 시간당 10,000원 적용.

**감면:** 세 테니스장은 모두 감면 대상 **개별 이용자 인원에 비례**해 기본 코트 이용료를 감면하도록 정리했습니다. 해운대수목원·삼락생태공원은 공식 계산 예시로 확인되었으며, 구덕운동장은 공식 안내의 감면 대상 이용자별 적용 및 대표 예약자 환급 문구와 사용자가 확인한 동일한 계산 방식에 따라 반영했습니다. 삼락의 공식 예시는 **평일 6,000원·4명 중 2명 감면 → 1인당 750원, 총 1,500원 반환**입니다. 해운대수목원 독립유공자 관련 감면율은 60%, 해당 시설의 다른 등록 대상은 50%입니다. 구덕은 환급금을 **대표 예약자에게 지급**하지만, 감면 적용 대상은 실제 감면 자격이 있는 이용자입니다. 세 시설 모두 조명료는 감면 대상에서 제외합니다. 세 시설의 원 미만 끝전 처리 기준은 여전히 미확인입니다.

**감면 끝전 처리 미확인:** 세 시설의 `discount_common.rounding_policy`는 모두 `null`이며, `facility_discounts.discount_rounding_policy`로 저장합니다. 공식 반올림/절사 기준이 미확인이라는 뜻이며 조명료 옵션의 `rounding_policy`와는 별개입니다. `query_api.discounts()`는 `rounding_status: unverified`를 반환합니다. `discount_proration_check(...)`는 세 시설 모두 **인원별 감면액에 원 미만이 생길 때** `needs_review`와 환급액 `null`을 반환합니다. 인원별 감면액이 정확한 정수인 사례는 감면액을 계산합니다. 예를 들어 구덕 8,000원·4명 중 1명 50% 감면은 1,000원 반환입니다. 예약 차단이나 HTTP 오류 응답은 이 DB의 책임이 아닙니다.

**환불:** 시설별 일반 취소 시점에 따른 환불률과 우천 등 별도 사유에 대한 규정은 `refund_rules`에 저장합니다. 같은 시설이라도 취소 사유에 따라 적용 규칙이 달라질 수 있습니다.

## 데이터 구성 원칙

- 요금과 규정은 `rule_set_id`를 통해 **시설·적용기간·출처**에 연결됩니다.
- **기본요금**, **추가 옵션 요금**, **감면액**, **환불액**을 서로 다른 규정으로 구분하여 저장합니다.
- 실제 예약 잔여 자리나 실시간 예약 확정 정보는 이 DB의 저장 범위에 포함되지 않습니다.

## 규정 누락 처리

공식 자료에서 확인되지 않은 1시간·90분 기본요금은 임의로 2시간 요금에서 환산하지 않는다. 미확인 요금 행은 생성하지 않고 조회 결과에서 `needs_review`와 `rule_missing`, 사유, 공식 출처를 반환한다. 금액 합계는 `null`이다. 시설별 실제 예약 가능 여부는 공식 예약 시스템에서 확인해야 한다.

## 복수 감면 자격의 미확인 규정 처리

한 이용자가 같은 시설의 감면 자격을 두 개 이상 선택했을 때 중복 적용 방식이 공식 자료로 확인되지 않았다면, 감면율을 합산하거나 높은 감면율 하나를 임의 선택하지 않습니다. `query_api.quote(..., discount_category_ids=['independence_merit', 'disabled'])`는 `needs_review` 및 `discount_stacking_unverified` 사유, 선택한 감면 대상별 감면율과 출처를 반환하고, 확정 계산 금액(`total_won`, `discount_won` 등)은 `null`로 둡니다.

이는 **복수 감면 자격에 관한 처리 보류**로, 단일 감면을 실제 결제금액에 적용한다는 의미는 아닙니다. 기존 `quote()`는 기본요금·조명료를 계산하며 단일 감면 환급액 계산은 별도 규칙 엔진에서 처리해야 합니다. DB에 기록된 개별 감면율은 변경하지 않았습니다.

## SQLite DB 생성 및 검증

시설별 JSON(`seed.json`, `samrak_winter_2026_2027.json`, `gudeok_winter_2026_2027.json`)을 **검토 가능한 원본 데이터**로 관리합니다. `facilities.sqlite3`는 이 자료와 `schema.sql`에서 생성되는 결과물이므로 Git에는 포함하지 않습니다.

프로젝트 루트에서 다음 명령으로 DB를 새로 생성할 수 있습니다.

```bash
python database/build_db.py
python database/audit_checks.py
```

`build_db.py`는 기존 DB를 바탕으로 누적하지 않고 **새 임시 DB에 전체 JSON을 적재·검증한 후 성공할 때에만** `database/facilities.sqlite3`를 교체합니다. 기존 파일이 다른 프로그램에서 열려 있으면 먼저 연결을 닫으세요.

새로운 시설을 추가한 경우 해당 JSON을 목록에 포함하도록 `build_db.py`의 `DEFAULT_FILES`를 갱신하거나, 다음과 같이 모든 파일을 명시합니다.

```bash
python database/build_db.py --data database/seed.json database/samrak_winter_2026_2027.json database/gudeok_winter_2026_2027.json
```

`database/.gitignore`는 생성된 SQLite 파일과 Python 임시 파일을 새로 커밋하지 않도록 합니다. **이미 Git에 올라간 `facilities.sqlite3`와 중복 `README_database_content.md`는 GitHub 브랜치에서 별도로 삭제 커밋해야 합니다.**

## 구·군 정보 (`district`)

`facilities.district`는 시설별 구·군 이름을 저장하며, 시설 목록 조회(`query_api.facilities`)에도 포함됩니다. 현재 등록된 값은 해운대수목원 `해운대구`, 삼락생태공원 `사상구`, 구덕운동장 `서구`입니다. 신규 시설 JSON의 `facility.district`는 필수이며 비어 있으면 적재를 거부합니다.

## 정기 휴장일 구조화 (`closure_rules`)

시설 JSON의 `closure_rules`를 공통 테이블에 저장합니다. 기존 `holiday_note` 및
`reservation.closure_note`의 원문도 보존합니다. 코드 유형은 다음과 같습니다.

- `annual_date`: 매년 같은 **양력** 날짜 `MM-DD` (예: `01-01`)
- `holiday_code`: `lunar_new_year_day`(설날 당일), `chuseok_day`(추석 당일)
- `exact_date`: 공식 근거로 확인된 날짜 `YYYY-MM-DD` (해당 규정 적용기간 안에서만 허용)

| 시설 | 구조화된 정기 휴장 규칙 |
| --- | --- |
| 해운대수목원 테니스장 | `01-01`(양력), `lunar_new_year_day`, `chuseok_day` |
| 삼락생태공원 테니스장 | `lunar_new_year_day`, `chuseok_day` |
| 구덕운동장 테니스장 | 정기 휴장 없음(`[]`); 명절 등 별도 공지는 따로 확인 필요 |

원본 규정의 **설·추석 '당일'**과 연휴·대체공휴일은 다릅니다. 명절 코드를
임의로 특정 날짜에 대응시키지 않았습니다. 백엔드가 검증된 한국 공휴일/음력 날짜
자료에서 이용일의 `holiday_codes`를 조회하여 전달해야 합니다.

```python
from database import query_api  # 프로젝트 루트에서 사용할 경우
rules = query_api.closure_rules(db_path, facility_id, '2026-11-09')
result = query_api.closure_status(db_path, facility_id, '2026-11-09',
                                  holiday_codes=['lunar_new_year_day'])
```

- `closure_status()`의 `holiday_codes=None`은 **명절 여부 미확인**을 뜻합니다.
  명절 휴장 규칙이 있으면 `needs_calendar_resolution`, `is_closed=None`으로
  확정을 보류합니다. 백엔드에서 명절 여부를 판정했으면 명절이 아닌 날은 `[]`을 넘깁니다.
- `closed`는 정기 휴장 규칙에 일치한 경우, `no_scheduled_closure`는 해당
  규정에 등록된 **정기 휴장 규칙에 해당하지 않는 경우**입니다.
  `no_scheduled_closure`를 실제 예약 가능/확정과 동일시하면 안 됩니다.
- 사용일에 유효한 규정기간이 없으면 `no_active_rule_set`을 반환합니다.
- 임시 행사·시설 보수·별도 통제 등 수시 공지는 포함하지 않습니다.
- 기존 요금 계산 `quote()`는 호환성을 위해 그대로 유지됩니다. 백엔드가
  예약 가능 여부를 안내하기 전에 휴장 판정을 별도로 호출해야 합니다.

## 출처 이용허락범위 (`sources.license`, NFR-006)

원본 JSON의 `source.license`와 SQLite `sources.license`에 이용허락조건을 저장합니다.
공식적으로 확인되지 않은 경우 **문자열 `"미확인"`을 넣지 않고 JSON `null` / SQLite `NULL`로 유지**합니다.
현재 세 시설의 공식 출처 재이용 조건은 검증된 값이 없어 전부 `null`입니다.
출처가 공식 페이지라는 사실은 데이터 재사용 허락이 있다는 뜻이 아닙니다.

`query_api.sources(db_path)` 또는 `query_api.sources(db_path, facility_id, use_date)`로 조회하면
`source_id`, `url`, `title`, `checked_on`, `verification_level`, `license`, `license_status`, `note`를 반환합니다.
`license_status`는 `unverified`(NULL) 또는 `confirmed`(문자열 기재)입니다.
미확인인 경우 API에서는 `license: null`과 `license_status: unverified`로 안내하고,
명시적인 이용 허락으로 해석하지 않습니다. 확인 자료를 확보한 뒤에만 실제 라이선스 문구를 입력합니다.

기존 DB에는 열이 없으므로 JSON 수정 후 `python database/build_db.py`로 **새로 생성**해야 합니다.
