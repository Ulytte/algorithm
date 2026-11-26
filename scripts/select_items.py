# -*- coding: utf-8 -*-
"""
실험용 품목 데이터셋 생성: 자동 매칭 A, B, B- 등급 전체 (열량·단백질 값이 있는 상품).

상품은 하나도 빼지 않는다. 대신 자동 값이 이상해 보이는 상품에는
suspect 칸에 이유를 적어 둔다 (실험에서 뺄지, 포장 확인할지는 팀이 결정).

suspect 규칙:
  - 1개 열량 1500kcal 초과                -> DB의 대용량/묶음 제품 값일 가능성
  - 음료인데 1ml당 1kcal 초과             -> 분말·농축 제품 값일 가능성 (예: 포카리 분말)
  - DB식품중량 기준인데 DB 중량 400g/ml 초과 -> CU 상품보다 큰 포장 기준일 가능성
  - 단백질 열량(4kcal/g)이 총열량보다 큼     -> 값끼리 모순

출력:
  data/selected/experiment_items.csv
  data/selected/experiment_items_summary.txt
"""
import csv, os, re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "processed", "cu_nutrition_v2.csv")
OUT_DIR = os.path.join(ROOT, "data", "selected")
GRADES = ("A", "B", "B-")

# suspect 규칙에 걸렸지만 사람이 확인해 보니 값이 정상인 상품 (2026-11-24 검토)
#  - DB 중량이 큰 게 실제 상품 크기인 경우 (도시락·정식·죽·파스타·홈 아이스크림)
#  - 묶음 상품이라 총열량이 큰 게 맞는 경우 (햇반 N입, 우유 2입, 요구르트 5입)
#  - 원래 열량이 높은 음료·식재료 (푸룬주스, 식용유, 마요네즈)
# 반대로 아래는 계속 제외: DB가 대용량/멀티팩 기준(라면·과자·컵우동·떡볶이컵),
#  다른 제품과 매칭(맛소금→맛소금 김, 국밥→밥 없는 국), 분말·원액 값(포카리·콤부차·쌍화),
#  값 자체가 이상(칠성사이다 1075kcal, 토닉워터 387kcal), CU 용량을 알 수 없는 대용량(요구르트 1L 등)
REVIEWED_OK = {
    "면)치즈오븐스파게티", "도)마제소밥함박정식", "도)크카당맛있당정식", "김)닭강정유부세트",
    "도)급식대가뉴정석도시락", "푸드)도토리묵사발", "CJ)햇반귀리소고기죽", "CJ)햇반파로통곡물죽",
    "팔도한끼)우거지갈비탕&밥", "삼립)소문난광천김우동", "휴게소)죽전한돈뼈해장국", "CJ)햇반전복죽",
    "MDS)베이컨로제파스타", "MDS)베이컨크림파스타N", "마이)레드와인스테이크",
    "빙그레)엑설런트", "빙그레)그라시아쿠앤크홈",
    "테일러)푸룬딥워터180ml", "웅진)푸룬부스터P200ml",
    "CJ)대두유1.8L", "CJ)대두유500ml", "CJ)백설카놀라유500ml", "오뚜기)골드마요네스300g",
}


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def amount(text):
    """'1050g', '350ml', '1.8L' -> (숫자, 단위) / 실패 시 (None, None)"""
    m = re.match(r"\s*([\d.]+)\s*(kg|g|ml|l)", (text or "").lower())
    if not m:
        return None, None
    v, u = float(m.group(1)), m.group(2)
    if u in ("kg", "l"):
        v *= 1000
    return v, ("ml" if u in ("ml", "l") else "g")


