# -*- coding: utf-8 -*-
"""
데이터 점검: 여러 조건으로 최적 조합을 구해 보고, 최적 조합에 자주 나오는 상품을 뽑는다.

최적화는 '너무 싸게 좋아 보이는' 값을 정확히 찾아내므로, 최적 조합에 나오는 상품부터
값이 맞는지 확인하는 것이 가장 효율적인 정제 방법이다.
  조건: 단백질 R x 열량 범위 격자, 전체 상품 + 유형 하나씩 체크
결과: data/selected/audit_optimal.txt (상품별 등장 횟수와 매칭 근거)
"""
import csv
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from algorithms import load_items, greedy, bnb  # noqa: E402

DATA = os.path.join(ROOT, "data", "selected", "experiment_items.csv")
OUT = os.path.join(ROOT, "data", "selected", "audit_optimal.txt")

PROTEINS = [20, 30, 40, 50, 60, 80, 100]
KCALS = [(300, 500), (400, 700), (500, 800), (600, 900), (700, 1000), (800, 1200)]


def main():
    items = load_items(DATA)
    meta = {r["item_id"]: r for r in csv.DictReader(open(DATA, encoding="utf-8-sig"))}
    types = sorted({it.food_type for it in items})
    seen = Counter()
    runs = 0
    # 전체 상품 + 유형 하나만 (대체 조합 없이 그 유형 안에서만) — 유형 안에서 튀는 값도 잡기 위해
    for checked in [None] + [t for t in types]:
        pool = items if checked is None else [it for it in items if it.food_type == checked]
        for R in PROTEINS:
            for cmin, cmax in KCALS:
                g = greedy(pool, R, cmin, cmax)
                res = bnb(pool, R, cmin, cmax, initial=g, time_limit=3.0)
                runs += 1
                if res.cost is not None:
                    for it in res.items:
                        seen[it.id] += 1
    L = [f"조건 {runs}개에서 최적 조합에 나온 상품 {len(seen)}개 (많이 나온 순)", ""]
    for iid, cnt in seen.most_common():
        m = meta[iid]
        L.append(f"{cnt:4d} | {iid} | {m['cu_name']} | {m['food_type']} | {m['price']}원 | {m['kcal']}kcal | "
                 f"P {m['protein_g']} | {m['grade']} | {m['basis']} | cu={m['cu_size']} | "
                 f"DB={m['mfds_name']} {m['mfds_weight']} | {m['maker']}")
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(L[0])


if __name__ == "__main__":
    main()
