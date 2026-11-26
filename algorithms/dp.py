# -*- coding: utf-8 -*-
"""
DP (동적 계획법)

상태: dp[p][k] = 단백질 p, 열량 정확히 k 를 만드는 최소 가격
  - p 는 R 에서 자른다 (R 이상은 전부 R 로 취급) -> 행 수 R+1
  - k 는 0 ~ C_max -> 열 수 C_max+1
전이 (상품 i 를 고르는 경우):
  dp'[min(R, p + p_i)][k + k_i] = min(dp'[...], dp[p][k] + c_i)
답: min{ dp[R][k] : C_min <= k <= C_max }

시간 복잡도: O(n * R * C_max), 공간: O((R+1)(C_max+1)) + 역추적 기록

역추적
  상품마다 '이 상품을 골라서 값이 좋아진 칸'만 기록한다.
  - p < R 인 행: 이전 칸이 (p - p_i, k - k_i) 하나로 정해진다.
  - p = R 행: 이전 단백질이 R - p_i ~ R 중 어느 것이었는지 모르므로 따로 기록한다.
"""
import time
from array import array
from bisect import bisect_left
from .common import finish, usable, NO_LIMITS

INF = 10 ** 15


class LimitsNotSupported(Exception):
    """선택 조건(탄수화물·지방·당류·나트륨)이 있으면 DP 상태에 차원이 하나씩 늘어나야 해서 지원하지 않는다."""


def _has(arr, x):
    """정렬된 array 안에 x 가 있는지 (이진 탐색)"""
    i = bisect_left(arr, x)
    return i < len(arr) and arr[i] == x


def dp_solve(items, R, c_min, c_max, limits=NO_LIMITS):
    if limits.active():
        # 예: 나트륨 상한 2000mg 을 1mg 단위로 넣으면 상태 수가 (R+1)(C_max+1) x 2001 배가 된다.
        raise LimitsNotSupported("DP는 단백질·열량 조건만 지원합니다 (선택 조건은 B&B 사용)")
    t0 = time.perf_counter()
    items = usable(items, c_max)
    K = c_max
    dp = [[INF] * (K + 1) for _ in range(R + 1)]
    dp[0][0] = 0
    history = []       # 상품별 (changed, r_prev)
    updates = 0

    for it in items:
        c, pi, ki = it.price, min(it.protein, R), it.kcal
        n = K + 1 - ki                    # 이 상품을 더할 수 있는 열량 칸 수 (k = ki .. K)
        changed = {}                      # p(<R) -> 좋아진 칸의 j 목록 (k = ki + j)
        r_prev = {}                       # R 행에서 좋아진 칸 j -> 이전 단백질 값

        # (1) R 행: 이전 단백질 pp 가 R-pi ~ R 인 모든 행에서 올 수 있다. (이전 값만 읽음)
        best = dp[R][ki:]
        for pp in range(max(0, R - pi), R + 1):
            src = dp[pp]
            for j in [j for j, (a, b) in enumerate(zip(best, src)) if b + c < a]:
                best[j] = src[j] + c
                r_prev[j] = pp

        # (2) p < R 행: 이전 칸은 (p - pi, k - ki). 큰 p 부터 갱신하면 아직 안 바뀐 행을 읽는다.
        for p in range(R - 1, pi - 1, -1):
            row = dp[p]
            src = dp[p - pi] if pi > 0 else row[:]      # pi=0 이면 자기 행을 읽으므로 복사본 사용
            seg = row[ki:]
            idx = [j for j, (a, b) in enumerate(zip(seg, src)) if b + c < a]
            if idx:
                for j in idx:
                    row[ki + j] = src[j] + c
                changed[p] = array("H", idx)
                updates += len(idx)

        # R 행 반영은 (2) 이후에 해도 되고 먼저 해도 된다 ((2)는 R 행을 읽지 않음)
        if r_prev:
            rowR = dp[R]
            for j in r_prev:
                rowR[ki + j] = best[j]
            updates += len(r_prev)
        history.append((changed, r_prev))

    # 답 찾기
    rowR = dp[R]
    k_best = min(range(c_min, K + 1), key=lambda k: rowR[k], default=None) if c_min <= K else None
    if k_best is None or rowR[k_best] >= INF:
        return finish("DP", None, t0, time.perf_counter(), optimal=True, nodes=updates, note="해 없음")
    best_cost = rowR[k_best]

    # 역추적: 마지막 상품부터 거꾸로
    chosen, p, k = [], R, k_best
    for it, (changed, r_prev) in zip(reversed(items), reversed(history)):
        j = k - it.kcal
        if j < 0:
            continue
        if p == R:
            if j in r_prev:
                chosen.append(it); p = r_prev[j]; k = j
        else:
            arr = changed.get(p)
            if arr is not None and _has(arr, j):
                chosen.append(it); p = p - min(it.protein, R); k = j
    assert p == 0 and k == 0, "역추적 실패"

    res = finish("DP", chosen[::-1], t0, time.perf_counter(), optimal=True, nodes=updates)
    assert res.cost == best_cost
    return res
