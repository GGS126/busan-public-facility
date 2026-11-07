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
 print('PASS: JSON 3개 재적재, DB 무결성, 요금 계산 8건, 잘못된 JSON 4건 차단 및 DB 원본 보존')
