# -*- coding: utf-8 -*-
"""
비교 실험: 같은 입력에 Greedy / DP / B&B 를 돌려 가격(최적성)·실행 시간·메모리를 비교한다.

  - 조건(시나리오) 5개 x 상품 수 n 여러 개 x 시드 여러 개 (전체 데이터에서 무작위 추출)
    전체(n = 전체 상품 수)는 부분집합이 하나뿐이라 시드 1개
  - 시간: 같은 입력을 REPEAT 번 돌려 중앙값 (데이터 읽기·부분집합 뽑기 시간은 빼고 알고리즘만 잰다)
    한 번에 0.5초를 넘으면 한 번만 잰다
  - 메모리: 시간 측정과 따로 한 번 더 돌려 tracemalloc 최대치 (tracemalloc 이 느려서 시간과 섞지 않음, n마다 첫 시드만)
  - B&B 는 Greedy 결과를 초기 최선해로 받는다 (Greedy 시간은 1~3ms 수준이라 따로 더하지 않음).
    시간 제한을 넘으면 '최적 보장 안 됨'으로 기록한다.
  - 정답 검증: DP 와 B&B 가격이 같은지 확인하고, n <= BRUTE_N 이면 완전탐색과도 비교한다.
  - 결과: results/experiment_results.csv, results/experiment_summary.md,
          results/experiment_subsets.json (웹 비교 페이지에서 같은 부분집합을 다시 쓰기 위함)

실행: python -I scripts/run_experiment.py [--quick]
"""
import csv
import json
import os
import random
import statistics
import sys
import time
import tracemalloc
from itertools import combinations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 윈도 콘솔(cp949)에서 깨짐 방지
from algorithms import load_items, greedy, dp_solve, bnb, check  # noqa: E402

DATA = os.path.join(ROOT, "data", "selected", "experiment_items.csv")
OUT = os.path.join(ROOT, "results")

# (이름, 단백질 하한 R, 칼로리 하한, 칼로리 상한) — 실험용 입력 조건 (제안 값, 영양 권장량 아님)
SCENARIOS = [
    ("가벼운 한 끼", 20, 300, 500),
    ("일반 한 끼", 40, 500, 800),
    ("운동 후 한 끼", 60, 600, 900),
    ("고단백 한 끼", 80, 700, 1000),
    ("고단백·저칼로리", 60, 300, 500),
]
SIZES = [10, 20, 30, 40, 50, 100, 200, 500, 1000, None]     # None = 전체
SEEDS = 5
REPEAT = 3
BRUTE_N = 10
BNB_TIME_LIMIT = 30.0


def subset_seed(size, s):
    return 1000 * s + size


def brute(items, R, cmin, cmax):
    """완전탐색: 모든 부분집합 중 조건을 만족하는 최저가 (작은 n 검증용)"""
    best = None
    for r in range(1, len(items) + 1):
        for comb in combinations(items, r):
            p = sum(it.protein for it in comb)
            k = sum(it.kcal for it in comb)
            if p >= R and cmin <= k <= cmax:
                c = sum(it.price for it in comb)
                if best is None or c < best:
                    best = c
    return best


def timed(fn, repeat):
    """repeat 번 돌려 마지막 결과와 시간 중앙값.
    한 번에 0.5초 넘게 걸리면(큰 n 의 DP) 잡음 영향이 작으므로 한 번만 잰다."""
    times, res = [], None
    for _ in range(repeat):
        res = fn()
        times.append(res.time_s)
        if res.time_s > 0.5:
            break
    return res, statistics.median(times)


def peak_kb(fn):
    tracemalloc.start()
    fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return round(peak / 1024, 1)


