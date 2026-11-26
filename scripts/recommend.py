# -*- coding: utf-8 -*-
"""
추천 실행 (명령줄)

예)
  python -I scripts/recommend.py --list-types
  python -I scripts/recommend.py --types 샌드위치·햄버거 라면·면·떡볶이 --protein 40 --kcal 500 800
  python -I scripts/recommend.py --protein 60 --kcal 600 900 --sodium-max 1500 --sugar-max 20
  (--types 를 빼면 전체 상품)
"""
import argparse
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 윈도 콘솔(cp949)에서 깨짐 방지
from algorithms import load_items, Limits, recommend, check  # noqa: E402

DATA = os.path.join(ROOT, "data", "selected", "experiment_items.csv")


def format_rec(rec, R, c_min, c_max, limits):
    L = []
    cond = f"단백질 ≥ {R}g, 열량 {c_min}~{c_max}kcal" + (f", {limits.describe()}" if limits.active() else "")
    L.append(f"[조건] {cond}")
    for m in rec.messages:
        L.append(m)
    r = rec.result
    if r is not None and r.cost is not None:
        added = {it.id for it in rec.added}
        L.append(f"\n[추천 조합] {r.cost:,}원 · 단백질 {sum(it.protein_raw for it in r.items):.1f}g · "
                 f"{sum(it.kcal_raw for it in r.items):.0f}kcal"
                 + ("" if r.optimal else " (계산 시간 제한으로 최적 보장 안 됨)"))
        for it in r.items:
            L.append(f"  - {it.name} [{it.food_type}] {it.price:,}원 · 단백질 {it.protein_raw:g}g · {it.kcal_raw:g}kcal"
                     + ("  ← 추가됨" if it.id in added else ""))
        ex = [sum(getattr(it, k) for it in r.items) for k in ("carb", "fat", "sugar", "sodium")]
        L.append(f"  (탄수화물 {ex[0]:.0f}g · 지방 {ex[1]:.0f}g · 당류 {ex[2]:.0f}g · 나트륨 {ex[3]:.0f}mg)")
    for a in rec.alternatives:
        L.append("다른 선택지: " + a)
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-types", action="store_true")
    ap.add_argument("--types", nargs="*", default=None, help="체크한 식품 유형 (없으면 전체)")
    ap.add_argument("--protein", type=int, default=40)
    ap.add_argument("--kcal", type=int, nargs=2, default=[500, 800], metavar=("MIN", "MAX"))
    ap.add_argument("--carb-min", type=float); ap.add_argument("--carb-max", type=float)
    ap.add_argument("--fat-max", type=float); ap.add_argument("--sugar-max", type=float)
    ap.add_argument("--sodium-max", type=float)
    ap.add_argument("--algo", default="bnb", choices=["bnb", "dp", "greedy"])
    ap.add_argument("--out", help="결과를 파일로도 저장")
    a = ap.parse_args(argv)

    items = load_items(DATA)
    if a.list_types:
        text = "\n".join(f"{t}: {n}개" for t, n in sorted(Counter(it.food_type for it in items).items()))
    else:
        known = {it.food_type for it in items}
        bad = [t for t in (a.types or []) if t not in known]
        if bad:
            sys.exit("없는 유형: " + ", ".join(bad) + "  (--list-types 로 확인)")
        limits = Limits(a.carb_min, a.carb_max, a.fat_max, a.sugar_max, a.sodium_max)
        rec = recommend(items, a.types, a.protein, a.kcal[0], a.kcal[1], limits, a.algo)
        if rec.result is not None:
            check(rec.result, a.protein, a.kcal[0], a.kcal[1],
                  limits if rec.status != "relaxed" else Limits())
        text = format_rec(rec, a.protein, a.kcal[0], a.kcal[1], limits)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
