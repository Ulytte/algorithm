# -*- coding: utf-8 -*-
"""
사용자 요청 처리: 체크리스트(식품 유형) + 조건 -> 추천 조합 + 이유 설명

순서
  1) 체크한 유형의 상품만으로 최저가 조합을 찾는다.
  2) 없으면 왜 없는지 진단하고, 체크하지 않은 유형의 상품을 '최소 개수만' 추가한 조합을 찾는다.
     (방법: 체크 밖 상품 가격에 아주 큰 벌점 BIG 을 더해서 푼다
            -> 추가 개수가 가장 적은 조합 중 가장 싼 것이 나온다. 알고리즘은 그대로 쓴다.)
  3) 그래도 없으면 선택 조건을 하나씩 빼 보고, 빼면 가능한 조건을 알려준다.
  4) 그래도 없으면 '조합 없음'과 이유를 알려준다.
"""
from dataclasses import dataclass, field, replace
from typing import List, Optional

from .common import Limits, NO_LIMITS, Result, usable
from .greedy import greedy
from .dp import dp_solve
from .bnb import bnb

BIG = 10 ** 8     # 체크 밖 상품 벌점. 어떤 조합의 실제 가격 합보다도 커야 한다.


@dataclass
class Recommendation:
    status: str                         # ok / expanded / relaxed / none
    result: Optional[Result] = None     # 실제 가격 기준 결과
    added: List = field(default_factory=list)     # 체크 밖에서 추가된 상품
    messages: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)


def _solve(items, R, c_min, c_max, limits, algo):
    """algo: 'bnb'(기본) / 'dp' / 'greedy'. DP는 선택 조건이 있으면 B&B로 대신한다."""
    if algo == "greedy":
        return greedy(items, R, c_min, c_max, limits), ""
    if algo == "dp":
        if not limits.active():
            return dp_solve(items, R, c_min, c_max), ""
        algo_note = "선택 조건이 있어 DP 대신 B&B로 계산했어요."
    else:
        algo_note = ""
    g = greedy(items, R, c_min, c_max, limits)
    return bnb(items, R, c_min, c_max, limits, initial=g), algo_note


def diagnose(pool, R, c_min, c_max, limits):
    """조합이 없는 이유를 사람이 읽을 수 있게 설명"""
    if not pool:
        return ["체크한 유형에 해당하는 상품이 없어요."]
    msgs = []
    cand = usable(pool, c_max, limits)
    if len(cand) < len(pool):
        msgs.append(f"{len(pool) - len(cand)}개 상품은 1개만으로도 열량 상한{'이나 선택 조건' if limits.active() else ''}을 넘어서 쓸 수 없어요.")
    if not cand:
        return msgs + ["남는 상품이 없어요."]
    tot_p = sum(it.protein for it in cand)
    tot_k = sum(it.kcal for it in cand)
    if tot_p < R:
        msgs.append(f"쓸 수 있는 상품을 전부 사도 단백질이 {tot_p}g이라 {R}g을 못 채워요.")
    if tot_k < c_min:
        msgs.append(f"쓸 수 있는 상품을 전부 사도 열량이 {tot_k}kcal이라 {c_min}kcal을 못 채워요.")
    if limits.carb_min is not None and sum(it.carb for it in cand) < limits.carb_min:
        msgs.append(f"전부 사도 탄수화물이 {limits.carb_min:g}g에 못 미쳐요.")
    if tot_p >= R:
        # 단백질 R 을 채우는 데 필요한 최소 열량 (상품을 쪼갤 수 있다고 본 하한)
        need, kcal = R, 0.0
        for it in sorted((x for x in cand if x.protein > 0), key=lambda x: x.kcal / x.protein):
            take = min(1.0, need / it.protein)
            kcal += take * it.kcal
            need -= take * it.protein
            if need <= 0:
                break
        if kcal > c_max:
            msgs.append(f"단백질 {R}g을 채우려면 열량이 최소 약 {kcal:.0f}kcal 필요해서 상한 {c_max}kcal을 넘어요.")
    blocking = [m for m in msgs if "쓸 수 없어요" not in m]     # 앞의 '제외된 상품 수'는 참고 정보
    if not blocking:
        msgs.append("남은 상품으로는 단백질·열량·선택 조건을 동시에 맞추는 조합이 없어요 (하나를 맞추면 다른 조건을 넘어요).")
    return msgs