def suspects(r, kcal, prot):
    why = []
    if kcal > 1500:
        why.append("열량 과다(대용량 값 의심)")
    size, unit = amount(r.get("cu_size", ""))
    if r["category"] == "음료" and unit == "ml" and size and kcal / size > 1.0:
        why.append("음료 열량 과다(분말·농축 값 의심)")
    if r["basis"].startswith("DB식품중량"):
        w, _ = amount(r.get("mfds_weight", ""))
        if w and w > 400:
            why.append(f"DB 중량 {r['mfds_weight']} 기준")
    if prot * 4 > kcal * 1.05 + 5:
        why.append("단백질 열량 > 총열량(모순)")
    return "; ".join(why)


# 최적 조합 점검(scripts/audit_optimal.py)으로 찾은 '값이 틀린' 상품 (2026-11-24 검토)
# 최적화는 너무 싸게 좋아 보이는 값을 골라내므로, 최적 조합에 나온 상품부터 확인했다.
BAD_VALUES = {
    "빙그레)프로틴스트링치즈": "DB 값이 여러 개 묶음(200g) 기준 — 1개에 단백질 60g·600kcal로 나옴",
    "크라운)참크래커": "DB 값이 대용량(280g) 기준 — 800원짜리 1개에 1,285kcal로 나옴",
    "오리온)고소미": "DB 값이 대용량(216g) 기준 — 1,200원 1갑 값이 아님",
    "코카)파워에이드P1.5L": "다른 제품(파워에이드 프로틴)과 매칭돼 단백질이 들어감",
    "코카)파워에이드캔240ml": "다른 제품(파워에이드 프로틴)과 매칭돼 단백질이 들어감",
    "990)하루견과그린": "DB 값이 여러 봉(100g) 기준 — 990원 1봉 값이 아님",
    "990)하루견과블루": "DB 값이 여러 봉(100g) 기준 — 990원 1봉 값이 아님",
    "990)하루견과핑크": "DB 값이 여러 봉(100g) 기준 — 990원 1봉 값이 아님",
    "제니코)스트링치즈": "CU 용량을 알 수 없고 DB 중량 기준 값이 가격에 비해 과다",
    "제니코)스모크스트링치즈": "CU 용량을 알 수 없고 DB 중량 기준 값이 가격에 비해 과다",
    "널담)카스테라초코": "CU 용량을 알 수 없고 DB 중량(336g) 기준 값이 가격에 비해 과다",
    "널담)카스테라플레인": "CU 용량을 알 수 없고 DB 중량 기준 값이 가격에 비해 과다",
    "팔도한끼)소고기육개장&밥": "밥이 포함된 상품인데 국만의 값으로 매칭",
    "팔도한끼)소고기장터국밥": "국밥인데 DB 100g 기준 값(85kcal) — 1개 값이 아님",
    "팔도한끼)진한돼지국밥": "국밥인데 DB 250g 기준 값 — 밥 포함 1개 값으로 보기 어려움",
    "팔도한끼)얼큰순대국밥": "국밥인데 DB 250g 기준 값 — 밥 포함 1개 값으로 보기 어려움",
}
# 그대로 먹는 음식이 아닌 조미료·식재료 (액젓·된장·식용유 등). 단백질·열량 '공급원'으로 뽑히는 걸 막는다.
CONDIMENT_RE = re.compile(r"(액젓|된장\d|쌈장|고추장\d|맛소금|대두유|카놀라유|참기름\d|마요네스|머스타드|페이스트|"
                          r"다진마늘|굴소스|소스\d*(g|ml|G|ML)?$|강된장양념|식초\d|연유\d)")

