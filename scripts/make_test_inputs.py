# -*- coding: utf-8 -*-
"""
팀원 알고리즘 테스트용 입력 만들기 -> tests/test_inputs.json, tests/test_inputs.md

각 입력은 (상품 목록, 단백질 하한 R, 열량 C_min~C_max) 이다.
  - 상품 목록: "all"(실험용 1,315개 전체) 또는 item_id 목록 (results/experiment_subsets.json 의 부분집합)
  - 정답(최저 가격)은 DP 와 B&B 로 구하고 둘이 같은지 확인한다. 상품 20개 이하면 완전탐색과도 비교한다.
  - Greedy 결과, DP 상태 갱신 수, B&B 노드 수도 함께 적어서 '왜 이 입력이 차이를 보여 주는지' 근거로 쓴다.

실행: python -I scripts/make_test_inputs.py
"""
import json
import os
import sys
import time
from itertools import combinations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from algorithms import load_items, greedy, dp_solve, bnb, check  # noqa: E402

DATA = os.path.join(ROOT, "data", "selected", "experiment_items.csv")
SUB = os.path.join(ROOT, "results", "experiment_subsets.json")
OUT_JSON = os.path.join(ROOT, "tests", "test_inputs.json")
OUT_MD = os.path.join(ROOT, "tests", "test_inputs.md")

# (id, 이름, 상품(all 또는 '크기-시드'), R, C_min, C_max, 무엇을 보여 주는지)
CASES = [
    ("T1", "작은 입력 (정답 손으로 확인용)", "10-1", 20, 300, 500,
     "상품 10개라 2^10 = 1,024가지를 모두 따져 정답을 확인할 수 있다. 새 알고리즘의 첫 테스트로 쓴다."),
    ("T2", "Greedy가 크게 비싼 답", "all", 20, 300, 500,
     "Greedy는 1g당 가장 싼 단백질 음료 3개 묶음(단백질 75g)을 사서 20g 목표를 크게 넘긴다. "
     "최적은 해바라기씨 하나다. 이 목록에서 Greedy와 최적의 차이가 가장 크다."),
    ("T3", "Greedy가 해를 못 찾음", "100-0", 60, 600, 900,
     "해가 있는데도 Greedy는 1g당 싼 상품으로 열량을 먼저 써 버려 단백질을 못 채운다. 최적 보장 알고리즘만 답을 낸다."),
    ("T4", "DP만 느림 (Greedy·B&B는 금방)", "all", 80, 400, 1000,
     "R과 C_max가 커서 DP 표가 (80+1) x (1000+1)칸이다. 상품 1,315개를 곱하면 1억 칸 이상을 계산한다. "
     "같은 입력에서 Greedy도 최적을 찾고 B&B는 노드 몇 개로 끝난다."),
    ("T5", "B&B가 가장 많이 탐색", "100-4", 80, 700, 1000,
     "기존 실험 230개 경우 중 B&B 방문 노드가 가장 많았던 입력이다. 가지치기가 잘 안 되는 경우를 보여 준다."),
    ("T6", "해 없음 (B&B는 증명에 노드가 많이 듦)", "40-0", 60, 600, 900,
     "조건을 만족하는 조합이 없다. 새 알고리즘이 '해 없음'을 제대로 내는지 확인한다. "
     "B&B는 해가 없다는 걸 증명하려고 노드를 1만 개 가까이 방문한다(그래도 DP보다는 빠르다)."),
    ("T7", "열량 범위가 아주 좁음", "all", 40, 600, 620,
     "열량을 20kcal 범위에 맞춰야 한다. 단백질만 보고 고르는 Greedy가 범위를 맞추기 어렵다."),
    ("T8", "열량 하한이 큼 (단백질은 쉬움)", "all", 20, 900, 1000,
     "단백질 20g은 쉽지만 열량 900kcal 이상을 싸게 채워야 한다. Greedy는 단백질용으로 음료 묶음을 먼저 사고, "
     "2단계에서 열량을 채우려 과자를 더 산다. 최적은 볶음땅콩 하나로 둘 다 채운다."),
    ("T9", "중간 크기 (과제 강조 구간 n = 50)", "50-2", 40, 500, 800,
     "과제에서 강조한 n = 30~50 구간의 대표 입력이다. 모두 최적을 찾지만 DP만 시간이 크게 든다."),
]


