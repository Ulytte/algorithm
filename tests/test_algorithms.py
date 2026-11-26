# -*- coding: utf-8 -*-
"""
정확성 검증: 작은 입력에서 완전 탐색(2^n)과 비교한다.

  - DP, B&B: 완전 탐색과 최소 가격이 같아야 한다 (해가 없으면 둘 다 없어야 함).
  - Greedy: 해를 냈다면 제약을 지켜야 하고, 가격은 최적 이상이어야 한다.
  - 모든 결과는 common.check 로 합계·제약을 다시 계산해서 확인한다.

입력: 실제 CU 데이터(experiment_items.csv)에서 무작위로 뽑은 n개 + 무작위 조건
실행: python -I tests/test_algorithms.py
"""
import os
import random
import sys
from itertools import combinations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 윈도 콘솔(cp949)에서 깨짐 방지
from algorithms import load_items, greedy, dp_solve, bnb, check, Limits, NO_LIMITS, recommend  # noqa: E402

DATA = os.path.join(ROOT, "data", "selected", "experiment_items.csv")


def brute_force(items, R, c_min, c_max, limits=NO_LIMITS):
    best = None
    for r in range(1, len(items) + 1):
        for comb in combinations(items, r):
            k = sum(it.kcal for it in comb)
            if k > c_max or k < c_min or sum(it.protein for it in comb) < R:
                continue
            ex = tuple(sum(getattr(it, a) for it in comb) for a in ("carb", "fat", "sugar", "sodium"))
            if not limits.satisfied(ex):
                continue
            c = sum(it.price for it in comb)
            if best is None or c < best:
                best = c
    return best


def main(cases=300, seed=2026):
    all_items = load_items(DATA)
    rnd = random.Random(seed)
    stats = {"cases": 0, "feasible": 0, "greedy_opt": 0, "greedy_worse": 0, "greedy_fail": 0}
    for t in range(cases):
        n = rnd.randint(4, 14)
        items = rnd.sample(all_items, n)
        R = rnd.randint(5, 60)
        c_min = rnd.randint(100, 700)
        c_max = c_min + rnd.randint(0, 500)

        opt = brute_force(items, R, c_min, c_max)
        g = greedy(items, R, c_min, c_max)
        d = dp_solve(items, R, c_min, c_max)
        b = bnb(items, R, c_min, c_max, initial=g)
        for res in (g, d, b):
            check(res, R, c_min, c_max)

        info = f"case {t}: n={n} R={R} C=[{c_min},{c_max}] opt={opt} DP={d.cost} B&B={b.cost} G={g.cost}"
        assert d.cost == opt, "DP 오답 " + info
        assert b.cost == opt and b.optimal, "B&B 오답 " + info
        if opt is None:
            assert g.cost is None, "Greedy가 없는 해를 냄 " + info
        else:
            stats["feasible"] += 1
            if g.cost is None:
                stats["greedy_fail"] += 1
            elif g.cost == opt:
                stats["greedy_opt"] += 1
            else:
                assert g.cost > opt, "Greedy가 최적보다 쌈?? " + info
                stats["greedy_worse"] += 1
        stats["cases"] += 1

    lines = [f"[기본 조건] 통과: {stats['cases']}개 사례 (해 있는 사례 {stats['feasible']}개)",
             "  DP, B&B: 모두 완전 탐색과 같은 최소 가격",
             f"  Greedy: 최적 {stats['greedy_opt']} / 더 비쌈 {stats['greedy_worse']} / 해 못 찾음 {stats['greedy_fail']}"]

    # 선택 조건(탄수화물·지방·당류·나트륨)이 있을 때: B&B 정확성 + Greedy 제약 준수
    feas = 0
    for t in range(cases):
        n = rnd.randint(4, 13)
        items = rnd.sample(all_items, n)
        R, c_min = rnd.randint(5, 50), rnd.randint(100, 600)
        c_max = c_min + rnd.randint(50, 500)
        lim = Limits(carb_min=rnd.choice([None, rnd.randint(10, 80)]), carb_max=rnd.choice([None, rnd.randint(60, 200)]),
                     fat_max=rnd.choice([None, rnd.randint(5, 40)]), sugar_max=rnd.choice([None, rnd.randint(5, 40)]),
                     sodium_max=rnd.choice([None, rnd.randint(300, 2000)]))
        opt = brute_force(items, R, c_min, c_max, lim)
        g = greedy(items, R, c_min, c_max, lim)
        b = bnb(items, R, c_min, c_max, lim, initial=g)
        check(g, R, c_min, c_max, lim); check(b, R, c_min, c_max, lim)
        assert b.cost == opt, f"B&B(선택 조건) 오답 case {t}: opt={opt} B&B={b.cost} {lim}"
        assert g.cost is None or (opt is not None and g.cost >= opt)
        feas += opt is not None
    lines.append(f"[선택 조건 포함] 통과: {cases}개 사례 (해 있는 사례 {feas}개) — B&B가 완전 탐색과 모두 일치")

    # 추천(체크리스트 + 대체 조합): 체크 안에서 해가 있으면 체크 밖 상품이 없어야 하고,
    # 확장한 경우 추가 개수가 최소인지 완전 탐색으로 확인
    for t in range(100):
        items = rnd.sample(all_items, rnd.randint(6, 12))
        types = list({it.food_type for it in items})
        checked = rnd.sample(types, max(1, len(types) // 2))
        R, c_min = rnd.randint(5, 40), rnd.randint(100, 500)
        c_max = c_min + rnd.randint(100, 400)
        rec = recommend(items, checked, R, c_min, c_max)
        inside = [it for it in items if it.food_type in checked]
        opt_in = brute_force(inside, R, c_min, c_max)
        if opt_in is not None:
            assert rec.status == "ok" and rec.result.cost == opt_in and not rec.added
        elif rec.status == "expanded":
            check(rec.result, R, c_min, c_max)
            # 완전 탐색: (체크 밖 상품 수, 가격)이 사전식으로 가장 작은 해와 같아야 함
            best = None
            for r in range(1, len(items) + 1):
                for comb in combinations(items, r):
                    k = sum(it.kcal for it in comb)
                    if c_min <= k <= c_max and sum(it.protein for it in comb) >= R:
                        key = (sum(it.food_type not in checked for it in comb), sum(it.price for it in comb))
                        best = key if best is None or key < best else best
            assert (len(rec.added), rec.result.cost) == best, f"추천 확장 오답 case {t}: {best} vs {len(rec.added), rec.result.cost}"
        else:
            assert brute_force(items, R, c_min, c_max) is None
    lines.append("[추천] 통과: 100개 사례 — 체크 안 해가 있으면 그대로, 없으면 추가 개수 최소 → 그중 최저가")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
