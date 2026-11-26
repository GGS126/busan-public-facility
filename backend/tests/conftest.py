import os

# 기존 API 테스트는 가상 데이터(F001 등)를 기준으로 작성됐다. DB 경로는 test_sqlite_api.py에서 따로 검증한다.
# 셸에 RULE_DATA_SOURCE=sqlite가 설정돼 있어도 같은 결과가 나오도록 덮어쓴다.
os.environ["RULE_DATA_SOURCE"] = "sample"