# 팀 결정(2026-11-24): 가스레인지로 끓이거나 구워야 하는 상품은 제외 (전자레인지·뜨거운 물은 허용)
#  - 봉지라면·건면·사리·당면·분말스프 (컵라면은 뜨거운 물이면 되므로 유지)
#  - 두부·순두부(찌개용)·어묵·어묵탕, 생고기·양념육(미트뱅크 등)·생베이컨
STOVE = {
    # 봉지라면·봉지면
    "농심)멸치칼국수", "농심)배홍동비빔면", "농심)생생우동", "농심)신라면", "농심)신라면건면", "농심)신라면블랙",
    "더본)백종원김치찌개라면", "삼양)까르보불닭볶음면", "삼양)맵탱마늘조개라면", "삼양)불닭볶음면", "삼양)불닭볶음탕면",
    "오뚜기)스낵면", "오뚜기)열라면", "오뚜기)열치즈라면", "오뚜기)오동통면", "오뚜기)진라면매운맛", "오뚜기)진라면순한맛",
    "진라면약간매운맛", "오뚜기)진밀면", "오뚜기)진비빔면", "오뚜기)진짬뽕", "오뚜기)참깨라면", "오뚜기)크림진짬뽕",
    "오뚜기)짜슐랭", "짱구)초코비의짜장라면", "치트키)진한새우탕면", "팔도)꼬꼬면", "이가)얼큰육개장칼국수", "이가)얼큰짬뽕",
    "이가)누룽지랑수제비랑", "한끼여행)투움바수제비", "삼양)탱글갈릭오일파스타", "삼양)탱글머쉬크림파스타", "오뚜기)옛날잡채", "금미옥)킹쫄라떡볶이",
    # 사리·당면·생면·분말스프
    "CJ)전통냉면사리150g", "오뚜기)당면300g", "오뚜기)옛날자른당면100g", "풀무원)생칼국수320g",
    "오뚜기)쇠고기스프80g", "오뚜기)크림스프80g", "오뚜기)콘크림스프", "오뚜기)양송이크림스프",
    # 두부·어묵
    "강릉초당)초당두부550g", "강릉초당)초당순두부400g", "CJ)삼호부산어묵200G", "CJ)삼호정통어묵탕342g",
    # 생고기·양념육·생베이컨
    "미트)간장삼겹살구이350g", "미트)고추장삼겹살구이350", "미트)닭다리스테이크320g", "미트)마늘제육볶음600g",
    "미트)매실불고기350g", "미트)앞다리제육볶음350g", "미트)양념목심구이600g", "미트)양념소불고기300g",
    "한우)큐브스테이크180g", "CJ)두툼한굿베이컨340g", "CJ)햄스빌아침베이컨70g",
    # 애매한 것도 제외 (팀 결정 2026-11-24: "애매한 거 다 빼고") - 찌개용 통조림, 냄비 데우기 권장 찌개
    "동원)꽁치300g", "신세계)순두부찌개450g",
}
CONDIMENT_NAMES = {"CJ)백설소갈비양념290g", "CJ)백설소불고기양념290g", "오뚜기)딸기쨈300g", "오뚜기)토마토케챂300g",
                   "웰팜)냉동다진청양고추180", "풀무원)순두부찌개양념140"}

BUNDLE_RE = re.compile(r"(\*\s*\d+|(?<![\d.])([2-9]|\d{2,})\s*(입|개입|구|봉|매|T)(?![가-힣]))")


def is_bundle(o):
    """여러 개가 한 상품으로 묶여 팔리는 경우 (예: 햇반210g*6입, 구운계란2입, 커피20T)"""
    c = num(o.get("cu_count"))
    return (c is not None and c > 1) or bool(BUNDLE_RE.search(o["cu_name"]))


# ---------------------------------------------------------------------------
# 식품 유형 (사용자 체크리스트용). 위에서부터 먼저 맞는 규칙을 쓴다.
# ---------------------------------------------------------------------------
FOOD_TYPES = ["도시락", "김밥·삼각김밥", "샌드위치·햄버거", "샐러드", "라면·면·떡볶이", "밥·죽",
              "닭가슴살·육가공", "계란·두부", "참치·수산", "우유·두유·요거트", "단백질음료·식품",
              "견과·안주", "과자·빵", "아이스크림", "기타음료", "기타식품"]
# 간편식사는 상품명 앞 글자(접두어)로 나뉜다
PREFIX_TYPE = {"도": "도시락", "김": "김밥·삼각김밥", "삼": "김밥·삼각김밥", "빅삼": "김밥·삼각김밥",
               "주": "김밥·삼각김밥", "샌": "샌드위치·햄버거", "햄": "샌드위치·햄버거", "핫": "샌드위치·햄버거",
               "샐": "샐러드", "면": "라면·면·떡볶이"}
