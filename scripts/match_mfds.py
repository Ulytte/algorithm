# -*- coding: utf-8 -*-
"""
파일럿: CU 상품 ↔ 식약처 '전국통합식품영양성분정보(가공식품)' 자동 매칭률 측정

절차
1) data/raw/cu_products.csv 에서 단백질 관련 후보 상품을 골라 표본(약 100개)을 만든다.
2) 상품명에서 검색 키워드를 만들어 공공데이터포털 표준데이터 조회 화면(가공식품)에 질의한다.
3) 후보 중 상품명 유사도·브랜드·중량을 비교해 가장 그럴듯한 1건을 고르고
   신뢰도(확실/추정/실패)를 부여한다.
4) 매칭된 경우 '1개 기준' 칼로리·단백질을 환산한다 (값 × 식품중량 / 기준량, 단위가 같을 때만).

주의: 이 스크립트의 결과는 '자동 매칭 후보'일 뿐이다.
      최종 데이터셋에는 사람이 확인(포장지 영양성분표 등)한 값만 사용한다.

사용법: python scripts/match_mfds.py
출력:   data/pilot/pilot_sample.csv, data/pilot/pilot_match.csv, data/pilot/pilot_summary.txt
"""
import csv
import difflib
import html
import os
import random
import re
import time
import urllib.parse
import urllib.request

BASE = os.path.join(os.path.dirname(__file__), "..")
CU_PATH = os.path.join(BASE, "data", "raw", "cu_products.csv")
OUT_DIR = os.path.join(BASE, "data", "pilot")
CACHE_DIR = os.path.join(BASE, "data", "cache", "mfds")

QUERY_URL = "https://www.data.go.kr/tcs/dss/selectStdDataDetailView.do"
PUBLIC_DATA_PK = "15100066"  # 전국통합식품영양성분정보(가공식품) 표준데이터
REQUEST_DELAY_SEC = 1.0
SAMPLE_SIZE = 100
SEED = 20261123

# 단백질 관련 후보를 고르는 키워드 (상품명 기준)
PROTEIN_KEYWORDS = ["닭가슴", "닭", "계란", "달걀", "란", "단백", "프로틴", "우유", "두유", "그릭",
                    "요거트", "요구르트", "치즈", "소시지", "햄", "두부", "참치", "연어", "불고기",
                    "제육", "돈까스", "스테이크", "치킨", "콩"]

# 간편식사에서 쓰는 유형 접두어 (브랜드가 아님)
TYPE_PREFIXES = {"도", "김", "샌", "햄", "주", "삼", "빅삼", "면", "샐", "겟모닝", "반", "컵", "튀김", "도너츠"}

# 표 컬럼 위치 (공공데이터포털 조회 화면 기준, 0부터)
COL = {"code": 0, "name": 1, "base": 16, "kcal": 17, "protein": 19,
       "weight": 44, "report_no": 45, "maker": 46, "importer": 47, "distributor": 48}

TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TR_RE = re.compile(r'<tr class="contentsTr">(.*?)</tr>', re.S)
SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l|L|입|개|구)\b", re.I)


