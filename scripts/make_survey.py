# -*- coding: utf-8 -*-
"""
매장 조사(포장지 영양성분표 확인) 대상 상품 목록과 입력용 템플릿 생성

선정 기준 (제안 단계, 팀 논의로 변경 가능)
- 구매 후 바로 먹을 수 있는 1회 분량 상품 (생란·생고기·조리용 두부·대용량 1L 이상·10입 묶음 제외)
- 단백질 공급원(닭가슴살·계란·유제품·두유·단백질음료)과 식사류(삼각김밥·김밥·도시락·샐러드·샌드위치)를 섞어
  '단백질 효율'과 '칼로리 채우기'가 서로 경쟁하는 조합 문제가 되도록 구성
- 가격대를 고르게 (800원 ~ 5,900원)
- 목표 40~50개 + 품절 대비 여유분 → 53개

출력
- data/survey/survey_template.csv : 팀원이 채워 넣는 입력용 표 (Excel/구글시트에서 열기)
- docs/store_checklist.md         : 매장에서 보는 체크리스트 (카테고리별)
참고값 컬럼(db_*)은 식약처 DB 자동 매칭 후보로, 검증되지 않은 값이다.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import match_mfds as mm  # 파일럿에서 만든 매칭 함수 재사용

BASE = os.path.join(os.path.dirname(__file__), "..")
OUT_CSV = os.path.join(BASE, "data", "survey", "survey_template.csv")
OUT_MD = os.path.join(BASE, "docs", "store_checklist.md")

# (CU 상세 ID gd_idx, 유형) — data/raw/cu_products.csv 의 gd_idx
SELECTED = [
    # 간편식사 18
    ("26412", "삼각김밥"), ("26496", "삼각김밥"), ("26415", "삼각김밥"), ("26960", "삼각김밥"),
    ("25774", "주먹밥"), ("26575", "김밥"), ("21781", "김밥"), ("27793", "김밥"), ("27400", "김밥"),
    ("25784", "도시락"), ("28449", "도시락"), ("27397", "도시락"),
    ("17620", "샐러드"), ("28559", "샐러드"), ("23571", "샐러드"),
    ("27798", "샌드위치"), ("26440", "샌드위치"), ("28211", "햄버거"),
    # 식품 20
    ("27440", "닭가슴살"), ("27441", "닭가슴살"), ("8527", "닭가슴살"), ("26882", "닭가슴살"),
    ("27119", "닭가슴살가공"), ("13342", "닭가슴살가공"), ("17061", "닭가슴살가공"),
    ("27934", "계란"), ("15038", "계란"), ("23740", "계란"), ("19370", "계란가공"),
    ("26100", "계란가공"), ("26798", "치즈"), ("4523", "참치캔"), ("28284", "참치캔"),
    ("23321", "두부"), ("22589", "낫또"), ("27822", "즉석밥"), ("1650", "소시지"), ("27591", "단백질과자"),
    # 음료 15
    ("4055", "우유"), ("4053", "우유"), ("25931", "두유"), ("15514", "두유"), ("27305", "두유"),
    ("6217", "두유"), ("13115", "단백질음료"), ("15686", "단백질음료"), ("26231", "단백질음료"),
    ("16977", "단백질음료"), ("21523", "단백질음료"), ("26265", "단백질음료"),
    ("23884", "요거트"), ("20997", "요거트"), ("13074", "단백질음료"),
]

FILL_COLUMNS = [
    "found",            # 매장에서 찾았는지 Y/N
    "store_price",      # 매장 표시 정상가(원), 행사가 아님
    "net_content",      # 총 내용량 (예: 100g, 190ml)
    "label_basis",      # 영양성분 표시 기준 (총 내용량 / 100g / 1회 제공량 xx g)
    "servings_per_pack",# 기준이 1회 제공량이면 포장 1개에 몇 회분인지
    "label_kcal",       # 표시된 열량 (표시 기준 그대로)
    "label_protein_g",  # 표시된 단백질
    "label_carb_g",     # 표시된 탄수화물 (검산용)
    "label_fat_g",      # 표시된 지방 (검산용)
    "photo_file",       # 사진 파일명 (예: 07_front.jpg, 07_label.jpg)
    "checked_by",       # 조사자 이니셜
    "checked_date",     # 확인 날짜 YYYY-MM-DD
    "note",             # 특이사항 (리뉴얼, 품절, 규격 다름 등)
]


def main():
    by_idx = {r["gd_idx"]: r for r in mm.load_cu()}
    missing = [g for g, _ in SELECTED if g not in by_idx]
    if missing:
        raise SystemExit(f"CU 목록에 없는 gd_idx: {missing}")
    if len(set(g for g, _ in SELECTED)) != len(SELECTED):
        raise SystemExit("중복 선정 상품이 있음")

    rows = []
    for i, (gd, kind) in enumerate(SELECTED, 1):
        r = by_idx[gd]
        # 식약처 DB 참고 후보 (자동, 미검증)
        cu = mm.split_cu_name(r["name"])
        best = None
        for kw in mm.keywords_for(cu[1]):
            for c in mm.query_mfds(kw):
                s = mm.score(cu, c)
                if best is None or s[0] > best[0][0]:
                    best = (s, c)
            if best and mm.classify(*best[0][1:]) == "확실":
                break
        ref = {"db_confidence": "실패", "db_name": "", "db_weight": "", "db_kcal_item": "", "db_protein_item": ""}
        if best:
            (_, sim, b_ok, w_ok), c = best
            conf = mm.classify(sim, b_ok, w_ok)
            if conf != "실패":
                kcal, prot = mm.per_item(c)
                ref = {"db_confidence": conf, "db_name": c["name"], "db_weight": c["weight"],
                       "db_kcal_item": kcal if kcal is not None else "",
                       "db_protein_item": prot if prot is not None else ""}
        row = {"id": f"{i:02d}", "category": r["category"], "kind": kind, "cu_name": r["name"],
               "site_price": r["price"], "site_badges": r["badges"], "gd_idx": gd,
               "source_url": r["source"], "site_collected_at": r["collected_at"], **ref}
        row.update({k: "" for k in FILL_COLUMNS})
        rows.append(row)
        print(f"{row['id']} {r['name']} [{ref['db_confidence']}]")

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    head = ["id", "category", "kind", "cu_name", "site_price", "site_badges"] + FILL_COLUMNS + \
           ["db_confidence", "db_name", "db_weight", "db_kcal_item", "db_protein_item",
            "gd_idx", "source_url", "site_collected_at"]
    if os.path.exists(OUT_CSV):
        raise SystemExit(f"이미 존재함(덮어쓰지 않음): {OUT_CSV}")
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=head)
        w.writeheader(); w.writerows(rows)

    # 매장용 체크리스트 (Markdown)
    md = ["# CU 매장 조사 체크리스트", "",
          f"대상 {len(rows)}개 (목표 40~50개 + 품절 대비 여유분). 가격은 CU 공식 사이트 기준"
          f"({rows[0]['site_collected_at']} 수집). 행사(1+1, 2+1)여도 **정상가**를 적는다.", "",
          "각 상품마다: ☐ 앞면 사진 ☐ 영양성분표 사진 ☐ 매장 정상가 ☐ 총 내용량 ☐ 표시 기준(총/100g/1회)", ""]
    for cat in ("간편식사", "식품", "음료"):
        md += [f"## {cat}", "", "| ☐ | ID | 유형 | 상품명(CU 표기) | 사이트 가격 | 행사 |", "|---|---|---|---|---|---|"]
        for r in rows:
            if r["category"] == cat:
                badge = r["site_badges"].replace("plus1", "1+1").replace("plus2", "2+1").replace("new", "신상")
                md.append(f"| ☐ | {r['id']} | {r['kind']} | {r['cu_name']} | {int(r['site_price']):,}원 | {badge} |")
        md.append("")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"저장: {os.path.abspath(OUT_CSV)}\n저장: {os.path.abspath(OUT_MD)}")


if __name__ == "__main__":
    main()