NUTS = ("땅콩", "아몬드", "견과", "호두", "캐슈", "피스타치오", "해바라기", "너트")
SNACK_WORDS = ("쿠키", "샌드", "빵", "바", "케익", "케이크", "초코볼", "스콘")   # 과자류에서 견과로 보지 않을 말
OTHER_WORDS = ("소스", "양념", "돌김", "김자반", "양반김", "감태김", "참기름김", "브리즈")  # 식재료·조미료 등
KEYWORD_TYPE = [   # (유형, 키워드들) — 식품·음료에 적용, 위에서부터 먼저 맞는 것
    ("단백질음료·식품", ("프로틴", "단백", "프로핏", "뉴케어", "테이크핏", "하이뮨", "얼티브")),
    ("라면·면·떡볶이", ("라면", "면", "우동", "국수", "짬뽕", "짜파", "메밀소바", "냉소바", "파스타", "스파게티",
                    "짜장", "누들", "사발", "뚜껑", "볶이", "새우탕")),
    ("밥·죽", ("햇반", "밥", "죽", "리조또")),
    ("우유·두유·요거트", ("우유", "두유", "베지밀", "요거트", "요구르트", "요플레", "요프로", "야쿠르트",
                     "스트링치즈", "에멘탈", "밀크")),
    ("계란·두부", ("계란", "구운란", "반숙란", "장란", "에그", "두부")),
    ("참치·수산", ("참치", "크랩", "어묵", "연어", "오징어", "쥐포", "노가리", "크래미", "명란", "골뱅이", "새우", "고등어", "임연수", "황태")),
    ("닭가슴살·육가공", ("닭", "치킨", "소시지", "후랑크", "비엔나", "햄", "스팸", "베이컨", "육포", "부어스트",
                      "너겟", "돈까스", "족발", "편육", "순대", "스테이크", "제육", "불고기", "삼겹", "목심", "곱창", "만두", "교자")),
    ("견과·안주", NUTS),
]


def food_type(name, category):
    if category == "아이스크림":
        return "아이스크림"
    m = re.match(r"^([^)]+)\)", name)
    prefix = m.group(1) if m else ""
    if category == "간편식사":
        if prefix in PREFIX_TYPE:
            return PREFIX_TYPE[prefix]
        if "김밥" in name:
            return "김밥·삼각김밥"
    core = name[m.end():] if m else name
    if category == "과자류":
        nut = any(w in core for w in NUTS) and not any(w in core for w in SNACK_WORDS)
        return "견과·안주" if nut else "과자·빵"
    if any(w in core for w in OTHER_WORDS) or "피자" in core or "김밥김" in core:
        return "기타음료" if category == "음료" else "기타식품"
    if "김밥햄" in core:
        return "닭가슴살·육가공"
    if category == "식품" and core.endswith("도시락"):    # 팔도 (김치)도시락 = 컵라면
        return "라면·면·떡볶이"
    for t, words in KEYWORD_TYPE:
        if any(w in core for w in words):
            return t
    if category == "간편식사":
        return "기타식품"
    return "기타음료" if category == "음료" else "기타식품"


def event_of(badges):
    """CU 행사 표시 -> (받는 개수, 돈 내는 개수). 1+1 -> (2, 1), 2+1 -> (3, 2)"""
    tags = (badges or "").split(";")
    if "plus1" in tags:
        return 2, 1
    if "plus2" in tags:
        return 3, 2
    return None


