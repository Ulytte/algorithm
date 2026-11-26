# -*- coding: utf-8 -*-
"""
세 알고리즘이 같이 쓰는 부분: 상품 데이터 읽기, 결과 형식, 해 검증.

문제 정의
  상품마다 가격 c_i, 단백질 p_i, 열량 k_i 가 있고 각 상품은 최대 1번 고른다(0/1).
  단백질 합 >= R, C_min <= 열량 합 <= C_max 를 만족하면서 가격 합을 최소화한다.

정수화 (세 알고리즘 모두 같은 값을 쓴다 — 공정한 비교를 위해)
  - 단백질: g 단위 내림 (예: 9.9g -> 9g). 내림이라 실제 단백질은 항상 계산값 이상이다.
  - 열량: kcal 단위 반올림.
  DP가 정수 상태를 쓰기 때문에 정한 것이며, 원래 값은 protein_raw / kcal_raw 에 남긴다.
"""
import csv
import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Item:
    id: str            # item_id (행사 행은 '상품번호-개수')
    name: str
    price: int         # 이 행을 살 때 내는 돈 (행사면 행사 단위 가격)
    protein: int       # g, 내림
    kcal: int          # kcal, 반올림
    protein_raw: float
    kcal_raw: float
    category: str = ""
    event: str = ""
    food_type: str = ""
    carb: float = 0.0       # g
    fat: float = 0.0        # g
    sugar: float = 0.0      # g
    sodium: float = 0.0     # mg

    def extra(self):
        """선택 조건용 영양성분 (탄수화물, 지방, 당류, 나트륨)"""
        return (self.carb, self.fat, self.sugar, self.sodium)


@dataclass
class Limits:
    """
    사용자가 고르는 선택 조건 (None 이면 그 조건은 안 씀).
    필수 조건(단백질 R, 열량 C_min~C_max)은 따로 받는다.
    """
    carb_min: Optional[float] = None
    carb_max: Optional[float] = None
    fat_max: Optional[float] = None
    sugar_max: Optional[float] = None
    sodium_max: Optional[float] = None

    def active(self):
        return any(v is not None for v in (self.carb_min, self.carb_max, self.fat_max, self.sugar_max, self.sodium_max))

    def uppers(self):
        """(탄수화물, 지방, 당류, 나트륨) 상한. 없으면 무한대."""
        inf = float("inf")
        return tuple(inf if v is None else v for v in (self.carb_max, self.fat_max, self.sugar_max, self.sodium_max))

    def within_upper(self, sums):
        return all(s <= u + 1e-9 for s, u in zip(sums, self.uppers()))

    def satisfied(self, sums):
        return self.within_upper(sums) and (self.carb_min is None or sums[0] >= self.carb_min - 1e-9)

    def describe(self):
        parts = []
        if self.carb_min is not None or self.carb_max is not None:
            parts.append(f"탄수화물 {self.carb_min or 0:g}~{'' if self.carb_max is None else f'{self.carb_max:g}'}g")
        for name, v, unit in (("지방", self.fat_max, "g"), ("당류", self.sugar_max, "g"), ("나트륨", self.sodium_max, "mg")):
            if v is not None:
                parts.append(f"{name} ≤ {v:g}{unit}")
        return ", ".join(parts)


NO_LIMITS = Limits()


def add_extra(a, b):
    return tuple(x + y for x, y in zip(a, b))


ZERO4 = (0.0, 0.0, 0.0, 0.0)


@dataclass
class Result:
    algo: str
    cost: Optional[int]                 # 해를 못 찾으면 None
    items: List[Item] = field(default_factory=list)
    protein: int = 0
    kcal: int = 0
    feasible: bool = False
    optimal: Optional[bool] = None      # 최적이 보장되면 True, 아니면 False/None
    time_s: float = 0.0
    nodes: int = 0                      # B&B 방문 노드 수 / DP 상태 갱신 수 등
    note: str = ""


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0     # 값이 없으면 0 (실험 데이터는 4개 성분 모두 100% 채워져 있음)


def load_items(path):
    """data/selected/experiment_items.csv -> Item 리스트"""
    items = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            p_raw, k_raw = float(r["protein_g"]), float(r["kcal"])
            items.append(Item(
                id=r["item_id"], name=r["cu_name"], price=int(float(r["price"])),
                protein=int(math.floor(p_raw + 1e-9)), kcal=int(round(k_raw)),
                protein_raw=p_raw, kcal_raw=k_raw,
                category=r.get("category", ""), event=r.get("event", ""),
                food_type=r.get("food_type", ""),
                carb=_f(r.get("carb_g")), fat=_f(r.get("fat_g")),
                sugar=_f(r.get("sugar_g")), sodium=_f(r.get("sodium_mg")),
            ))
    return items


def usable(items, c_max, limits=NO_LIMITS):
    """혼자서도 열량·선택 상한을 넘는 상품, 가격이 0 이하인 상품은 어떤 해에도 못 들어가므로 미리 뺀다."""
    return [it for it in items
            if it.kcal <= c_max and it.price > 0 and limits.within_upper(it.extra())]


def check(result, R, c_min, c_max, limits=NO_LIMITS):
    """결과가 제약을 지키는지, 합계가 맞는지 다시 계산해서 확인 (알고리즘 버그 잡기용)."""
    if result.cost is None:
        return True
    ids = [it.id for it in result.items]
    assert len(ids) == len(set(ids)), f"{result.algo}: 같은 상품을 두 번 골랐음"
    cost = sum(it.price for it in result.items)
    p = sum(it.protein for it in result.items)
    k = sum(it.kcal for it in result.items)
    assert cost == result.cost, f"{result.algo}: 가격 합 불일치 {cost} != {result.cost}"
    assert p >= R and c_min <= k <= c_max, f"{result.algo}: 제약 위반 P={p} K={k}"
    ex = ZERO4
    for it in result.items:
        ex = add_extra(ex, it.extra())
    assert limits.satisfied(ex), f"{result.algo}: 선택 조건 위반 {ex}"
    return True


def finish(algo, chosen, t0, t1, **kw):
    """고른 상품 목록으로 Result를 만든다."""
    if chosen is None:
        return Result(algo, None, time_s=t1 - t0, **kw)
    return Result(algo, sum(it.price for it in chosen), list(chosen),
                  sum(it.protein for it in chosen), sum(it.kcal for it in chosen),
                  True, time_s=t1 - t0, **kw)
