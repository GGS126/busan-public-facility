import json, sqlite3, tempfile, pathlib, hashlib
from contextlib import closing
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
  assert c.execute('select count(*) from pricing_rules').fetchone()[0]==14
  assert c.execute('select count(*) from facility_discounts').fetchone()[0]==31
 checks=[('busan_haeundae_arboretum_tennis','09:00','11:00',False,0,8000),('busan_haeundae_arboretum_tennis','20:00','22:00',False,0,28000),('busan_haeundae_arboretum_tennis','18:00','20:00',False,80,21200),('busan_samrak_ecopark_tennis','08:00','10:00',False,70,26000),('busan_samrak_ecopark_tennis','08:00','10:00',True,0,9000),('busan_gudeok_stadium_tennis','10:00','11:00',False,0,4000),('busan_gudeok_stadium_tennis','17:00','19:00',False,0,18000),('busan_gudeok_stadium_tennis','18:00','20:00',False,0,28000)]
 for fac,start,end,week,light,expected in checks:
  actual=q.quote(db,fac,'2026-11-09',start,end,week,light)
  assert actual['status']=='priced' and actual['total_won']==expected,(fac,actual,expected)
 before=hashlib.sha256(db.read_bytes()).hexdigest()
 for section,key,bad in [('source','checked_on','2026-13-55'),('reservation','online_open_days_before',-1),('facility','name',''),('rule_set','effective_from','2028-01-01')]:
  mutated=json.loads((R/'seed.json').read_text(encoding='utf-8'))
  mutated[section][key]=bad
  badfile=tmp/'bad.json';badfile.write_text(json.dumps(mutated,ensure_ascii=False))
  try:load.load_many([R/'samrak_winter_2026_2027.json',badfile],db)
  except (ValueError, KeyError, sqlite3.Error):pass
  else:raise AssertionError(f'잘못된 JSON 수락: {section}.{key}')
  assert hashlib.sha256(db.read_bytes()).hexdigest()==before,'실패 후 DB 변경'
 # 회귀 테스트: 같은 시간제 방식의 시설이 추가되어도 기본요금 규칙 ID는 충돌하지 않는다.
 # 서로 다른 2시간 주말요금의 1시간 값이 평일과 구분되어 저장되는지도 확인한다.
 base=json.loads((R/'gudeok_winter_2026_2027.json').read_text(encoding='utf-8'))
 first=json.loads(json.dumps(base,ensure_ascii=False))
 first['pricing']['weekday_fee_won']=8000
 first['pricing']['weekend_holiday_fee_won']=12000
 first['pricing']['hourly_fee_won']=4000
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
 print('PASS: 시간제 시설 2곳 추가 시 PK 충돌 없음, 평일/주말 1시간 요금 분리 확인')
 print('PASS: JSON 3개 재적재, DB 무결성, 요금 계산 8건, 잘못된 JSON 4건 차단 및 DB 원본 보존')
