# -*- coding: utf-8 -*-
"""
매칭 v2: CU 상품 ↔ 식약처 가공식품 영양DB(전체, 로컬 CSV)

파일럿(v1)에서 확인된 오매칭 원인을 규칙으로 반영한다.
  1) 다른 제조사 제품과 연결  → CU 브랜드 접두어를 제조사/유통사/상품명에서 확인 (브랜드 사전)
  2) 묶음·다른 용량과 연결     → CU 표기 용량과 DB 식품중량 비교. 같은 제품 다른 용량이면
                                  100g(ml)당 값 × CU 용량으로 환산 ('용량환산')
  3) 다른 종류 제품과 연결     → CU 카테고리와 DB 식품대분류가 충돌하면 감점 (예: 음료 ↔ 빙과)
  4) 값 자체의 오류            → 열량 ≈ 4×단백질 + 4×탄수화물 + 9×지방 검산, 어긋나면 등급 하향
  5) 검색 1페이지 제한         → 전체 DB를 내려받아 로컬에서 바이그램 색인으로 후보 검색

등급
  A  : 이름 유사 + (브랜드 일치 또는 브랜드 없는 상품이면 이름 거의 동일) + 용량 일치
  B  : 이름 유사 + 브랜드 일치, 용량은 다르지만 100g(ml)당 값으로 CU 용량에 맞춰 환산
  B- : 이름 유사 + 브랜드 문제 없음, CU 상품명에 용량이 없어 DB 중량을 그대로 사용 (같은 규격 가정)
  C  : 후보만 있음 (값은 참고용, 실험에 쓰지 않음)
  F  : 후보 없음
실험 데이터에는 A, B 를 우선 쓰고 B- 는 포장지 확인 후 사용하는 것을 제안한다.

사용법: python scripts/match_v2.py
입력:   data/raw/cu_products.csv, data/mfds/mfds_processed_food.csv
출력:   data/processed/cu_nutrition_v2.csv, data/processed/cu_nutrition_v2_summary.txt
"""
import collections
import csv
import difflib
import os
import re

BASE = os.path.join(os.path.dirname(__file__), "..")
CU_PATH = os.path.join(BASE, "data", "raw", "cu_products.csv")
DB_PATH = os.path.join(BASE, "data", "mfds", "mfds_processed_food.csv")
OUT_DIR = os.path.join(BASE, "data", "processed")

# 영양성분 컬럼 (DB 한글 컬럼명 → 출력 이름)
NUTRIENTS = [
    ("에너지(kcal)", "kcal"), ("단백질(g)", "protein_g"), ("지방(g)", "fat_g"), ("탄수화물(g)", "carb_g"),
    ("당류(g)", "sugar_g"), ("식이섬유(g)", "fiber_g"), ("나트륨(mg)", "sodium_mg"), ("포화지방산(g)", "satfat_g"),
    ("트랜스지방산(g)", "transfat_g"), ("콜레스테롤(mg)", "cholesterol_mg"), ("칼슘(mg)", "calcium_mg"),
]
DB_KEEP = ["식품코드", "식품명", "식품대분류명", "대표식품명", "영양성분함량기준량", "식품중량", "품목제조보고번호",
           "제조사명", "수입업체명", "유통업체명", "데이터생성일자"] + [k for k, _ in NUTRIENTS]

# CU 상품명 접두어 → DB 제조사/유통사/상품명에서 찾을 문자열 (브랜드 사전, 필요하면 추가)
BGF = ["비지에프", "bgf", "씨유"]
BRAND_ALIASES = {
    "서울": ["서울우유"], "서울F&B": ["서울에프엔비", "서울f&b"], "서울FB": ["서울에프엔비", "서울f&b"],
    "매일": ["매일유업", "매일"], "상하": ["매일유업", "상하"], "남양": ["남양유업", "남양"], "빙그레": ["빙그레"],
    "동원": ["동원"], "CJ": ["씨제이", "cj"], "비비고": ["씨제이", "cj"], "풀무원": ["풀무원"], "풀": ["풀무원"],
    "오뚜기": ["오뚜기"], "하림": ["하림"], "진주햄": ["진주햄"], "롯데": ["롯데"], "삼양": ["삼양"],
    "농심": ["농심"], "정식품": ["정식품"], "연세": ["연세"], "사조": ["사조"], "목우촌": ["목우촌"],
    "대상": ["대상"], "청정원": ["대상"], "해태": ["해태"], "오리온": ["오리온"], "크라운": ["크라운"],
    "팔도": ["팔도"], "삼립": ["삼립", "에스피씨"], "동서": ["동서"], "아워홈": ["아워홈"], "신세계": ["신세계"],
    "hy": ["에치와이", "hy", "한국야쿠르트"], "코카콜라": ["코카콜라"], "롯데칠성": ["롯데칠성"], "광동": ["광동"],
    "웅진": ["웅진"], "동아": ["동아오츠카"], "샘표": ["샘표"], "베지밀": ["정식품"], "닥터유": ["오리온"],
    "하이뮨": ["일동"], "테이크핏": ["남양"], "얼티브": ["씨제이", "cj"], "덴마크": ["동원"],
    "득템": BGF, "PBICK": BGF, "헤이루": BGF, "HEYROO": BGF, "del": BGF, "delaffe": BGF, "델라페": BGF,
}
# 간편식사의 유형 접두어 (브랜드가 아님)
TYPE_PREFIXES = {"도", "김", "샌", "햄", "주", "삼", "빅삼", "면", "샐", "겟모닝", "반", "컵", "튀김", "도너츠",
                 "빵", "떡", "죽", "국", "밥", "샐러드"}
