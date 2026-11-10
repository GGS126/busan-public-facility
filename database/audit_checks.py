import json, sqlite3, tempfile, pathlib, hashlib
from contextlib import closing
from unittest.mock import patch
import load,query_api as q
R=pathlib.Path(__file__).resolve().parent
D=json.loads((R/'seed.json').read_text(encoding='utf-8'))
files=['seed.json','samrak_winter_2026_2027.json','gudeok_winter_2026_2027.json']
with tempfile.TemporaryDirectory() as tmp:
 tmp=pathlib.Path(tmp)
 db=tmp/'facilities.sqlite3'
 load.load_many([R/x for x in files],db)
 with closing(sqlite3.connect(db)) as c:
  assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
  assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
  assert c.execute('select count(*) from facilities').fetchone()[0]==3
  assert c.execute('select count(*) from pricing_rules').fetchone()[0]==13
  assert c.execute('select count(*) from facility_discounts').fetchone()[0]==31
 checks=[('busan_haeundae_arboretum_tennis','09:00','11:00',False,0,8000),('busan_haeundae_arboretum_tennis','20:00','22:00',False,0,28000),('busan_haeundae_arboretum_tennis','18:00','20:00',False,80,21200),('busan_samrak_ecopark_tennis','08:00','10:00',False,70,26000),('busan_samrak_ecopark_tennis','08:00','10:00',True,0,9000),('busan_gudeok_stadium_tennis','17:00','19:00',False,0,18000),('busan_gudeok_stadium_tennis','18:00','20:00',False,0,28000)]
 for fac,start,end,week,light,expected in checks:
  actual=q.quote(db,fac,'2026-11-09',start,end,week,light)
  assert actual['status']=='priced' and actual['total_won']==expected,(fac,actual,expected)
 # 회귀 테스트: quote()가 필수/포함/선택 조명 옵션을 반복 조회하지 않는다.
 # 함수 직접 호출(optional_lighting_quote)은 기존처럼 독립적으로 동작해야 한다.
 original_facility_options=q.facility_options
 for fac,start,end,week,light,expected in checks:
  with patch.object(q,'facility_options',wraps=original_facility_options) as mock_options:
   result=q.quote(db,fac,'2026-11-09',start,end,week,light)
   assert result['total_won']==expected,result
   assert mock_options.call_count==1,(
    f'{fac} {start}~{end}: 옵션 조회 {mock_options.call_count}회 (기대 1회)'
   )
 with patch.object(q,'facility_options',wraps=original_facility_options) as mock_options:
  separate=q.optional_lighting_quote(db,'busan_haeundae_arboretum_tennis','2026-11-09',80)
  assert separate['status']=='priced' and separate['optional_lighting_fee_won']==13200,separate
  assert mock_options.call_count==1,'독립적인 옵션 조회 함수 동작 오류'
 # 공식 근거가 없는 1시간·90분 요금은 금액을 만들지 않고 확인 필요로 응답한다.
 for start,end in [('10:00','11:00'),('10:00','11:30')]:
  missing=q.quote(db,'busan_gudeok_stadium_tennis','2026-11-09',start,end,False)
  assert missing['status']=='needs_review' and missing['total_won'] is None,missing
  assert missing['review_items'][0]['code']=='rule_missing',missing
  assert missing['review_items'][0]['source_url'].startswith('https://reserve.busan.go.kr/'),missing
 assert q.quote(db,'busan_gudeok_stadium_tennis','2026-11-09','10:00','13:00',False)['status']=='invalid_time'
 with closing(sqlite3.connect(db)) as c:
  assert c.execute("SELECT COUNT(*) FROM pricing_rules WHERE rule_set_id='gudeok_tennis_winter_2026_2027' AND duration_minutes=60").fetchone()[0]==0
 before=hashlib.sha256(db.read_bytes()).hexdigest()
 # 잘못된 데이터가 반드시 기대한 검증 오류로 거부되는지 확인한다.
 # 무관한 KeyError/SQLite 오류가 발생하면 검증 성공으로 처리하지 않는다.
 invalid_cases = [
  ('source', 'checked_on', '2026-13-55', 'source.checked_on 날짜 오류'),
  ('reservation', 'online_open_days_before', -1, 'reservation.online_open_days_before 오류'),
  ('facility', 'name', '', 'facility.name 누락'),
  ('rule_set', 'effective_from', '2028-01-01', '규정 적용기간 순서 오류'),
 ]
 for section, key, bad, expected_error in invalid_cases:
  mutated=json.loads((R/'seed.json').read_text(encoding='utf-8'))
  mutated[section][key]=bad
  badfile=tmp/'bad.json'
  badfile.write_text(json.dumps(mutated,ensure_ascii=False),encoding='utf-8')
  try:
   load.load_many([R/'samrak_winter_2026_2027.json',badfile],db)
  except ValueError as exc:
   assert str(exc)==expected_error, (
    f'{section}.{key}: 기대한 검증 오류={expected_error!r}, 실제={str(exc)!r}'
   )
  else:
   raise AssertionError(f'잘못된 JSON 수락: {section}.{key}')
  assert hashlib.sha256(db.read_bytes()).hexdigest()==before, (
   f'{section}.{key}: 실패 후 DB 변경'
  )
 # 회귀 테스트: 같은 시간제 방식의 시설이 추가되어도 기본요금 규칙 ID는 충돌하지 않는다.
 # 서로 다른 2시간 주말요금의 1시간 값이 평일과 구분되어 저장되는지도 확인한다.
 base=json.loads((R/'gudeok_winter_2026_2027.json').read_text(encoding='utf-8'))
 first=json.loads(json.dumps(base,ensure_ascii=False))
 first['pricing']['weekday_fee_won']=8000
 first['pricing']['weekend_holiday_fee_won']=12000
 first['pricing']['hourly_fee_won']=4000
 first['pricing']['hourly_weekend_holiday_fee_won']=6000
 second=json.loads(json.dumps(first,ensure_ascii=False))
 second['facility']['id']='test_other_flexible_facility'
 second['facility']['name']='추가 시간제 시설(테스트 전용)'
 second['source']['id']='test_other_flexible_source'
 second['rule_set']['id']='test_other_flexible_ruleset'
 first_path=tmp/'flexible_first.json'
 second_path=tmp/'flexible_second.json'
 first_path.write_text(json.dumps(first,ensure_ascii=False),encoding='utf-8')
 second_path.write_text(json.dumps(second,ensure_ascii=False),encoding='utf-8')
 extra_db=tmp/'additional_facilities.sqlite3'
 load.load_many([first_path,second_path],extra_db)
 with closing(sqlite3.connect(extra_db)) as c:
  assert c.execute('SELECT COUNT(*) FROM pricing_rules').fetchone()[0]==4
  rows=c.execute('SELECT id,rule_set_id,duration_minutes,weekday_base_won,weekend_holiday_base_won FROM pricing_rules').fetchall()
  assert len({row[0] for row in rows})==4, '시간제 시설 요금 규칙 ID 충돌'
  for row in rows:
   assert row[0].startswith(row[1]+'_'), '규칙 ID가 rule_set ID에서 생성되지 않음'
   if row[2]==60: assert (row[3],row[4])==(4000,6000), row
  assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
 # 회귀 테스트: 규정 ID를 변경하면서 동일 시설 기간을 중복 적재하면 거부한다.
 # 실패한 다중 파일 적재에서는 원본 DB가 바뀌지 않아야 한다.
 for source_file in ('seed.json','gudeok_winter_2026_2027.json'):
  original=json.loads((R/source_file).read_text(encoding='utf-8'))
  same_fac_new_id=json.loads(json.dumps(original,ensure_ascii=False))
  same_fac_new_id['rule_set']['id']=original['rule_set']['id']+'_v2'
  conflicting_file=tmp/('overlap_'+source_file)
  conflicting_file.write_text(json.dumps(same_fac_new_id,ensure_ascii=False),encoding='utf-8')
  pristine_hash=hashlib.sha256(db.read_bytes()).hexdigest()
  try:
   load.load_many([conflicting_file],db)
  except ValueError as exc:
   assert '기간' in str(exc),str(exc)
  else:
   raise AssertionError(f'다른 ID의 중복 적용기간 허용: {source_file}')
  assert hashlib.sha256(db.read_bytes()).hexdigest()==pristine_hash, '실패한 적재가 원본 DB 변경'
  # 같은 규정 ID를 사용하는 정상 재적재는 허용한다.
  load.load_many([R/source_file],db)
  with closing(sqlite3.connect(db)) as c:
   assert c.execute('SELECT COUNT(*) FROM rule_sets WHERE facility_id=?',(original['facility']['id'],)).fetchone()[0]==1
 # 바로 다음 날짜부터 시작하는 기간은 허용하고, 경계일이 겹치면 거부한다.
 import datetime as dt
 original=json.loads((R/'seed.json').read_text(encoding='utf-8'))
 valid_next=json.loads(json.dumps(original,ensure_ascii=False))
 valid_next['rule_set']['id']=original['rule_set']['id']+'_next'
 last_day=dt.date.fromisoformat(original['rule_set']['effective_to'])
 valid_next['rule_set']['effective_from']=(last_day+dt.timedelta(days=1)).isoformat()
 valid_next['rule_set']['effective_to']=(last_day+dt.timedelta(days=31)).isoformat()
 nextfile=tmp/'next_period.json'
 nextfile.write_text(json.dumps(valid_next,ensure_ascii=False),encoding='utf-8')
 extra_db2=tmp/'adjacent_periods.sqlite3'
 load.load_many([R/'seed.json',nextfile],extra_db2)
 with closing(sqlite3.connect(extra_db2)) as c:
  assert c.execute('SELECT COUNT(*) FROM rule_sets').fetchone()[0]==2
 # 같은 파일 배치에 기간이 중복된 다른 ID 두 개를 포함하면 전체 실패.
 batch_db=tmp/'batch_failure.sqlite3'
 hash_before=hashlib.sha256(db.read_bytes()).hexdigest()
 try:load.load_many([R/'gudeok_winter_2026_2027.json',conflicting_file],db)
 except ValueError:pass
 else:raise AssertionError('배치 중복 적재 허용')
 assert hashlib.sha256(db.read_bytes()).hexdigest()==hash_before
 # 회귀 테스트: 구분자 없는 ISO 날짜(YYYYMMDD)도 조회·저장 시 YYYY-MM-DD로 정규화한다.
 fac='busan_haeundae_arboretum_tennis'
 for value in ('20261109', '2026-11-09'):
  assert q.pricing_rules(db,fac,value,False)==q.pricing_rules(db,fac,'2026-11-09',False)
  assert q.discounts(db,fac,value)==q.discounts(db,fac,'2026-11-09')
  assert q.refund_rules(db,fac,value)==q.refund_rules(db,fac,'2026-11-09')
  assert q.facility_options(db,fac,value)==q.facility_options(db,fac,'2026-11-09')
  quote=q.quote(db,fac,value,'09:00','11:00',False)
  assert quote['status']=='priced' and quote['total_won']==8000 and quote['date']=='2026-11-09',quote
 normalized=json.loads((R/'seed.json').read_text(encoding='utf-8'))
 normalized['source']['checked_on']=normalized['source']['checked_on'].replace('-','')
 normalized['rule_set']['effective_from']='20260701'
 normalized['rule_set']['effective_to']='20261231'
 normalized_path=tmp/'date_without_separators.json'
 normalized_path.write_text(json.dumps(normalized,ensure_ascii=False),encoding='utf-8')
 normalized_db=tmp/'normalized_dates.sqlite3'
 load.load_many([normalized_path],normalized_db)
 with closing(sqlite3.connect(normalized_db)) as c:
  assert c.execute('SELECT effective_from,effective_to FROM rule_sets').fetchone()==('2026-07-01','2026-12-31')
  assert c.execute('SELECT checked_on FROM sources').fetchone()[0]==normalized['source']['checked_on'][:4]+'-'+normalized['source']['checked_on'][4:6]+'-'+normalized['source']['checked_on'][6:]
 assert q.quote(normalized_db,fac,'20261109','09:00','11:00',False)['total_won']==8000
 for invalid in ('20261309','not-a-date'):
  try:q.pricing_rules(db,fac,invalid,False)
  except ValueError:pass
  else:raise AssertionError('잘못된 조회 날짜 수락: '+invalid)
 # 회귀 테스트: JSON time_policy의 NULL/최소/최대/단위 값을 하드코딩 없이 저장·조회한다.
 with closing(sqlite3.connect(db)) as c:
  actual=c.execute("SELECT min_minutes,max_minutes,step_minutes,daily_limit_minutes FROM time_selection_policies WHERE rule_set_id=?",(base['rule_set']['id'],)).fetchone()
  assert actual==(None,120,None,120),actual
 flexible=json.loads((R/'gudeok_winter_2026_2027.json').read_text(encoding='utf-8'))
 flexible['time_policy'].update(min_minutes=60,max_minutes=180,step_minutes=30,daily_limit_minutes=180)
 policy_file=tmp/'flexible_30min.json'
 policy_file.write_text(json.dumps(flexible,ensure_ascii=False),encoding='utf-8')
 policy_db=tmp/'policy.sqlite3'
 load.load_many([policy_file],policy_db)
 with closing(sqlite3.connect(policy_db)) as c:
  got=c.execute('SELECT min_minutes,max_minutes,step_minutes,daily_limit_minutes FROM time_selection_policies').fetchone()
  assert got==(60,180,30,180),got
  assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 fac=flexible['facility']['id']
 assert q.quote(policy_db,fac,'2026-11-09','08:30','10:30',False)['total_won']==8000
 assert q.quote(policy_db,fac,'2026-11-09','08:15','10:15',False)['status']=='invalid_time'
 # 3시간 허용 정책이 저장되어도 3시간 가격이 없으므로 요금을 지어내지 않는다.
 assert q.quote(policy_db,fac,'2026-11-09','08:30','11:30',False)['status']!='priced'
 # 최소 이용시간이 90분이면 1시간 요금행이 있어도 선택할 수 없어야 한다.
 flexible['time_policy']['min_minutes']=90
 policy_file.write_text(json.dumps(flexible,ensure_ascii=False),encoding='utf-8')
 load.load_many([policy_file],policy_db)
 assert q.quote(policy_db,fac,'2026-11-09','08:30','09:30',False)['status']=='invalid_time'
 for bad in (0,-30,'30',True):
  flexible['time_policy']['step_minutes']=bad
  policy_file.write_text(json.dumps(flexible,ensure_ascii=False),encoding='utf-8')
  pristine=hashlib.sha256(policy_db.read_bytes()).hexdigest()
  try:load.load_many([policy_file],policy_db)
  except ValueError:pass
  else:raise AssertionError('잘못된 시간 단위 수락: '+repr(bad))
  assert hashlib.sha256(policy_db.read_bytes()).hexdigest()==pristine
 # 복수 감면 자격은 공식 중복 적용 기준이 없으므로 추정 금액을 반환하지 않는다.
 d_fac='busan_haeundae_arboretum_tennis'
 double=q.quote(db,d_fac,'2026-11-09','09:00','11:00',False,
                discount_category_ids=['independence_merit','disabled'])
 assert double['status']=='needs_review',double
 assert double['total_won'] is None and double['discount_won'] is None,double
 assert double['review_items'][0]['code']=='discount_stacking_unverified',double
 assert {rule['percent'] for rule in double['selected_discount_rules']}=={50,60},double
 assert all(rule['source_url'].startswith('https://reserve.busan.go.kr/') for rule in double['selected_discount_rules']),double
 # 동일한 자격 ID를 중복 전달해도 복수 감면으로 오인하지 않는다.
 same=q.quote(db,d_fac,'2026-11-09','09:00','11:00',False,
              discount_category_ids=['disabled','disabled'])
 assert same['status']=='priced' and same['total_won']==8000,same
 # 감면 자격을 전달하지 않은 기존 요금 조회 결과는 그대로 유지한다.
 no_discount=q.quote(db,d_fac,'2026-11-09','09:00','11:00',False)
 assert no_discount['status']=='priced' and no_discount['total_won']==8000,no_discount
 # 해당 시설에 등록되지 않은 자격 ID는 잘못된 입력으로 거부한다.
 try:q.quote(db,d_fac,'2026-11-09','09:00','11:00',False,discount_category_ids=['unknown_discount'])
 except ValueError:pass
 else:raise AssertionError('등록되지 않은 감면 자격을 허용함')
 # 회귀 테스트: 전화번호·선택적 메모가 없는 시설도 양 적재 경로에서 동등하게 처리한다.
 for input_name, mode in [('seed.json', 'fixed'),
                          ('gudeok_winter_2026_2027.json', 'duration')]:
  item=json.loads((R/input_name).read_text(encoding='utf-8'))
  item['facility'].pop('phone', None)
  item['source'].pop('note', None)
  item['reservation'].pop('closure_note', None)
  phone_file=tmp/f'no_phone_{mode}.json'
  phone_file.write_text(json.dumps(item,ensure_ascii=False),encoding='utf-8')
  phone_db=tmp/f'no_phone_{mode}.sqlite3'
  load.load_many([phone_file],phone_db)
  with closing(sqlite3.connect(phone_db)) as c:
   stored=c.execute('SELECT phone FROM facilities WHERE id=?',
                    (item['facility']['id'],)).fetchone()
   assert stored==(None,), (mode,stored)
   source_note=c.execute('SELECT note FROM sources WHERE id=?',
                         (item['source']['id'],)).fetchone()
   assert source_note==(None,), (mode,source_note)
   rid=item['rule_set']['id']
   assert c.execute('SELECT count(*) FROM rule_sets WHERE id=?',(rid,)).fetchone()[0]==1
   assert c.execute('SELECT count(*) FROM refund_rules WHERE rule_set_id=?',(rid,)).fetchone()[0]==len(item['refunds'])
   assert c.execute('SELECT closure_note FROM reservation_rules WHERE rule_set_id=?',(rid,)).fetchone()==(None,)
   assert c.execute('PRAGMA foreign_key_check').fetchall()==[]
 print('PASS: 공통 저장 경로 테스트(고정 회차/시간제), 전화번호·출처 메모 누락 허용, 예약·환불 규정 유지')
 print('PASS: quote() 옵션 조회 호출 1회(필수/포함/선택 조명), 독립 옵션 계산 유지')
 print('PASS: 복수 감면 60%+50%는 needs_review/금액 null/근거 출처 반환, 단일 자격 및 기존 계산 유지')
 print('PASS: JSON 시간 정책 최소/최대/단위 저장, 30분 시작, NULL 보존, 잘못된 값 차단')
 print('PASS: YYYYMMDD 날짜 조회·저장 정규화, 구분자 있는 날짜와 동일 결과, 잘못된 날짜 차단')
 print('PASS: 규정 ID 변경 시 기간 중복 차단(고정회차/시간제), 동일 ID 갱신, 인접 기간, 원본 DB 보존')
 print('PASS: 시간제 시설 2곳 추가 시 PK 충돌 없음, 평일/주말 1시간 요금 분리 확인')
 print('PASS: JSON 3개 재적재, DB 무결성, 확인된 요금 계산 7건 및 미확인 요금 2건 확인 필요, 잘못된 JSON 4건 차단 및 DB 원본 보존')