def main():
    out = []
    for r in csv.DictReader(open(SRC, encoding="utf-8-sig")):
        if r["grade"] not in GRADES:
            continue
        kcal, prot, price = num(r["kcal"]), num(r["protein_g"]), num(r["price"])
        if kcal is None or prot is None or not price:
            continue
        out.append({
            "no": len(out) + 1,
            "cu_name": r["cu_name"],
            "category": r["category"],
            "price": int(price),                     # 정상가 (행사가 아님)
            "kcal": round(kcal, 1),
            "protein_g": round(prot, 2),
            "carb_g": r["carb_g"], "fat_g": r["fat_g"], "sugar_g": r["sugar_g"], "sodium_mg": r["sodium_mg"],
            "grade": r["grade"],
            "suspect": suspects(r, kcal, prot),
            "basis": r["basis"],
            "cu_size": r.get("cu_size", ""),
            "mfds_name": r["mfds_name"],
            "mfds_weight": r.get("mfds_weight", ""),
            "maker": r["maker"],
            "mfds_code": r["mfds_code"],
            "cu_count": r.get("cu_count", ""),
            "badges": r.get("badges", ""),
            "gd_idx": r["gd_idx"],
            "collected_at": r["collected_at"],
        })

    os.makedirs(OUT_DIR, exist_ok=True)

    # 1) 제외 사유 결정
    #    - 묶음 상품(팀 결정 2026-11-24): 단품만 사용
    #    - suspect(자동 값 이상) 중 수동 검토로 정상 판정되지 않은 것
    for o in out:
        o["review"] = "수동 검토: 정상" if o["suspect"] and o["cu_name"] in REVIEWED_OK else ""
        o["exclude"] = ""
        if is_bundle(o):
            o["exclude"] = "묶음 상품"
        elif o["cu_name"] in BAD_VALUES:
            o["exclude"] = "값 오류(검토): " + BAD_VALUES[o["cu_name"]]
        elif o["cu_name"] in CONDIMENT_NAMES or (
                o["category"] != "과자류" and CONDIMENT_RE.search(o["cu_name"])):  # 과자류는 '고추장맛 칩' 등이라 제외
            o["exclude"] = "조미료·식재료"
        elif o["cu_name"] in STOVE:
            o["exclude"] = "가스레인지 조리 필요"
        elif o["suspect"] and not o["review"]:
            o["exclude"] = "값 이상: " + o["suspect"]
    singles = [o for o in out if not o["exclude"]]
    excluded = [o for o in out if o["exclude"]]
    unused = (REVIEWED_OK | STOVE | CONDIMENT_NAMES | set(BAD_VALUES)) - {o["cu_name"] for o in out}
    if unused:
        print("경고: REVIEWED_OK에 있지만 데이터에 없는 상품:", ", ".join(sorted(unused)))

    # 2) 행사 가격 적용 (팀 결정 2026-11-24: 행사도 반영)
    #    행사 중인 상품은 행사 행 하나만 둔다 (단품 정가 행 없음):
    #      1+1 -> 2개를 정가 1개 값에 / 2+1 -> 3개를 정가 2개 값에
    #    -> 상품 하나 = 행 하나이므로 일반 0/1 배낭 문제 그대로 쓸 수 있다.
    items = []
    for o in singles:
        base = dict(o, item_id=o["gd_idx"], group_id=o["gd_idx"], units=1, event="", unit_price=o["price"],
                    food_type=food_type(o["cu_name"], o["category"]))
        ev = event_of(o["badges"])
        if not ev:
            items.append(base)
        else:
            units, pay = ev
            row = dict(base)
            row.update(item_id=f"{o['gd_idx']}-{units}", units=units,
                       event=f"{pay}+1",
                       price=o["price"] * pay, unit_price=round(o["price"] * pay / units))
            row["cu_name"] = f"{o['cu_name']} ×{units} ({row['event']})"
            for k in ("kcal", "protein_g", "carb_g", "fat_g", "sugar_g", "sodium_mg"):
                v = num(o[k])
                row[k] = "" if v is None else round(v * units, 2)
            items.append(row)
    for i, o in enumerate(items, 1):
        o["no"] = i

    fields = ["no", "item_id", "group_id", "cu_name", "category", "food_type", "units", "event", "price", "unit_price",
              "kcal", "protein_g", "carb_g", "fat_g", "sugar_g", "sodium_mg", "grade", "suspect", "review",
              "basis", "cu_size", "mfds_name", "mfds_weight", "maker", "mfds_code", "badges", "gd_idx", "collected_at"]
    with open(os.path.join(OUT_DIR, "experiment_items.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(items)
    # 3) 웹 앱용 (팀 결정 2026-11-25): 행사 상품은 적게 사는 행도 둔다.
    #      1+1 -> 1개(1개 값) 또는 2개(1개 값)
    #      2+1 -> 1개(1개 값), 2개(2개 값), 3개(2개 값)
    #    같은 상품(group_id)의 행은 한 조합에 하나만 — 앱 탐색에서 막는다.
    #    실험용 experiment_items.csv (Python 알고리즘 비교)는 상품당 1행 그대로 둔다.
    web_items = []
    for o in items:
        web_items.append(o)
        if o["event"]:
            src = next(s for s in singles if s["gd_idx"] == o["group_id"])
            fewer = [1] if o["event"] == "1+1" else [1, 2]
            for u in fewer:
                row = dict(src, item_id=o["group_id"] if u == 1 else f"{o['group_id']}-{u}", group_id=o["group_id"],
                           units=u, event="", promo=o["event"], price=src["price"] * u, unit_price=src["price"],
                           food_type=o["food_type"])
                if u > 1:
                    row["cu_name"] = f"{src['cu_name']} ×{u}"
                    for k in ("kcal", "protein_g", "carb_g", "fat_g", "sugar_g", "sodium_mg"):
                        v = num(src[k])
                        row[k] = "" if v is None else round(v * u, 2)
                web_items.append(row)
    with open(os.path.join(OUT_DIR, "web_items.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields + ["promo"], extrasaction="ignore")
        w.writeheader(); w.writerows(web_items)

    xfields = ["exclude"] + [k for k in fields if k not in ("no", "item_id", "group_id", "units", "event", "unit_price")]
    with open(os.path.join(OUT_DIR, "experiment_items_excluded.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=xfields, extrasaction="ignore")
        w.writeheader(); w.writerows(excluded)

    ev_rows = [o for o in items if o["event"]]
    assert len({o["group_id"] for o in items}) == len(items), "상품당 행이 하나여야 함"
    lines = [f"실험용 행 experiment_items.csv: {len(items)}행 (상품당 1행) = 행사 없음 {len(items) - len(ev_rows)} + 행사 {len(ev_rows)}",
             f"  행사: " + ", ".join(f"{k} {v}" for k, v in Counter(o['event'] for o in ev_rows).items()),
             f"  단품 등급별: " + ", ".join(f"{g} {sum(o['grade'] == g for o in singles)}" for g in GRADES),
             f"  단품 카테고리별: " + ", ".join(f"{k} {v}" for k, v in Counter(o['category'] for o in singles).items()),
             f"  단품 중 단백질 10g 이상: {sum(o['protein_g'] >= 10 for o in singles)}개",
             f"  식품 유형별: " + ", ".join(f"{t} {sum(o['food_type'] == t for o in items)}" for t in FOOD_TYPES),
             f"  행사 가격은 {singles[0]['collected_at']} 수집 기준 (CU 행사는 보통 매월 바뀜)",
             f"제외 experiment_items_excluded.csv: {len(excluded)}개",
             "  " + ", ".join(f"{k} {v}" for k, v in Counter(o['exclude'].split(':')[0] for o in excluded).items()),
             "묶음 상품으로 제외:"]
    lines += [f"  {o['cu_name']}" for o in excluded if o["exclude"] == "묶음 상품"]
    open(os.path.join(OUT_DIR, "experiment_items_summary.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    old_md = os.path.join(OUT_DIR, "experiment_items.md")   # 이전 50개 선정 표는 더 이상 맞지 않으므로 삭제
    if os.path.exists(old_md):
        os.remove(old_md)


if __name__ == "__main__":
    main()