# ---------------------------------------------------------------- 표본 추출
def load_cu():
    with open(CU_PATH, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def make_sample(rows):
    """단백질 관련 + 외부 DB 연결 가능성이 있는(88 바코드) 상품 중 무작위 표본."""
    cands = [r for r in rows
             if r["category"] in ("간편식사", "식품", "음료")
             and any(k in r["name"] for k in PROTEIN_KEYWORDS)]
    rnd = random.Random(SEED)
    rnd.shuffle(cands)
    # 카테고리별로 고르게: 간편식사 40, 식품 30, 음료 30 (부족하면 남는 만큼 채움)
    quota = {"간편식사": 40, "식품": 30, "음료": 30}
    sample, used = [], set()
    for r in cands:
        if quota.get(r["category"], 0) > 0:
            sample.append(r); used.add(r["gd_idx"]); quota[r["category"]] -= 1
    for r in cands:
        if len(sample) >= SAMPLE_SIZE:
            break
        if r["gd_idx"] not in used:
            sample.append(r); used.add(r["gd_idx"])
    return sample, len(cands)


# ---------------------------------------------------------------- 이름 정규화
def split_cu_name(name):
    """'빙그레)더단백밤라떼40g' → (prefix='빙그레', core='더단백밤라떼', size=(40,'g'))"""
    prefix, core = "", name
    if ")" in name:
        prefix, core = name.split(")", 1)
    size = None
    m = SIZE_RE.search(core)
    if m:
        size = (float(m.group(1)), m.group(2).lower())
        core = core[:m.start()] + core[m.end():]
    core = re.sub(r"\(.*?\)|[^\w가-힣]", "", core)
    return prefix.strip(), core.strip(), size


def norm(s):
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", s).lower()


def keywords_for(core):
    """검색어 후보: 전체 → 앞 6글자 → 앞 4글자 → 뒤 4글자 (부분일치 검색이므로 점점 짧게)."""
    ks = [core, core[:6], core[:4], core[-4:]]
    out = []
    for k in ks:
        if len(k) >= 2 and k not in out:
            out.append(k)
    return out


# ---------------------------------------------------------------- DB 질의
def query_mfds(keyword):
    """공공데이터포털 조회 화면에 식품명 부분일치 질의 (첫 페이지만, 결과는 캐시)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, norm(keyword) + ".html")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            text = f.read()
    else:
        body = urllib.parse.urlencode({"searchKeyword1": keyword, "publicDataPk": PUBLIC_DATA_PK,
                                       "colCondition": "FOOD_NM"}).encode()
        req = urllib.request.Request(QUERY_URL, data=body, headers={
            "User-Agent": "Mozilla/5.0 (student algorithm project; low-rate)",
            "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=40) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        with open(cache, "w", encoding="utf-8") as f:
            f.write(text)
        time.sleep(REQUEST_DELAY_SEC)
    rows = []
    for tr in TR_RE.findall(text):
        cells = [html.unescape(re.sub(r"<.*?>", "", c)).strip() for c in TD_RE.findall(tr)]
        if len(cells) > COL["distributor"]:
            rows.append({k: cells[i] for k, i in COL.items()})
    return rows


# ---------------------------------------------------------------- 점수/환산
def parse_amount(s):
    """'100g' → (100.0,'g'), '230ml' → (230.0,'ml'), '250ml(g)' → (250.0,'ml')"""
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(kg|g|ml|l)", s or "", re.I)
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2).lower()
    if u == "kg": v, u = v * 1000, "g"
    if u == "l": v, u = v * 1000, "ml"
    return v, u


def score(cu, cand):
    prefix, core, size = cu
    sim = difflib.SequenceMatcher(None, norm(core), norm(cand["name"])).ratio()
    brand_ok = bool(prefix) and prefix not in TYPE_PREFIXES and (
        prefix in cand["name"] or prefix in cand["maker"] or prefix in cand["distributor"])
    weight_ok = False
    w = parse_amount(cand["weight"])
    if size and w:
        sv, su = size
        if su == "kg": sv, su = sv * 1000, "g"
        if su == "l": sv, su = sv * 1000, "ml"
        weight_ok = su == w[1] and abs(sv - w[0]) <= 0.05 * max(sv, 1)
    return sim + (0.15 if brand_ok else 0) + (0.10 if weight_ok else 0), sim, brand_ok, weight_ok


def per_item(cand):
    """1개(포장 1개) 기준 kcal, 단백질. 기준량과 식품중량 단위가 같을 때만 환산."""
    base, weight = parse_amount(cand["base"]), parse_amount(cand["weight"])
    try:
        kcal, prot = float(cand["kcal"]), float(cand["protein"])
    except ValueError:
        return None, None
    if not base or not weight or base[1] != weight[1]:
        return None, None
    f = weight[0] / base[0]
    return round(kcal * f, 1), round(prot * f, 2)


def classify(sim, brand_ok, weight_ok):
    """
    1차 파일럿 수동 검토 결과, 이름만 비슷한 경우 오매칭이 많았다
    (예: 흰우유→흰우유콘(아이스크림), 구운계란3입→1050g 대용량, 진주햄→하림 제품).
    따라서 '확실'은 브랜드와 중량이 모두 일치할 때로 엄격하게 제한한다.
    """
    if sim >= 0.75 and brand_ok and weight_ok:
        return "확실"
    if sim >= 0.85 or (sim >= 0.65 and (brand_ok or weight_ok)):
        return "추정"      # 사람이 포장지로 검증해야 하는 후보
    return "실패"


# ---------------------------------------------------------------- 실행
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    sample, n_cands = make_sample(load_cu())
    results = []
    for i, r in enumerate(sample, 1):
        cu = split_cu_name(r["name"])
        best, used_kw, n_hits = None, "", 0
        for kw in keywords_for(cu[1]):
            cands = query_mfds(kw)
            n_hits = len(cands)
            for c in cands:
                s = score(cu, c)
                if best is None or s[0] > best[0][0]:
                    best, used_kw = (s, c), kw
            if best and classify(*best[0][1:]) == "확실":
                break
        row = {"cu_name": r["name"], "price": r["price"], "category": r["category"],
               "barcode": r["barcode"], "badges": r["badges"], "query": used_kw, "hits_last": n_hits}
        if best:
            (total, sim, b_ok, w_ok), c = best
            kcal, prot = per_item(c)
            row.update(confidence=classify(sim, b_ok, w_ok), similarity=round(sim, 3),
                       brand_ok=b_ok, weight_ok=w_ok, mfds_name=c["name"], mfds_code=c["code"],
                       base=c["base"], weight=c["weight"], kcal_100=c["kcal"], protein_100=c["protein"],
                       kcal_item=kcal, protein_item=prot, maker=c["maker"], distributor=c["distributor"],
                       report_no=c["report_no"])
        else:
            row.update(confidence="실패")
        results.append(row)
        print(f"{i:3d}/{len(sample)} {row['confidence']} {r['name']} -> {row.get('mfds_name', '')}")

    fields = ["cu_name", "price", "category", "barcode", "badges", "confidence", "similarity",
              "brand_ok", "weight_ok", "mfds_name", "mfds_code", "base", "weight", "kcal_100",
              "protein_100", "kcal_item", "protein_item", "maker", "distributor", "report_no",
              "query", "hits_last"]
    with open(os.path.join(OUT_DIR, "pilot_match.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(results)

    # 요약
    lines = [f"단백질 관련 후보 수: {n_cands}", f"표본 수: {len(results)}"]
    for cat in ("간편식사", "식품", "음료", "전체"):
        rs = results if cat == "전체" else [x for x in results if x["category"] == cat]
        if not rs:
            continue
        cnt = {k: sum(1 for x in rs if x["confidence"] == k) for k in ("확실", "추정", "실패")}
        # CU 상품명에 용량이 적혀 있는데 DB 식품중량과 다르면 묶음/다른 규격일 가능성이 높다
        size_conflict = sum(1 for x in rs if x["confidence"] == "추정"
                            and split_cu_name(x["cu_name"])[2] and not x.get("weight_ok"))
        conv = sum(1 for x in rs if x["confidence"] != "실패" and x.get("kcal_item") is not None)
        lines.append(f"[{cat}] n={len(rs)} 확실={cnt['확실']} 추정={cnt['추정']} 실패={cnt['실패']} "
                     f"1개기준 환산가능(확실+추정 중)={conv}")
        lines.append(f"  - 추정 중 CU 표기 용량과 DB 중량 불일치: {size_conflict}")
    with open(os.path.join(OUT_DIR, "pilot_summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
