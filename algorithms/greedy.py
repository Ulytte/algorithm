# -*- coding: utf-8 -*-
"""
Greedy (탐욕 알고리즘)

1단계: 단백질 1g당 가격이 싼 순서로, 열량 상한(과 선택 조건 상한)을 넘지 않는 상품을 담는다.
       단백질 합이 R 이상이 되면 멈춘다.
2단계: 열량이 아직 C_min 보다 적으면(또는 탄수화물 하한이 모자라면), 남은 상품 중
       1kcal당 가격이 싼 순서로 상한을 넘지 않게 담는다.

시간 복잡도: 정렬 O(n log n)
한계: 한 번 담은 상품은 되돌리지 않는다.
  - 최적보다 비싼 조합을 낼 수 있다.
  - 해가 있는데도 못 찾을 수 있다 (예: 1단계에서 열량을 너무 써 버려서 2단계가 막히는 경우).
"""
import time
from .common import finish, usable, NO_LIMITS, ZERO4, add_extra


def greedy(items, R, c_min, c_max, limits=NO_LIMITS):
    t0 = time.perf_counter()
    items = usable(items, c_max, limits)
    chosen, used = [], set()
    p = k = 0
    ex = ZERO4

    def fits(it):
        return k + it.kcal <= c_max and limits.within_upper(add_extra(ex, it.extra()))

    # 1단계: 단백질 채우기 (1g당 가격 오름차순)
    by_protein = sorted((it for it in items if it.protein > 0), key=lambda it: it.price / it.protein)
    for it in by_protein:
        if p >= R:
            break
        if fits(it):
            chosen.append(it); used.add(it.id)
            p += it.protein; k += it.kcal; ex = add_extra(ex, it.extra())

    # 2단계: 열량 하한(+ 탄수화물 하한) 채우기 (1kcal당 가격 오름차순)
    def short():
        return k < c_min or (limits.carb_min is not None and ex[0] < limits.carb_min)

    if p >= R and short():
        by_kcal = sorted((it for it in items if it.id not in used and it.kcal > 0),
                         key=lambda it: it.price / it.kcal)
        for it in by_kcal:
            if not short():
                break
            if fits(it):
                chosen.append(it); used.add(it.id)
                p += it.protein; k += it.kcal; ex = add_extra(ex, it.extra())

    t1 = time.perf_counter()
    if p >= R and c_min <= k <= c_max and limits.satisfied(ex):
        return finish("Greedy", chosen, t0, t1, optimal=False)
    return finish("Greedy", None, t0, t1, optimal=False,
                  note=f"해를 못 찾음 (단백질 {p}g, 열량 {k}kcal에서 멈춤)")
