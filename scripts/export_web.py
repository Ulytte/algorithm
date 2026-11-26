# -*- coding: utf-8 -*-
"""
웹 페이지(web/index.html)용 상품 데이터 내보내기: data/selected/web_items.csv -> web/items.json
(web_items.csv = experiment_items.csv + 행사 상품의 '1개만 사기' 행. scripts/select_items.py 가 만든다)

정수화는 algorithms/common.py 의 load_items 와 똑같이 파이썬에서 미리 해 둔다.
(파이썬 round 는 .5 를 짝수로 보내고 JS Math.round 는 올리기 때문에, 브라우저에서 다시 하면 값이 달라질 수 있음)
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from algorithms import load_items  # noqa: E402
import csv  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "data", "selected", "web_items.csv")
OUT = os.path.join(ROOT, "web", "items.json")


def main():
    items = load_items(SRC)
    extra = {r["item_id"]: r for r in csv.DictReader(open(SRC, encoding="utf-8-sig"))}
    rows = []
    for it in items:
        r = extra[it.id]
        # [id, 이름, 가격, 단백질(정수), 칼로리(정수), 단백질 원값, 칼로리 원값, 유형, 행사, 탄, 지, 당, 나트륨, 등급, CU 분류,
        #  상품 묶음 id(같은 상품의 행들은 같은 값), 행사 상품을 적게 사는 행이면 그 행사("1+1"/"2+1"), 받는 개수]
        rows.append([it.id, it.name, it.price, it.protein, it.kcal,
                     round(it.protein_raw, 2), round(it.kcal_raw, 1), it.food_type, it.event,
                     round(it.carb, 2), round(it.fat, 2), round(it.sugar, 2), round(it.sodium, 1),
                     r.get("grade", ""), r.get("category", ""), r.get("group_id", it.id), r.get("promo", ""), int(r.get("units") or 1)])
    collected = sorted({r.get("collected_at", "")[:10] for r in extra.values()} - {""})
    meta = {"source": "CU 상품 목록 + 식약처 가공식품 영양성분 DB", "collected": collected[-1] if collected else "",
            "count": len(rows)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write('{"meta":' + json.dumps(meta, ensure_ascii=False) + ',"items":[\n')
        f.write(",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in rows))
        f.write("\n]}\n")
    print(f"{OUT}: {len(rows)}개")


if __name__ == "__main__":
    main()