def brute(items, R, c_min, c_max):
    best = None
    for r in range(1, len(items) + 1):
        for comb in combinations(items, r):
            p = sum(it.protein for it in comb)
            k = sum(it.kcal for it in comb)
            if p >= R and c_min <= k <= c_max:
                c = sum(it.price for it in comb)
                if best is None or c < best:
                    best = c
    return best


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    all_items = load_items(DATA)
    by_id = {it.id: it for it in all_items}
    subsets = json.load(open(SUB, encoding="utf-8"))["subsets"]
    out = []
    for cid, title, src, R, c_min, c_max, why in CASES:
        items = all_items if src == "all" else [by_id[i] for i in subsets[src]]
        g = greedy(items, R, c_min, c_max)
        d = dp_solve(items, R, c_min, c_max)
        b = bnb(items, R, c_min, c_max, initial=g, time_limit=120)
        for r in (g, d, b):
            check(r, R, c_min, c_max)
        assert b.optimal, f"{cid}: B&B 시간 제한"
        assert d.cost == b.cost, f"{cid}: DP {d.cost} != B&B {b.cost}"
        bf = brute(items, R, c_min, c_max) if len(items) <= 20 else "생략"
        if bf != "생략":
            assert bf == d.cost, f"{cid}: 완전탐색 {bf} != DP {d.cost}"
        b0 = bnb(items, R, c_min, c_max, time_limit=120)     # Greedy 시작값 없이 (B&B 자체 탐색량)
        assert b0.cost == b.cost

        def combo(res):
            return [{"item_id": it.id, "name": it.name, "price": it.price, "protein_g": it.protein, "kcal": it.kcal}
                    for it in res.items]

        rec = {
            "id": cid, "title": title, "why": why,
            "input": {"items": "all" if src == "all" else subsets[src], "n": len(items),
                      "protein_min_g": R, "kcal_min": c_min, "kcal_max": c_max},
            "answer": {"optimal_cost": d.cost, "optimal_combo_example": combo(b) if b.cost is not None else [],
                       "protein_g": b.protein, "kcal": b.kcal},
            "reference": {
                "greedy_cost": g.cost, "greedy_note": g.note,
                "greedy_gap_pct": None if g.cost is None or d.cost is None else round((g.cost - d.cost) / d.cost * 100, 1),
                "dp_table_cells": (R + 1) * (c_max + 1), "dp_updates": d.nodes, "dp_ms": round(d.time_s * 1000, 1),
                "bnb_nodes_with_greedy_start": b.nodes, "bnb_nodes_without_start": b0.nodes,
                "bnb_ms": round(b.time_s * 1000, 2), "greedy_ms": round(g.time_s * 1000, 2),
                "brute_force_cost": bf,
            },
        }
        out.append(rec)
        print(f"{cid} {title}: n={len(items)} 정답={d.cost} Greedy={g.cost} "
              f"DP {d.time_s*1000:,.0f}ms / B&B {b.nodes:,}노드(시작값 없이 {b0.nodes:,}) / 완전탐색={bf}")

    meta = {"data": "data/selected/experiment_items.csv", "data_count": len(all_items),
            "rule": "단백질 합 >= protein_min_g, kcal_min <= 열량 합 <= kcal_max, 상품은 0개 또는 1개, 가격 합 최소",
            "integer_rule": "단백질은 g 단위 내림, 열량은 kcal 단위 반올림 (algorithms/common.py load_items)",
            "made": time.strftime("%Y-%m-%d %H:%M"),
            "timing_note": "시간(ms)은 i5-1340P 노트북 1회 측정값이라 참고용이다. 비교에는 dp_updates, bnb_nodes 같은 횟수가 더 안정적이다."}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "cases": out}, f, ensure_ascii=False, indent=1)
    write_md(meta, out)
    print(f"저장: {OUT_JSON}, {OUT_MD}")


def fmt(v, unit="원"):
    return "해 없음" if v is None else f"{v:,}{unit}"


def write_md(meta, cases):
    L = ["# 알고리즘 테스트 입력", "",
         f"데이터: `{meta['data']}` ({meta['data_count']:,}개). 문제: {meta['rule']}.", "",
         f"정수화: {meta['integer_rule']}. 새 알고리즘도 같은 규칙을 써야 정답이 맞는다.", "",
         "정답은 DP와 B&B로 구하고 둘이 같은지 확인했다. 상품 20개 이하는 완전탐색과도 같았다. "
         "상품 목록(item_id)과 정답 조합은 `tests/test_inputs.json`에 있다.", "",
         "| ID | 입력 | n | 단백질 | 열량 | 정답 | Greedy | DP 표 칸 / 시간 | B&B 노드 |",
         "|---|---|---|---|---|---|---|---|---|"]
    for c in cases:
        i, a, r = c["input"], c["answer"], c["reference"]
        gap = "" if r["greedy_gap_pct"] in (None, 0) else f" (+{r['greedy_gap_pct']}%)"
        g = fmt(r["greedy_cost"]) + gap if r["greedy_cost"] is not None else "못 찾음"
        L.append(f"| {c['id']} | {c['title']} | {i['n']:,} | ≥ {i['protein_min_g']}g | {i['kcal_min']}~{i['kcal_max']} | "
                 f"{fmt(a['optimal_cost'])} | {g} | {r['dp_table_cells']:,}칸 / {r['dp_ms']:,}ms | {r['bnb_nodes_with_greedy_start']:,} |")
    L += ["", "## 입력별 설명", ""]
    for c in cases:
        a = c["answer"]
        L.append(f"**{c['id']} {c['title']}** — {c['why']}")
        if a["optimal_combo_example"]:
            names = " + ".join(x["name"] for x in a["optimal_combo_example"])
            L.append(f"- 정답 조합 예: {names} → {a['optimal_cost']:,}원, 단백질 {a['protein_g']}g, {a['kcal']}kcal "
                     "(같은 가격의 다른 조합이 있을 수 있다)")
        L.append("")
    L += ["## 쓰는 방법", "",
          "1. `tests/test_inputs.json`의 `input`을 읽는다. `items`가 `\"all\"`이면 CSV 전체, 아니면 item_id 목록의 상품만 쓴다.",
          "2. 내 알고리즘의 가격 합을 `answer.optimal_cost`와 비교한다. 최적 보장 알고리즘이면 같아야 하고, 근사·휴리스틱이면 차이(%)를 적는다.",
          "3. 시간은 컴퓨터마다 달라서, 같은 컴퓨터에서 Greedy·DP·B&B와 함께 재서 비교한다.", "",
          f"> {meta['timing_note']}", ""]
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(L))


if __name__ == "__main__":
    main()
