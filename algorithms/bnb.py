# -*- coding: utf-8 -*-
"""
Branch & Bound (분기 한정법)

상품을 단백질 1g당 가격 오름차순으로 정렬한 뒤, 깊이 우선으로
'i번째 상품을 넣는다 / 안 넣는다' 두 갈래로 나눈다.

가지치기
  1) 열량이 C_max 를 넘으면 그 갈래는 버린다.
  2) 단백질 >= R, 열량 >= C_min 이 되면 그 자체로 해 (가격이 모두 양수라 더 담으면 비싸지기만 함).
  3) 하한(lower bound)이 지금까지 찾은 최선 가격 이상이면 버린다.
     하한 = 현재 가격 + max(단백질 하한, 열량 하한)
       - 단백질 하한: 남은 상품을 '쪼개서 살 수 있다'고 가정하고 1g당 싼 것부터
                      부족한 단백질만큼 사는 비용 (분수 배낭, 정렬돼 있어 이진 탐색으로 O(log n))
       - 열량 하한: 부족한 열량 x 남은 상품 중 가장 싼 1kcal당 가격
     남은 상품을 다 넣어도 단백질/열량이 모자라면 하한 = 무한대.

시간 복잡도: 최악 O(2^n). 실제로는 가지치기가 얼마나 잘 되느냐에 달렸다.
시간·노드 제한에 걸리면 그때까지 찾은 최선해를 내고 optimal=False 로 표시한다.
"""
import sys
import time
from bisect import bisect_left
from .common import finish, usable, NO_LIMITS, ZERO4

INF = float("inf")


class _Stop(Exception):
    pass


def bnb(items, R, c_min, c_max, limits=NO_LIMITS, initial=None, time_limit=60.0, node_limit=50_000_000):
    """
    initial: 처음 최선해로 쓸 Result (예: Greedy 결과). 있으면 가지치기가 빨라진다.
    limits : 선택 조건. 상한(탄수화물·지방·당류·나트륨)을 넘으면 그 갈래를 버리고,
             탄수화물 하한은 '해' 판정에 넣는다. 조건이 늘어도 상태 공간이 커지지 않는다는 점이 DP와 다르다.
    """
    t0 = time.perf_counter()
    items = usable(items, c_max, limits)
    uppers = limits.uppers()
    carb_min = limits.carb_min if limits.carb_min is not None else 0.0
    use_extra = limits.active()
    order = sorted(items, key=lambda it: it.price / it.protein if it.protein > 0 else INF)
    n = len(order)

    # 앞에서부터 누적합: 분수 배낭 하한 계산용
    P = [0] * (n + 1)
    C = [0] * (n + 1)
    for i, it in enumerate(order):
        P[i + 1] = P[i] + it.protein
        C[i + 1] = C[i] + it.price
    # 뒤에서부터: 남은 열량 합, 남은 상품 중 1kcal당 최저가
    suf_k = [0] * (n + 1)
    suf_rk = [INF] * (n + 1)
    suf_carb = [0.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        it = order[i]
        suf_k[i] = suf_k[i + 1] + it.kcal
        suf_rk[i] = min(suf_rk[i + 1], it.price / it.kcal if it.kcal > 0 else INF)
        suf_carb[i] = suf_carb[i + 1] + it.carb

    def lower_bound(i, cost, p, k, ex):
        if ex[0] + suf_carb[i] < carb_min - 1e-9:      # 남은 걸 다 넣어도 탄수화물 하한 미달
            return INF
        lb_p = 0.0
        d = R - p
        if d > 0:
            m = bisect_left(P, P[i] + d, lo=i + 1)      # i..m-1 까지 사면 d 이상
            if m > n:
                return INF
            last = order[m - 1]
            lb_p = (C[m - 1] - C[i]) + (P[i] + d - P[m - 1]) * last.price / last.protein
        lb_k = 0.0
        e = c_min - k
        if e > 0:
            if suf_k[i] < e:
                return INF
            lb_k = e * suf_rk[i]
        return cost + max(lb_p, lb_k)

    best = [INF, None]
    if initial is not None and initial.cost is not None:
        best = [initial.cost, list(initial.items)]
    path = []
    nodes = [0]

    def dfs(i, cost, p, k, ex):
        nodes[0] += 1
        if nodes[0] % 20000 == 0:
            if nodes[0] >= node_limit or time.perf_counter() - t0 > time_limit:
                raise _Stop
        if p >= R and k >= c_min and ex[0] >= carb_min - 1e-9:     # 해 발견
            if cost < best[0]:
                best[0], best[1] = cost, list(path)
            return
        if i == n or lower_bound(i, cost, p, k, ex) >= best[0]:
            return
        it = order[i]
        if k + it.kcal <= c_max:                # 넣는 갈래 먼저 (좋은 해를 빨리 찾기 위해)
            nex = ex
            ok = True
            if use_extra:
                nex = (ex[0] + it.carb, ex[1] + it.fat, ex[2] + it.sugar, ex[3] + it.sodium)
                ok = all(s <= u + 1e-9 for s, u in zip(nex, uppers))
            if ok:
                path.append(it)
                dfs(i + 1, cost + it.price, p + it.protein, k + it.kcal, nex)
                path.pop()
        dfs(i + 1, cost, p, k, ex)              # 안 넣는 갈래

    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, n + 1000))
    stopped = False
    try:
        dfs(0, 0, 0, 0, ZERO4)
    except _Stop:
        stopped = True
    finally:
        sys.setrecursionlimit(old_limit)

    t1 = time.perf_counter()
    note = f"제한 도달 ({'시간' if t1 - t0 > time_limit else '노드'}) - 최적 보장 안 됨" if stopped else ""
    if best[1] is None:
        return finish("B&B", None, t0, t1, optimal=not stopped, nodes=nodes[0], note=note or "해 없음")
    return finish("B&B", best[1], t0, t1, optimal=not stopped, nodes=nodes[0], note=note)