def _actual(result, original):
    """벌점 가격으로 푼 결과를 실제 가격 상품으로 되돌린다."""
    if result.cost is None:
        return result
    chosen = [original[it.id] for it in result.items]
    return replace(result, items=chosen, cost=sum(it.price for it in chosen))


def recommend(items, types, R, c_min, c_max, limits=NO_LIMITS, algo="bnb"):
    """
    items: 전체 상품 / types: 체크한 식품 유형 목록 (None 또는 빈 목록이면 전체)
    """
    all_types = {it.food_type for it in items}
    checked = set(types) if types else set(all_types)
    whole = checked >= all_types
    pool = [it for it in items if it.food_type in checked]
    rec = Recommendation("none")

    # 1) 체크한 유형 안에서
    res, note = _solve(pool, R, c_min, c_max, limits, algo)
    if note:
        rec.messages.append(note)
    if res.cost is not None:
        rec.status, rec.result = "ok", res
        rec.messages.append("체크한 유형 안에서 찾은 최저가 조합이에요." if not whole else "전체 상품 중 최저가 조합이에요.")
        return rec

    reasons = diagnose(pool, R, c_min, c_max, limits)
    rec.messages.append(("체크한 유형만으로는" if not whole else "전체 상품으로도") + " 조건을 만족하는 조합이 없어요.")
    rec.messages += ["  - " + m for m in reasons]

    # 2) 체크 밖 유형을 최소 개수만 추가
    original = {it.id: it for it in items}
    penalized = [it if it.food_type in checked else replace(it, price=it.price + BIG) for it in items]
    if not whole:
        res2, _ = _solve(penalized, R, c_min, c_max, limits, algo)
        if res2.cost is not None:
            res2 = _actual(res2, original)
            rec.status, rec.result = "expanded", res2
            rec.added = [it for it in res2.items if it.food_type not in checked]
            kinds = sorted({it.food_type for it in rec.added})
            rec.messages.append(f"그래서 체크하지 않은 유형({', '.join(kinds)})에서 {len(rec.added)}개를 추가했어요. "
                                "추가하는 개수를 가장 적게 하고, 그중 가장 싼 조합이에요.")
            if len(rec.added) == len(res2.items):
                rec.messages.append("체크한 유형의 상품은 이 조합에 들어가지 못했어요.")
            return rec

    # 3) 선택 조건을 하나씩 빼 보기
    if limits.active():
        names = [("carb_min", "탄수화물 하한"), ("carb_max", "탄수화물 상한"), ("fat_max", "지방 상한"),
                 ("sugar_max", "당류 상한"), ("sodium_max", "나트륨 상한")]
        options = []
        for key, label in names:
            if getattr(limits, key) is None:
                continue
            relaxed = replace(limits, **{key: None})
            r3, _ = _solve(penalized, R, c_min, c_max, relaxed, algo)
            if r3.cost is not None:
                options.append((_actual(r3, original), label))
        if options:
            options.sort(key=lambda x: x[0].cost)
            best, label = options[0]
            rec.status, rec.result = "relaxed", best
            rec.added = [it for it in best.items if it.food_type not in checked]
            rec.messages.append(f"상품을 추가해도 안 돼서 '{label}' 조건을 빼고 찾았어요.")
            if rec.added:
                rec.messages.append(f"체크하지 않은 유형에서 {len(rec.added)}개도 추가됐어요.")
            rec.alternatives = [f"'{lb}' 조건을 빼면 {r.cost:,}원 조합이 가능해요." for r, lb in options[1:]]
            return rec

    # 4) 정말 없음
    if not whole:
        rec.messages.append("전체 상품으로 넓혀도 조합이 없어요.")
        rec.messages += ["  - " + m for m in diagnose(items, R, c_min, c_max, limits)]
    rec.messages.append("단백질 기준을 낮추거나 열량 범위를 넓혀 보세요.")
    return rec