# CU 카테고리와 충돌하는 DB 식품대분류 키워드
CATEGORY_CONFLICT = {
    "음료": ["빙과", "과자", "빵"], "간편식사": ["빙과", "음료"], "아이스크림": ["음료류", "즉석"],
    "과자류": ["음료", "빙과"],
}

UNIT_RE = r"(kg|g|ml|l|L|ML|G)"
SIZE_RE = re.compile(r"P?(\d+(?:\.\d+)?)\s*" + UNIT_RE + r"(?![a-zA-Z])")
# '99.9팩'의 '9팩'처럼 숫자 일부를 개수로 읽지 않도록 앞에 숫자·점이 없을 때만 인정 ('팩'은 용기 표기라 제외)
COUNT_RE = re.compile(r"(?<![\d.])(\d+)\s*(입|구|개입|매입|매|봉|T|개)")
MULT_RE = re.compile(r"\*\s*(\d+)\s*(입|개|팩|구|봉)?")
# 브랜드 약칭 → 실제 이름 (확신이 낮아 필수 조건이 아닌 가점용)
SOFT_ALIASES = {
    "코카": ["코카콜라"], "하겐": ["하겐다즈"], "스벅": ["스타벅스"], "티오피": ["티오피", "동서"],
    "이디야": ["이디야"], "켈로그": ["켈로그"], "프링글스": ["프링글스"], "라라스윗": ["라라스윗"],
    "서주": ["서주"], "마즈": ["마즈", "mars"], "고래사": ["고래사", "늘푸른바다"], "바프": ["바프"],
    "머거본": ["머거본"], "담터": ["담터"], "칠갑": ["칠갑"], "하이트": ["하이트"], "풍림": ["풍림"],
}
TAIL_NUM_RE = re.compile(r"(\d{2,4})$")


def norm(s):
    return re.sub(r"[^0-9a-z가-힣]", "", (s or "").lower())


def to_base_unit(v, u):
    u = u.lower()
    if u == "kg": return v * 1000, "g"
    if u == "l": return v * 1000, "ml"
    return v, u


def parse_amount(s):
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(kg|g|ml|l)", (s or "").lower())
    return to_base_unit(float(m.group(1)), m.group(2)) if m else None


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ CU 이름 분석
def parse_cu(name, category):
    prefix, core = ("", name)
    if ")" in name:
        prefix, core = name.split(")", 1)
    prefix = prefix.strip()
    size = count = None
    m = SIZE_RE.search(core)
    if m:
        size = to_base_unit(float(m.group(1)), m.group(2))
        core = core[:m.start()] + " " + core[m.end():]
    mm = MULT_RE.search(core)
    if mm:
        count = int(mm.group(1)); core = core[:mm.start()] + core[mm.end():]
    mc = COUNT_RE.search(core)
    if mc:
        count = int(mc.group(1)); core = core[:mc.start()] + core[mc.end():]
    core = re.sub(r"\((냉동|팩|박스|병|캔|PET|봉)\)", "", core)
    core_n = re.sub(r"(캔|병|팩|pet)$", "", norm(core))   # 끝에 붙은 용기 표기 제거
    if size is None:  # '참치김치볶음밥230' 처럼 단위 없이 끝나는 숫자
        mt = TAIL_NUM_RE.search(core_n)
        if mt and int(mt.group(1)) >= 50:
            v = float(mt.group(1)); size = (v, "ml" if category == "음료" else "g"); core_n = core_n[:mt.start()]
    if prefix in TYPE_PREFIXES:
        brand_kind, aliases = "type", []
    elif prefix in BRAND_ALIASES:
        brand_kind, aliases = "known", BRAND_ALIASES[prefix]
    elif prefix:
        brand_kind, aliases = "other", [norm(prefix)] + SOFT_ALIASES.get(prefix, [])
    else:
        brand_kind, aliases = "none", []
    # CU 상품명은 약 12자에서 잘리는 경우가 많다. 잘린 이름이면 DB 이름이 더 길어도 감점하지 않는다.
    truncated = len(name) >= 12
    return {"prefix": prefix, "core": core_n, "size": size, "count": count, "truncated": truncated,
            "brand_kind": brand_kind, "aliases": [norm(a) for a in aliases]}


