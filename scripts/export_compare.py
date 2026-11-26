# -*- coding: utf-8 -*-
"""
알고리즘 비교 페이지(web/compare.html)용 데이터 내보내기 -> web/compare_data.json

  - items  : experiment_items.csv (Python 실험과 같은 상품당 1행, 정수화도 load_items 와 같음)
  - subsets: run_experiment.py 가 쓴 부분집합 (상품 번호 목록) — 페이지에서 같은 입력으로 다시 돌리기 위함
  - results: results/experiment_results.csv (Python 실험 결과)

실행: python -I scripts/export_compare.py   (run_experiment.py 다음에)
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from algorithms import load_items  # noqa: E402

DATA = os.path.join(ROOT, "data", "selected", "experiment_items.csv")
RES = os.path.join(ROOT, "results", "experiment_results.csv")
SUB = os.path.join(ROOT, "results", "experiment_subsets.json")
OUT = os.path.join(ROOT, "web", "compare_data.json")


def num(x):
    if x in ("", None):
        return None
    f = float(x)
    return int(f) if f.is_integer() else f


def main():
    items = load_items(DATA)
    raw = {r["item_id"]: r for r in csv.DictReader(open(DATA, encoding="utf-8-sig"))}
    idx = {it.id: i for i, it in enumerate(items)}
    # [id, 이름, 가격, 단백질(정수, 내림), 칼로리(정수, 반올림), 단백질 원값, 칼로리 원값, 식품 유형, 행사, 탄, 지, 당, 나트륨]
    rows = [[it.id, it.name, it.price, it.protein, it.kcal, round(it.protein_raw, 2), round(it.kcal_raw, 1),
             it.food_type, it.event, round(it.carb, 2), round(it.fat, 2), round(it.sugar, 2), round(it.sodium, 1)]
            for it in items]
    sub = json.load(open(SUB, encoding="utf-8"))
    subsets = {k: [idx[i] for i in v] for k, v in sub["subsets"].items()}
    res = []
    for r in csv.DictReader(open(RES, encoding="utf-8-sig")):
        res.append({
            "sc": r["scenario"], "R": int(r["R"]), "cmin": int(r["c_min"]), "cmax": int(r["c_max"]),
            "n": int(r["n"]), "seed": num(r["seed"]), "algo": r["algo"], "cost": num(r["cost"]),
            "opt": num(r["opt_cost"]), "gap": num(r["gap_pct"]), "optG": r["optimal_guaranteed"] == "True",
            "p": num(r["protein"]), "k": num(r["kcal"]), "ms": float(r["time_ms"]), "nodes": int(r["nodes"]),
            "kb": num(r["peak_kb"]), "brute": r["brute_check"], "note": r["note"],
            "ids": [idx[i] for i in r["chosen_ids"].split()] if r["chosen_ids"] else [],
        })
    collected = sorted({r.get("collected_at", "")[:10] for r in raw.values()} - {""})
    meta = dict(sub["meta"], collected=collected[-1] if collected else "", count=len(rows))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write('{"meta":' + json.dumps(meta, ensure_ascii=False) + ',\n"subsets":' + json.dumps(subsets, separators=(",", ":")))
        f.write(',\n"items":[\n' + ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in rows))
        f.write('\n],\n"results":[\n' + ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in res) + "\n]}\n")
    print(f"{OUT}: 상품 {len(rows)}개, 결과 {len(res)}행, 부분집합 {len(subsets)}개")


if __name__ == "__main__":
    main()
