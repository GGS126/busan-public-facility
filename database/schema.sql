PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS facilities (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, facility_type TEXT NOT NULL,
 address TEXT NOT NULL, phone TEXT, booking_url TEXT NOT NULL,
 open_time TEXT, close_time TEXT,
 holiday_note TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, url TEXT NOT NULL, title TEXT NOT NULL,
 checked_on TEXT, verification_level TEXT NOT NULL CHECK(verification_level IN ('official_page_verified','user_transcribed_official')),
 note TEXT
);
CREATE TABLE IF NOT EXISTS rule_sets (
 id TEXT PRIMARY KEY, facility_id TEXT NOT NULL REFERENCES facilities(id), source_id TEXT NOT NULL REFERENCES sources(id),
 effective_from TEXT NOT NULL, effective_to TEXT NOT NULL, status TEXT NOT NULL CHECK(status = 'confirmed'),
 UNIQUE(facility_id,effective_from,effective_to), CHECK(effective_from<=effective_to)
);
-- 공통 감면대상 분류: 시설과 무관한 고유 코드
CREATE TABLE IF NOT EXISTS discount_categories (
 id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
-- 시설별 규정기간마다 감면율과 적용범위를 별도로 연결
CREATE TABLE IF NOT EXISTS facility_discounts (
 id TEXT PRIMARY KEY,
 rule_set_id TEXT NOT NULL REFERENCES rule_sets(id) ON DELETE CASCADE,
 category_id TEXT NOT NULL REFERENCES discount_categories(id),
 percent INTEGER NOT NULL CHECK(percent BETWEEN 0 AND 100),
 basis TEXT NOT NULL, applies_to TEXT NOT NULL, excluded_from TEXT,
 processing TEXT NOT NULL, documents TEXT, deadline TEXT,
 note TEXT, original_group_label TEXT NOT NULL,
 verification_status TEXT NOT NULL DEFAULT 'official_confirmed' CHECK(verification_status = 'official_confirmed'),
 UNIQUE(rule_set_id, category_id)
);
CREATE INDEX IF NOT EXISTS ix_discount_rule_set ON facility_discounts(rule_set_id, category_id);
CREATE TABLE IF NOT EXISTS refund_rules (
 id TEXT PRIMARY KEY, rule_set_id TEXT NOT NULL REFERENCES rule_sets(id) ON DELETE CASCADE,
 reason TEXT NOT NULL, days_before_min INTEGER, days_before_max INTEGER,
 rate_percent INTEGER CHECK(rate_percent BETWEEN 0 AND 100), channel TEXT NOT NULL,
 condition TEXT, status TEXT NOT NULL CHECK(status = 'confirmed')
);
CREATE TABLE IF NOT EXISTS reservation_rules (
 rule_set_id TEXT PRIMARY KEY REFERENCES rule_sets(id) ON DELETE CASCADE,
 online_open_days_before INTEGER NOT NULL, online_close_days_before INTEGER NOT NULL,
 normal_cancel_online_min_days_before INTEGER NOT NULL,
 closure_note TEXT
);
CREATE INDEX IF NOT EXISTS ix_rules_date ON rule_sets(facility_id,effective_from,effective_to);

CREATE VIEW IF NOT EXISTS v_facility_discounts AS
 SELECT f.id AS facility_id, f.name AS facility_name, r.id AS rule_set_id,
 r.effective_from,r.effective_to,c.id AS category_id,c.name AS category_name,
 d.percent,d.basis,d.applies_to,d.excluded_from,d.processing,d.deadline,
 d.documents,d.note,d.original_group_label,s.url AS source_url,s.checked_on
 FROM facility_discounts d JOIN discount_categories c ON d.category_id=c.id
 JOIN rule_sets r ON r.id=d.rule_set_id JOIN facilities f ON f.id=r.facility_id
 JOIN sources s ON s.id=r.source_id;


-- 고정 회차가 없는 시설: 운영 가능 시간의 세부 범위는 확인 상태로 관리
CREATE TABLE IF NOT EXISTS time_selection_policies (
 rule_set_id TEXT PRIMARY KEY REFERENCES rule_sets(id) ON DELETE CASCADE,
 selection_type TEXT NOT NULL CHECK(selection_type IN ('fixed_slot','flexible_interval')),
 available_start_time TEXT, available_end_time TEXT,
 min_minutes INTEGER, max_minutes INTEGER,
 step_minutes INTEGER,
 daily_limit_minutes INTEGER,
 status TEXT NOT NULL CHECK(status = 'confirmed'),
 note TEXT NOT NULL
);
-- 회차 대신 요금 부과 단위 / 정해진 시간에 대한 공통 요금

-- 공통 요금: 고정 회차는 시작/종료시간 저장, 자유 선택은 이용시간만 저장
CREATE TABLE IF NOT EXISTS pricing_rules (
 id TEXT PRIMARY KEY,
 rule_set_id TEXT NOT NULL REFERENCES rule_sets(id) ON DELETE CASCADE,
 selection_type TEXT NOT NULL CHECK(selection_type IN ('fixed_slot','flexible_interval')),
 slot_no INTEGER,
 start_time TEXT,
 end_time TEXT,
 duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
 weekday_base_won INTEGER NOT NULL CHECK(weekday_base_won >= 0),
 weekend_holiday_base_won INTEGER NOT NULL CHECK(weekend_holiday_base_won >= 0),
 mandatory_light_won INTEGER NOT NULL DEFAULT 0 CHECK(mandatory_light_won >= 0),
 CHECK ((selection_type='fixed_slot' AND slot_no IS NOT NULL AND start_time IS NOT NULL AND end_time IS NOT NULL)
     OR (selection_type='flexible_interval' AND slot_no IS NULL AND start_time IS NULL AND end_time IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pricing_fixed ON pricing_rules(rule_set_id,start_time,end_time) WHERE selection_type='fixed_slot';
CREATE UNIQUE INDEX IF NOT EXISTS ux_pricing_duration ON pricing_rules(rule_set_id,duration_minutes) WHERE selection_type='flexible_interval';
CREATE VIEW IF NOT EXISTS v_slot_prices AS
 SELECT f.name,r.effective_from,r.effective_to,p.slot_no,p.start_time,p.end_time,
 p.weekday_base_won,p.weekend_holiday_base_won,p.mandatory_light_won,
 p.weekday_base_won+p.mandatory_light_won AS weekday_total_won,
 p.weekend_holiday_base_won+p.mandatory_light_won AS weekend_holiday_total_won,
 r.source_id FROM pricing_rules p JOIN rule_sets r ON r.id=p.rule_set_id
 JOIN facilities f ON f.id=r.facility_id WHERE p.selection_type='fixed_slot';

-- 고정회차 시설의 선택 조명료: 지정 단위로 올림 계산

-- 추가 옵션 종류 (장비 대여 등 다른 옵션이 생기면 데이터만 추가)
CREATE TABLE IF NOT EXISTS option_categories (
 id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
-- 시설별 옵션의 계산 규칙; 같은 옵션에도 시설마다 별도 산정 방식 적용
CREATE TABLE IF NOT EXISTS facility_options (
 id TEXT PRIMARY KEY,
 rule_set_id TEXT NOT NULL REFERENCES rule_sets(id) ON DELETE CASCADE,
 option_id TEXT NOT NULL REFERENCES option_categories(id),
 calculation_type TEXT NOT NULL CHECK(calculation_type IN ('hour_blocks_plus_steps','rounded_units','time_overlap_units','flat','per_item')),
 application_type TEXT NOT NULL CHECK(application_type IN ('optional','mandatory_when_applicable','included_in_base_price')),
 rounding_policy TEXT NOT NULL CHECK(rounding_policy IN ('round_up','exact_units','proportional_if_exact')),
 applies_from TEXT, applies_to TEXT,
 note TEXT,
 hour_price INTEGER NOT NULL CHECK(hour_price>=0),
 extra_unit_minutes INTEGER CHECK(extra_unit_minutes>0),
 extra_unit_price INTEGER CHECK(extra_unit_price>=0),
 CHECK((extra_unit_minutes IS NULL AND extra_unit_price IS NULL) OR
       (extra_unit_minutes IS NOT NULL AND extra_unit_price IS NOT NULL)),
 UNIQUE(rule_set_id,option_id,application_type)
);
