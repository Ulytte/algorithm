# 편의점 단백질 조합 최적화

운동하는 대학생을 위한 편의점(CU) 식품 조합 최적화. 단백질 ≥ R, 칼로리 C_min~C_max를 만족하는 가장 싼 조합을 Greedy / DP / Branch and Bound로 찾고 비교한다.

Python 3 (3.13.13에서 실행), 외부 라이브러리 없음.

## 폴더

| 폴더 | 내용 |
|---|---|
| algorithms/ | common.py(데이터 읽기·검산), greedy.py, dp.py, bnb.py, planner.py |
| tests/ | test_algorithms.py: 작은 n에서 완전탐색과 비교 |
| scripts/ | 데이터 수집·매칭(collect_cu, download_mfds, match_v2, select_items), 실험(run_experiment), 웹 내보내기(export_web, export_compare, bundle_web) |
| data/ | raw(CU 수집), processed(매칭 결과), selected(실험용 1,315개, 웹용) |
| results/ | 비교 실험 결과(230개 경우) |
| web/ | 웹 앱과 알고리즘 비교 페이지 |
| docs/ | [데이터 처리 과정](docs/데이터_처리_과정.md), [기준값과 근거](docs/기준값_근거.md) |

## 실행

```
python -I tests/test_algorithms.py
python -I scripts/run_experiment.py          # 전체 실험 (수십 분)
python -I scripts/run_experiment.py --quick  # 빠른 확인
python -I scripts/export_compare.py          # 실험 결과 -> web/compare_data.json
python -I scripts/bundle_web.py              # 웹 페이지를 파일 하나로 묶기
```

웹: `web/단백질조합기.html`(앱), `web/알고리즘비교.html`(비교 페이지)을 내려받아 더블클릭하면 바로 열린다.

## 저장소에 없는 것

식약처 원본 DB(data/mfds, data/cache, 약 700MB)는 GitHub 파일 한도(100MB)를 넘어서 올리지 않았다. 다시 만들려면 `python scripts/download_mfds.py`를 실행한다. 매칭 결과는 data/processed와 data/selected에 있어서, 실험과 웹 앱은 원본 없이 돌아간다.
