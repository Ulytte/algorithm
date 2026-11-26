# -*- coding: utf-8 -*-
"""
식약처 '전국통합식품영양성분정보(가공식품) 표준데이터' 전체 내려받기

- 출처: 공공데이터포털 https://www.data.go.kr/data/15100066/standard.do
  (화면의 파일 다운로드 버튼과 같은 JSON 엔드포인트를 1만 건씩 순서대로 호출)
- 그리드/파일 다운로드는 5만 건 제한이 있어 전체(약 33만 건)를 받기 위해 페이지 단위로 받는다.
- 중간에 끊겨도 이어받을 수 있도록 페이지별 임시 파일을 남기고, 마지막에 CSV 하나로 합친다.

사용법: python scripts/download_mfds.py
출력:   data/mfds/mfds_processed_food.csv (UTF-8 BOM, 한글 컬럼명)
"""
import csv
import json
import os
import time
import urllib.parse
import urllib.request

BASE = os.path.join(os.path.dirname(__file__), "..", "data", "mfds")
PAGE_DIR = os.path.join(BASE, "pages")
OUT = os.path.join(BASE, "mfds_processed_food.csv")
PK = "15100066"
PER_PAGE = 10000
HEADERS = {"User-Agent": "Mozilla/5.0 (student algorithm project)", "X-Requested-With": "XMLHttpRequest",
           "Accept": "application/json"}


def get_json(url, tries=4):
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # 네트워크 오류 시 재시도
            print(f"  재시도 {t + 1}: {e}")
            time.sleep(5 * (t + 1))
    raise RuntimeError(f"실패: {url[:120]}")


def main():
    os.makedirs(PAGE_DIR, exist_ok=True)
    header = get_json(f"https://www.data.go.kr/download/columList.json?pk={PK}&ext=CSV")
    cols = header["tableVO"]["colNmList"]
    code_to_kr = {c["columCode"]: c["columNm"] for c in header["columList"]}
    with open(os.path.join(BASE, "columns.json"), "w", encoding="utf-8") as f:
        json.dump(header["columList"], f, ensure_ascii=False, indent=1)

    page, total = 1, 0
    while True:
        path = os.path.join(PAGE_DIR, f"page_{page:03d}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
        else:
            q = [("colNmList", c) for c in cols] + [
                ("totalCount", header["totalCount"]), ("svcTableNm", header["tableVO"]["svcTableNm"]),
                ("perPage", PER_PAGE), ("page", page)]
            rows = get_json(f"https://www.data.go.kr/download/standard.json?publicDataPk={PK}&" + urllib.parse.urlencode(q))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False)
            time.sleep(1.0)
        if not rows:
            break
        total += len(rows)
        print(f"page {page}: {len(rows)}건 (누적 {total})", flush=True)
        page += 1

    # 하나의 CSV로 합치기 (컬럼 순서는 사이트 정의 순서, 이름은 한글)
    codes = [c["columCode"] for c in header["columList"]]
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([code_to_kr[c] for c in codes])
        for p in range(1, page):
            with open(os.path.join(PAGE_DIR, f"page_{p:03d}.json"), encoding="utf-8") as pf:
                for r in json.load(pf):
                    w.writerow([r.get(c, "") for c in codes])
    print(f"완료: {os.path.abspath(OUT)} ({total}건)")


if __name__ == "__main__":
    main()