# ------------------------------------------------------------------ DB 적재와 색인
def load_db():
    rows = []
    with open(DB_PATH, encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for d in r:
            rows.append(tuple(d.get(k, "") for k in DB_KEEP))
    return rows


F = {k: i for i, k in enumerate(DB_KEEP)}


def build_index(rows):
    names = [norm(r[F["식품명"]]) for r in rows]
    who = [norm(r[F["제조사명"]] + r[F["유통업체명"]] + r[F["수입업체명"]]) for r in rows]
    index = collections.defaultdict(list)
    for i, n in enumerate(names):
        for bg in set(n[j:j + 2] for j in range(len(n) - 1)):
            index[bg].append(i)
    # 브랜드 색인: 브랜드 문자열이 상품명·제조사·유통사·수입사에 들어 있는 행
    brand_rows = {}
    all_aliases = {norm(a) for v in list(BRAND_ALIASES.values()) + list(SOFT_ALIASES.values()) for a in v}
    for a in all_aliases:
        brand_rows[a] = {i for i in range(len(rows)) if a in names[i] or a in who[i]}
    return names, who, index, brand_rows


def candidates(cu, names, index, brand_rows, limit=150):
    """바이그램 겹침이 많은 순으로 후보를 고른다. 브랜드를 아는 상품은 그 브랜드 행 안에서 먼저 찾는다."""
    q = cu["core"]
    grams = set(q[j:j + 2] for j in range(len(q) - 1)) or {q}
    cnt = collections.Counter()
    for g in grams:
        lst = index.get(g)
        if lst and len(lst) < 60000:   # 너무 흔한 바이그램은 건너뜀
            cnt.update(lst)
    pool = set()
    for a in cu["aliases"]:
        pool |= brand_rows.get(a, set())
    out = []
    if pool:
        out = [i for i, _ in sorted(((i, c) for i, c in cnt.items() if i in pool), key=lambda x: -x[1])[:limit]]
    seen = set(out)
    out += [i for i, _ in cnt.most_common(limit) if i not in seen]
    return out


# ------------------------------------------------------------------ 점수
def name_similarity(cu_core, db_name_n, aliases, truncated):
    """
    두 가지 유사도 중 큰 값을 쓴다.
      - 순서 유사도: 글자 순서까지 맞는 부분 (difflib)
      - 글자 구성 유사도: 순서 무시 (예: '더단백초코드링크' ↔ '더단백드링크초코'), 0.9배로 낮춰 반영
    CU 이름이 잘리지 않았는데 DB 이름에 글자가 더 있으면(맛·종류 차이) 남는 글자 수만큼 감점한다.
      예: '맛있는우유' ↔ '맛있는우유초코', '참치김치볶음밥' ↔ '참치김치치즈볶음밥'
    """
    d = db_name_n
    for a in aliases:              # DB 상품명 앞의 브랜드 단어는 비교에서 제외
        if a and a in d:
            d = d.replace(a, "", 1)
    d = re.sub(r"\d+(\.\d+)?(kg|g|ml|l)", "", d)
    if not cu_core or not d:
        return 0.0
    w_cov = 0.65 if truncated else 0.5
    sm = difflib.SequenceMatcher(None, cu_core, d, autojunk=False)
    matched = sum(b.size for b in sm.get_matching_blocks())
    seq = w_cov * matched / len(cu_core) + (1 - w_cov) * matched / len(d)
    common = sum((collections.Counter(cu_core) & collections.Counter(d)).values())
    bag = 0.9 * (w_cov * common / len(cu_core) + (1 - w_cov) * common / len(d))
    sim = max(seq, bag)
    if not truncated:
        extra = len(d) - max(matched, common)
        if extra >= 2:
            sim -= 0.05 * extra
    return sim


def evaluate(cu, category, row, name_n, who_n):
    sim = name_similarity(cu["core"], name_n, cu["aliases"], cu["truncated"])
    text = name_n + who_n
    brand_ok = any(a and a in text for a in cu["aliases"])
    conflict = any(k in row[F["식품대분류명"]] for k in CATEGORY_CONFLICT.get(category, []))
    w = parse_amount(row[F["식품중량"]])
    size_rel = "unknown"
    if cu["size"] and w:
        cv, cu_unit = cu["size"]
        if cu_unit == w[1] or {cu_unit, w[1]} == {"g", "ml"}:
            # '200g*3입'처럼 묶음이면 낱개 용량 또는 묶음 전체 용량 중 하나와 같으면 일치로 본다
            totals = [cv] + ([cv * cu["count"]] if cu["count"] else [])
            size_rel = "same" if any(abs(t - w[0]) <= 0.03 * max(t, 1) for t in totals) else "diff"
    score = sim + (0.12 if brand_ok else 0) + (0.08 if size_rel == "same" else 0) - (0.3 if conflict else 0)
    return {"sim": sim, "brand_ok": brand_ok, "conflict": conflict, "size_rel": size_rel, "score": score}


def atwater_ok(row):
    k, p, c, f = (num(row[F[x]]) for x in ("에너지(kcal)", "단백질(g)", "탄수화물(g)", "지방(g)"))
    if None in (k, p, c, f) or k < 20:
        return None
    est = 4 * p + 4 * c + 9 * f
    return abs(est - k) <= max(0.30 * k, 15)


def grade(cu, ev, row):
    sim, b_ok = ev["sim"], ev["brand_ok"]
    brand_fine = b_ok or cu["brand_kind"] in ("type", "none", "other")
    if ev["conflict"] or sim < 0.75:
        return "C" if sim >= 0.6 else "F"
    if cu["brand_kind"] == "known" and not b_ok:
        return "C"
    exactish = sim >= 0.95
    if ev["size_rel"] == "same" and sim >= 0.85 and (b_ok or exactish):
        g = "A"
    elif ev["size_rel"] == "diff" and sim >= 0.85 and b_ok:
        g = "B"
    elif (ev["size_rel"] == "unknown" and sim >= 0.9 and brand_fine and cu["count"] is None
          and (parse_amount(row[F["식품중량"]]) or (0, ""))[0] <= 1000):
        g = "B-"   # DB 식품중량이 1kg(1L) 넘으면 업소용·대용량 규격일 가능성이 높아 제외
    else:
        g = "C"
    if g != "C" and atwater_ok(row) is False:   # 열량 검산 실패 시 한 단계 낮춤
        g = {"A": "B-", "B": "C", "B-": "C"}[g]
    return g


def per_item(cu, row, g):
    """
    CU 판매단위 1개 기준 영양값.
    CU 상품명에 용량이 있으면 'DB의 100g(ml)당 값 × CU 판매 용량'(묶음이면 × 개수)으로,
    없으면 DB 식품중량(같은 규격이라고 가정)으로 환산한다.
    """
    base = parse_amount(row[F["영양성분함량기준량"]])
    if not base:
        return None, ""
    if cu["size"]:
        v, u = cu["size"]
        amount, how = (v * (cu["count"] or 1), u), "CU용량" + (f"×{cu['count']}입" if cu["count"] else "")
    else:
        amount, how = parse_amount(row[F["식품중량"]]), "DB식품중량"
    if not amount:
        return None, ""
    if amount[1] != base[1] and {amount[1], base[1]} != {"g", "ml"}:
        return None, ""
    if amount[1] != base[1]:
        how += "(ml≈g)"
    factor = amount[0] / base[0]
    vals = {}
    for k, out in NUTRIENTS:
        v = num(row[F[k]])
        vals[out] = round(v * factor, 2) if v is not None else ""
    return vals, how


# ------------------------------------------------------------------ 실행
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("DB 적재 중...", flush=True)
    rows = load_db()
    names, who, index, brand_rows = build_index(rows)
    print(f"DB {len(rows)}건, 색인 완료", flush=True)

    with open(CU_PATH, encoding="utf-8-sig") as f:
        cu_rows = list(csv.DictReader(f))

    out = []
    for n_i, r in enumerate(cu_rows, 1):
        cu = parse_cu(r["name"], r["category"])
        best = None
        if r["category"] != "즉석조리" and cu["core"]:
            for i in candidates(cu, names, index, brand_rows):
                ev = evaluate(cu, r["category"], rows[i], names[i], who[i])
                key = (ev["score"], rows[i][F["데이터생성일자"]])
                if best is None or key > best[0]:
                    best = (key, i, ev)
        rec = {"cu_name": r["name"], "category": r["category"], "price": r["price"], "badges": r["badges"],
               "barcode": r["barcode"], "gd_idx": r["gd_idx"], "collected_at": r["collected_at"],
               "cu_size": f"{cu['size'][0]:g}{cu['size'][1]}" if cu["size"] else "",
               "cu_count": cu["count"] or ""}
        if best:
            _, i, ev = best
            row = rows[i]
            g = grade(cu, ev, row)
            vals, how = per_item(cu, row, g) if g in ("A", "B", "B-", "C") else (None, "")
            rec.update(grade=g, similarity=round(ev["sim"], 3), brand_ok=ev["brand_ok"], size_rel=ev["size_rel"],
                       category_conflict=ev["conflict"], kcal_check={True: "ok", False: "fail", None: ""}[atwater_ok(row)],
                       mfds_code=row[F["식품코드"]], mfds_name=row[F["식품명"]], mfds_class=row[F["식품대분류명"]],
                       mfds_base=row[F["영양성분함량기준량"]], mfds_weight=row[F["식품중량"]],
                       maker=row[F["제조사명"]], distributor=row[F["유통업체명"]],
                       report_no=row[F["품목제조보고번호"]], basis=how)
            for k, o in NUTRIENTS:
                rec[o + "_per_base"] = row[F[k]]
            if vals:
                rec.update(vals)
        else:
            rec.update(grade="F")
        out.append(rec)
        if n_i % 500 == 0:
            print(f"{n_i}/{len(cu_rows)}", flush=True)

    fields = ["cu_name", "category", "price", "badges", "grade", "kcal", "protein_g", "fat_g", "carb_g", "sugar_g",
              "fiber_g", "sodium_mg", "satfat_g", "transfat_g", "cholesterol_mg", "calcium_mg", "basis",
              "cu_size", "cu_count", "similarity", "brand_ok", "size_rel", "category_conflict", "kcal_check",
              "mfds_name", "mfds_code", "mfds_class", "mfds_base", "mfds_weight", "maker", "distributor",
              "report_no"] + [o + "_per_base" for _, o in NUTRIENTS] + ["barcode", "gd_idx", "collected_at"]
    with open(os.path.join(OUT_DIR, "cu_nutrition_v2.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(out)

    # 요약
    lines = [f"CU 상품 {len(out)}개, DB {len(rows)}건"]
    cats = ["간편식사", "즉석조리", "과자류", "아이스크림", "식품", "음료", "전체"]
    lines.append("카테고리 | n | A | B | B- | C | F | A+B 중 단백질·열량 있음")
    for c in cats:
        rs = out if c == "전체" else [x for x in out if x["category"] == c]
        cnt = collections.Counter(x["grade"] for x in rs)
        usable = sum(1 for x in rs if x["grade"] in ("A", "B") and x.get("kcal") not in (None, "")
                     and x.get("protein_g") not in (None, ""))
        lines.append(f"{c} | {len(rs)} | {cnt['A']} | {cnt['B']} | {cnt['B-']} | {cnt['C']} | {cnt['F']} | {usable}")
    # 실험용 후보 데이터셋: A, B, B- 중 열량·단백질 값이 있는 상품만 (행사 여부와 관계없이 정상가 사용)
    usable = [x for x in out if x["grade"] in ("A", "B", "B-")
              and x.get("kcal") not in (None, "") and x.get("protein_g") not in (None, "")]
    ufields = ["cu_name", "category", "price", "kcal", "protein_g", "fat_g", "carb_g", "sugar_g", "sodium_mg",
               "grade", "basis", "mfds_name", "mfds_code", "maker", "gd_idx", "collected_at"]
    with open(os.path.join(OUT_DIR, "cu_nutrition_usable.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=ufields, extrasaction="ignore")
        w.writeheader(); w.writerows(usable)
    hp = [x for x in usable if float(x["protein_g"]) >= 10]
    lines.append(f"실험용 후보(A·B·B-, 열량·단백질 있음): {len(usable)}개 "
                 f"(A·B {sum(x['grade'] in ('A', 'B') for x in usable)}, B- {sum(x['grade'] == 'B-' for x in usable)})")
    lines.append(f"  그중 단백질 10g 이상: {len(hp)}개 (A·B {sum(x['grade'] in ('A', 'B') for x in hp)})")

    with open(os.path.join(OUT_DIR, "cu_nutrition_v2_summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