def main():
    quick = "--quick" in sys.argv
    all_items = load_items(DATA)
    N = len(all_items)
    sizes = [10, 100, None] if quick else SIZES
    seeds = 1 if quick else SEEDS
    repeat = 1 if quick else REPEAT
    os.makedirs(OUT, exist_ok=True)
    rows, subsets = [], {}
    started = time.strftime("%Y-%m-%d %H:%M")
    for size in sizes:
        for s in (range(1) if size is None else range(seeds)):
            if size is None:
                items = all_items
            else:
                items = random.Random(subset_seed(size, s)).sample(all_items, size)
                subsets[f"{size}-{s}"] = [it.id for it in items]
            n = len(items)
            for name, R, cmin, cmax in SCENARIOS:
                g, gt = timed(lambda: greedy(items, R, cmin, cmax), repeat)
                d, dt = timed(lambda: dp_solve(items, R, cmin, cmax), repeat)
                b, bt = timed(lambda: bnb(items, R, cmin, cmax, initial=g, time_limit=BNB_TIME_LIMIT), repeat)
                for res in (g, d, b):
                    check(res, R, cmin, cmax)
                # 메모리는 tracemalloc 이 DP 를 몇 배 느리게 만들어서 n마다 첫 시드에서만 잰다
                mem = {"Greedy": "", "DP": "", "B&B": ""}
                if s == 0:
                    mem = {"Greedy": peak_kb(lambda: greedy(items, R, cmin, cmax)),
                           "DP": peak_kb(lambda: dp_solve(items, R, cmin, cmax)),
                           "B&B": peak_kb(lambda: bnb(items, R, cmin, cmax, initial=g, time_limit=BNB_TIME_LIMIT))}
                opt = d.cost
                if b.optimal and b.cost != opt:
                    raise AssertionError(f"DP {opt} != B&B {b.cost} ({name}, n={n}, seed={s})")
                bf = ""
                if n <= BRUTE_N:
                    bf = brute(items, R, cmin, cmax)
                    if bf != opt:
                        raise AssertionError(f"완전탐색 {bf} != DP {opt} ({name}, n={n}, seed={s})")
                    bf = "일치"
                for res, t in ((g, gt), (d, dt), (b, bt)):
                    gap = "" if res.cost is None or opt is None else round((res.cost - opt) / opt * 100, 2)
                    rows.append({
                        "scenario": name, "R": R, "c_min": cmin, "c_max": cmax, "n": n,
                        "seed": "" if size is None else s, "algo": res.algo,
                        "cost": "" if res.cost is None else res.cost,
                        "opt_cost": "" if opt is None else opt,
                        "gap_pct": gap, "feasible": res.cost is not None, "optimal_guaranteed": res.optimal,
                        "protein": res.protein if res.cost is not None else "",
                        "kcal": res.kcal if res.cost is not None else "",
                        "n_items": len(res.items), "time_ms": round(t * 1000, 4), "nodes": res.nodes,
                        "peak_kb": mem[res.algo], "brute_check": bf, "note": res.note,
                        "chosen_ids": " ".join(it.id for it in res.items),
                        "chosen": " + ".join(it.name for it in res.items),
                    })
                print(f"n={n} s={s} {name}: G={g.cost} ({gt*1000:.2f}ms) DP={d.cost} ({dt*1000:.1f}ms) "
                      f"B&B={b.cost} ({bt*1000:.2f}ms, {b.nodes} nodes{', 중단' if not b.optimal else ''})", flush=True)

    with open(os.path.join(OUT, "experiment_results.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    meta = {"started": started, "finished": time.strftime("%Y-%m-%d %H:%M"), "n_all": N,
            "seeds": seeds, "repeat": repeat, "brute_n": BRUTE_N, "bnb_time_limit_s": BNB_TIME_LIMIT,
            "python": sys.version.split()[0], "scenarios": SCENARIOS}
    with open(os.path.join(OUT, "experiment_subsets.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "subsets": subsets}, f, ensure_ascii=False)
    write_summary(rows, meta)


def write_summary(rows, meta):
    L = ["# 비교 실험 결과", "",
         f"- 데이터: experiment_items.csv (CU 상품 {meta['n_all']}개, 상품당 1행, 행사 반영) / 실행: {meta['started']} ~ {meta['finished']}",
         f"- 부분집합: n마다 시드 {meta['seeds']}개 (전체는 1개), 시간은 {meta['repeat']}번 중앙값(ms), Python {meta['python']}",
         f"- B&B 시간 제한 {meta['bnb_time_limit_s']:.0f}초, n ≤ {meta['brute_n']} 은 완전탐색과 대조",
         "- gap = (Greedy 가격 - 최적 가격) / 최적 가격. 표의 값은 시드 평균(해가 있는 경우만)", ""]
    groups = {}
    for r in rows:
        groups.setdefault((r["scenario"], r["n"]), []).append(r)
    L += ["| 조건 | n | 해 있음 | Greedy 해 찾음 | Greedy 최적 | 평균 gap | Greedy ms | DP ms | B&B ms | B&B 노드 | DP KB | B&B KB |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else ""
    for (sc, n), rs in groups.items():
        by = lambda a: [r for r in rs if r["algo"] == a]
        G, D, B = by("Greedy"), by("DP"), by("B&B")
        has = [d["cost"] != "" for d in D]
        gfound = [g["cost"] != "" for g, h in zip(G, has) if h]
        gopt = [g["gap_pct"] == 0 for g, h in zip(G, has) if h and g["cost"] != ""]
        gaps = [g["gap_pct"] for g in G if g["gap_pct"] != ""]
        L.append(f"| {sc} | {n} | {sum(has)}/{len(has)} | {sum(gfound)}/{sum(has)} | {sum(gopt)}/{sum(has)} | "
                 f"{'' if not gaps else str(mean(gaps)) + '%'} | {mean([r['time_ms'] for r in G])} | "
                 f"{mean([r['time_ms'] for r in D])} | {mean([r['time_ms'] for r in B])} | "
                 f"{mean([r['nodes'] for r in B])} | {mean([r['peak_kb'] for r in D if r['peak_kb'] != ''])} | "
                 f"{mean([r['peak_kb'] for r in B if r['peak_kb'] != ''])} |")
    open(os.path.join(OUT, "experiment_summary.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
