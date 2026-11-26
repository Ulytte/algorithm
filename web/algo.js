// 세 알고리즘 + 추천(체크 밖 추가·조건 완화) — algorithms/*.py 를 그대로 옮긴 것
// 상품 객체: {id, name, price, p(단백질 정수), k(칼로리 정수), pr, kr(원값), type, event, carb, fat, sugar, na, grade}
(function (global) {
  "use strict";
  const INF = Infinity;
  const BIG = 1e8; // 체크 밖 상품 벌점

  const now = () => performance.now();
  const extra = (it) => [it.carb, it.fat, it.sugar, it.na];
  const add4 = (a, it) => [a[0] + it.carb, a[1] + it.fat, a[2] + it.sugar, a[3] + it.na];

  // ---- 선택 조건 ----
  function active(L) {
    return ["carbMin", "carbMax", "fatMax", "sugarMax", "naMax"].some((k) => L[k] != null);
  }
  function uppers(L) {
    return [L.carbMax, L.fatMax, L.sugarMax, L.naMax].map((v) => (v == null ? INF : v));
  }
  function withinUpper(L, s) {
    const u = uppers(L);
    return s.every((v, i) => v <= u[i] + 1e-9);
  }
  function satisfied(L, s) {
    return withinUpper(L, s) && (L.carbMin == null || s[0] >= L.carbMin - 1e-9);
  }
  const NO_LIMITS = {};

  function usable(items, cmax, L) {
    return items.filter((it) => it.k <= cmax && it.price > 0 && withinUpper(L, extra(it)));
  }

  function finish(algo, chosen, t0, t1, kw) {
    const base = Object.assign({ algo, cost: null, items: [], protein: 0, kcal: 0, feasible: false,
      optimal: null, time: t1 - t0, nodes: 0, note: "" }, kw || {});
    if (!chosen) return base;
    base.items = chosen.slice();
    base.cost = chosen.reduce((s, it) => s + it.price, 0);
    base.protein = chosen.reduce((s, it) => s + it.p, 0);
    base.kcal = chosen.reduce((s, it) => s + it.k, 0);
    base.feasible = true;
    return base;
  }

  // ---- Greedy ----
  function greedy(items, R, cmin, cmax, L) {
    L = L || NO_LIMITS;
    const t0 = now();
    items = usable(items, cmax, L);
    const chosen = [], used = new Set();
    let p = 0, k = 0, ex = [0, 0, 0, 0];
    const fits = (it) => k + it.k <= cmax && withinUpper(L, add4(ex, it));
    const take = (it) => { chosen.push(it); used.add(it.id); p += it.p; k += it.k; ex = add4(ex, it); };

    // 1단계: 단백질 1g당 가격 오름차순
    const byP = items.filter((it) => it.p > 0).sort((a, b) => a.price / a.p - b.price / b.p);
    for (const it of byP) {
      if (p >= R) break;
      if (fits(it)) take(it);
    }
    // 2단계: 칼로리(+탄수화물 하한) 채우기, 1kcal당 가격 오름차순
    const short = () => k < cmin || (L.carbMin != null && ex[0] < L.carbMin);
    if (p >= R && short()) {
      const byK = items.filter((it) => !used.has(it.id) && it.k > 0).sort((a, b) => a.price / a.k - b.price / b.k);
      for (const it of byK) {
        if (!short()) break;
        if (fits(it)) take(it);
      }
    }
    const t1 = now();
    if (p >= R && cmin <= k && k <= cmax && satisfied(L, ex)) return finish("Greedy", chosen, t0, t1, { optimal: false });
    return finish("Greedy", null, t0, t1, { optimal: false, note: `해를 못 찾음 (단백질 ${p}g, 칼로리 ${k}kcal에서 멈춤)` });
  }

  // ---- DP ----
  function bsearch(arr, x) {
    let lo = 0, hi = arr.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] < x) lo = m + 1; else hi = m; }
    return lo < arr.length && arr[lo] === x;
  }

  function dpSolve(items, R, cmin, cmax) {
    const t0 = now();
    items = usable(items, cmax, NO_LIMITS);
    const K = cmax, W = K + 1;
    const dp = [];
    for (let p = 0; p <= R; p++) dp.push(new Float64Array(W).fill(INF));
    dp[0][0] = 0;
    const history = [];
    let updates = 0;
    const Arr = W <= 65536 ? Uint16Array : Uint32Array;

    for (const it of items) {
      const c = it.price, pi = Math.min(it.p, R), ki = it.k, n = W - ki;
      const changed = new Map(); // p(<R) -> 좋아진 칸 j 목록 (k = ki + j)
      const rPrev = new Map();   // R 행 j -> 이전 단백질
      // (1) R 행: 이전 단백질 R-pi ~ R
      const rowR = dp[R];
      const best = rowR.slice(ki);
      for (let pp = Math.max(0, R - pi); pp <= R; pp++) {
        const src = dp[pp];
        for (let j = 0; j < n; j++) {
          const v = src[j] + c;
          if (v < best[j]) { best[j] = v; rPrev.set(j, pp); }
        }
      }
      // (2) p < R 행, 큰 p 부터
      for (let p = R - 1; p >= pi; p--) {
        const row = dp[p];
        const src = pi > 0 ? dp[p - pi] : row.slice();
        const idx = [];
        for (let j = 0; j < n; j++) {
          const v = src[j] + c;
          if (v < row[ki + j]) { row[ki + j] = v; idx.push(j); }
        }
        if (idx.length) { changed.set(p, Arr.from(idx)); updates += idx.length; }
      }
      for (const [j] of rPrev) rowR[ki + j] = best[j];
      updates += rPrev.size;
      history.push([changed, rPrev]);
    }

    const rowR = dp[R];
    let kBest = -1;
    for (let k = cmin; k <= K; k++) if (kBest < 0 || rowR[k] < rowR[kBest]) kBest = k;
    if (kBest < 0 || rowR[kBest] >= INF) return finish("DP", null, t0, now(), { optimal: true, nodes: updates, note: "해 없음" });

    const chosen = [];
    let p = R, k = kBest;
    for (let i = items.length - 1; i >= 0; i--) {
      const it = items[i], [changed, rPrev] = history[i];
      const j = k - it.k;
      if (j < 0) continue;
      if (p === R) {
        if (rPrev.has(j)) { chosen.push(it); p = rPrev.get(j); k = j; }
      } else {
        const arr = changed.get(p);
        if (arr && bsearch(arr, j)) { chosen.push(it); p = p - Math.min(it.p, R); k = j; }
      }
    }
    if (p !== 0 || k !== 0) throw new Error("DP 역추적 실패");
    return finish("DP", chosen.reverse(), t0, now(), { optimal: true, nodes: updates });
  }

  // ---- Branch & Bound ----
  function bnb(items, R, cmin, cmax, L, initial, timeLimitMs, nodeLimit) {
    L = L || NO_LIMITS;
    timeLimitMs = timeLimitMs || 10000;
    nodeLimit = nodeLimit || 50000000;
    const t0 = now();
    items = usable(items, cmax, L);
    const U = uppers(L);
    const carbMin = L.carbMin != null ? L.carbMin : 0;
    const useExtra = active(L);
    const order = items.slice().sort((a, b) => (a.p > 0 ? a.price / a.p : INF) - (b.p > 0 ? b.price / b.p : INF));
    const n = order.length;
    const P = new Float64Array(n + 1), C = new Float64Array(n + 1);
    for (let i = 0; i < n; i++) { P[i + 1] = P[i] + order[i].p; C[i + 1] = C[i] + order[i].price; }
    const sufK = new Float64Array(n + 1), sufRK = new Float64Array(n + 1).fill(INF), sufCarb = new Float64Array(n + 1);
    for (let i = n - 1; i >= 0; i--) {
      const it = order[i];
      sufK[i] = sufK[i + 1] + it.k;
      sufRK[i] = Math.min(sufRK[i + 1], it.k > 0 ? it.price / it.k : INF);
      sufCarb[i] = sufCarb[i + 1] + it.carb;
    }
    function lowerBound(i, cost, p, k, ex) {
      if (ex[0] + sufCarb[i] < carbMin - 1e-9) return INF;
      let lbP = 0;
      const d = R - p;
      if (d > 0) {
        const target = P[i] + d;
        let lo = i + 1, hi = n + 1; // bisect_left(P, target, lo=i+1)
        while (lo < hi) { const m = (lo + hi) >> 1; if (P[m] < target) lo = m + 1; else hi = m; }
        const m = lo;
        if (m > n) return INF;
        const last = order[m - 1];
        lbP = (C[m - 1] - C[i]) + (target - P[m - 1]) * last.price / last.p;
      }
      let lbK = 0;
      const e = cmin - k;
      if (e > 0) {
        if (sufK[i] < e) return INF;
        lbK = e * sufRK[i];
      }
      return cost + Math.max(lbP, lbK);
    }

    let bestCost = INF, bestItems = null;
    if (initial && initial.cost != null) { bestCost = initial.cost; bestItems = initial.items.slice(); }
    const path = [];
    let nodes = 0, stopped = false;
    const STOP = {};

    function dfs(i, cost, p, k, ex) {
      nodes++;
      if (nodes % 20000 === 0 && (nodes >= nodeLimit || now() - t0 > timeLimitMs)) throw STOP;
      if (p >= R && k >= cmin && ex[0] >= carbMin - 1e-9) {
        if (cost < bestCost) { bestCost = cost; bestItems = path.slice(); }
        return;
      }
      if (i === n || lowerBound(i, cost, p, k, ex) >= bestCost) return;
      const it = order[i];
      if (k + it.k <= cmax) {
        let nex = ex, ok = true;
        if (useExtra) {
          nex = add4(ex, it);
          ok = nex.every((s, t) => s <= U[t] + 1e-9);
        }
        if (ok) {
          path.push(it);
          dfs(i + 1, cost + it.price, p + it.p, k + it.k, nex);
          path.pop();
        }
      }
      dfs(i + 1, cost, p, k, ex);
    }
    try { dfs(0, 0, 0, 0, [0, 0, 0, 0]); } catch (e) { if (e === STOP) stopped = true; else throw e; }
    const t1 = now();
    const note = stopped ? `제한 도달 (${t1 - t0 > timeLimitMs ? "시간" : "노드"}) - 최적 보장 안 됨` : "";
    if (!bestItems) return finish("B&B", null, t0, t1, { optimal: !stopped, nodes, note: note || "해 없음" });
    return finish("B&B", bestItems, t0, t1, { optimal: !stopped, nodes, note });
  }

  // ---- B&B 상위 K개: 가격 상한 안의 조합을 최저가 순으로 ----
  // 조합 = 조건(단백질·칼로리·선택 조건)을 만족하고, 어느 상품 하나를 빼도 조건이 깨지는 상품 묶음 (제안).
  //   "최소 조합"만 세는 이유: 조건을 만족하는 조합에 껌 하나를 더 얹어도 조건은 계속 만족하므로,
  //   그런 조합까지 세면 목록이 '같은 조합 + 아무거나 1개'로 채워진다.
  //   칼로리 상한·영양 상한은 빼면 더 잘 지켜지고, 단백질·칼로리 하한은 더하면 더 잘 지켜지므로
  //   "하나씩 빼 보기"만 확인하면 어떤 부분집합도 조건을 만족하지 않는다는 뜻이 된다.
  // 가지치기: 하한 > 가격 상한이면 버림, 목록이 K개 찼으면 하한 >= K번째 가격일 때 버림.
  // Q (선택): {식품 유형: 개수} — 그 유형에서 정확히 그 개수(행 수)만큼 고른 조합만 센다.
  //   수량을 정한 유형의 상품은 빼면 개수가 깨지므로, '최소 조합' 확인은 수량을 안 정한 유형의 상품만 한다.
  //   (수량을 정한 상태에서도 '조건 만족하면 멈춤'이 모든 최소 조합을 찾는다는 성질은 그대로 성립)
  //   하한에는 '모자란 개수 x 남은 그 유형 상품 중 최저가'를 더 넣는다 (세 하한 중 최댓값 사용).
  // 같은 상품(묶음 id g)의 행(1개 / 행사 묶음 등)은 한 조합에 하나만 담는다.
  function bnbTopK(items, R, cmin, cmax, L, cap, K, Q, timeLimitMs, nodeLimit) {
    L = L || NO_LIMITS;
    cap = cap == null ? INF : cap;
    K = K || 20;
    timeLimitMs = timeLimitMs || 10000;
    nodeLimit = nodeLimit || 50000000;
    const t0 = now();
    items = usable(items, cmax, L).filter((it) => it.price <= cap);
    const U = uppers(L);
    const carbMin = L.carbMin != null ? L.carbMin : 0;
    const useExtra = active(L);
    const order = items.slice().sort((a, b) => (a.p > 0 ? a.price / a.p : INF) - (b.p > 0 ? b.price / b.p : INF));
    const n = order.length;
    const P = new Float64Array(n + 1), C = new Float64Array(n + 1);
    for (let i = 0; i < n; i++) { P[i + 1] = P[i] + order[i].p; C[i + 1] = C[i] + order[i].price; }
    const sufK = new Float64Array(n + 1), sufRK = new Float64Array(n + 1).fill(INF), sufCarb = new Float64Array(n + 1);
    for (let i = n - 1; i >= 0; i--) {
      const it = order[i];
      sufK[i] = sufK[i + 1] + it.k;
      sufRK[i] = Math.min(sufRK[i + 1], it.k > 0 ? it.price / it.k : INF);
      sufCarb[i] = sufCarb[i + 1] + it.carb;
    }
    // 수량 조건
    const qTypes = Q ? Object.keys(Q).filter((t) => Q[t] != null) : [];
    const qIdx = new Map(qTypes.map((t, j) => [t, j]));
    const need = qTypes.map((t) => Q[t]);
    const m = qTypes.length;
    const tIdx = order.map((it) => (qIdx.has(it.type) ? qIdx.get(it.type) : -1));
    const sufCnt = [], sufMin = [];
    for (let j = 0; j < m; j++) { sufCnt.push(new Int32Array(n + 1)); sufMin.push(new Float64Array(n + 1).fill(INF)); }
    for (let i = n - 1; i >= 0; i--) {
      for (let j = 0; j < m; j++) {
        const mine = tIdx[i] === j;
        sufCnt[j][i] = sufCnt[j][i + 1] + (mine ? 1 : 0);
        sufMin[j][i] = mine ? Math.min(sufMin[j][i + 1], order[i].price) : sufMin[j][i + 1];
      }
    }
    const cnt = new Int32Array(m);
    const countsDone = () => { for (let j = 0; j < m; j++) if (cnt[j] !== need[j]) return false; return true; };

    function lowerBound(i, cost, p, k, ex) {
      if (ex[0] + sufCarb[i] < carbMin - 1e-9) return INF;
      let lbQ = 0;
      for (let j = 0; j < m; j++) {
        const lack = need[j] - cnt[j];
        if (lack > 0) {
          if (sufCnt[j][i] < lack) return INF;
          lbQ += lack * sufMin[j][i];
        }
      }
      let lbP = 0;
      const d = R - p;
      if (d > 0) {
        const target = P[i] + d;
        let lo = i + 1, hi = n + 1;
        while (lo < hi) { const mid = (lo + hi) >> 1; if (P[mid] < target) lo = mid + 1; else hi = mid; }
        if (lo > n) return INF;
        const last = order[lo - 1];
        lbP = (C[lo - 1] - C[i]) + (target - P[lo - 1]) * last.price / last.p;
      }
      let lbK = 0;
      const e = cmin - k;
      if (e > 0) {
        if (sufK[i] < e) return INF;
        lbK = e * sufRK[i];
      }
      return cost + Math.max(lbP, lbK, lbQ);
    }

    const found = []; // 가격 오름차순, 최대 K개
    const pruneAt = () => (found.length < K ? cap : Math.min(cap, found[K - 1].cost - 1e-9));
    const path = [];
    const usedG = new Set(); // 지금 담은 상품 묶음 id (같은 상품은 한 행만)
    let nodes = 0, stopped = false;
    const STOP = {};
    function minimal(p, k, ex) {
      for (const it of path) {
        if (qIdx.has(it.type)) continue; // 수량을 정한 유형은 빼면 개수가 깨짐
        // 탄수화물 하한이 없으면 ex 가 누적되지 않으므로(useExtra=false) 탄수화물은 확인하지 않음
        if (p - it.p >= R && k - it.k >= cmin && (L.carbMin == null || ex[0] - it.carb >= carbMin - 1e-9)) return false;
      }
      return true;
    }
    // 같은 '모양'(유형·가격 묶음이 같은) 조합은 하나로 친다. 예: 닭가슴살 + 1,200원 라면 A / 라면 B.
    // 모양이 같으면 가격 합도 같으므로, 먼저 찾은 것 하나만 목록에 두고 나머지는 '바꿔 담기'로 보여준다.
    // 받는 개수(u)도 모양에 넣는다: 2+1 상품의 2개·3개처럼 값이 같아도 개수가 다르면 따로 보여준다
    const shapeKey = (its) => its.map((it) => it.type + "|" + it.price + "|" + (it.u || 1)).sort().join("/");
    const seen = new Set();
    function record(cost, p, k) {
      const key = shapeKey(path);
      if (seen.has(key)) return;
      const combo = { cost, items: path.slice(), protein: p, kcal: k, key };
      // 앞에 올 조합: 가격 낮은 것, 같으면 상품 수 적은 것
      let i = found.length;
      while (i > 0 && (found[i - 1].cost > cost || (found[i - 1].cost === cost && found[i - 1].items.length > combo.items.length))) i--;
      found.splice(i, 0, combo);
      seen.add(key);
      if (found.length > K) seen.delete(found.pop().key);
    }
    function dfs(i, cost, p, k, ex) {
      nodes++;
      if (nodes % 20000 === 0 && (nodes >= nodeLimit || now() - t0 > timeLimitMs)) throw STOP;
      const core = p >= R && k >= cmin && ex[0] >= carbMin - 1e-9;
      if (core && countsDone()) {
        // 더 담으면 같은 조합 + 군더더기가 되므로 여기서 멈춤
        if (cost <= pruneAt() && minimal(p, k, ex)) record(cost, p, k);
        return;
      }
      if (i === n || lowerBound(i, cost, p, k, ex) > pruneAt()) return;
      const it = order[i], j = tIdx[i];
      // 넣을 수 있는지: 칼로리 상한, 수량을 정한 유형이면 개수가 남았는지,
      // 단백질·칼로리는 이미 채웠고 개수만 모자라면 수량 정한 유형만 (다른 걸 넣으면 군더더기)
      // 같은 상품(묶음 id g)의 다른 행(1개 / 행사 묶음)이 이미 담겼으면 못 넣음
      const canAdd = k + it.k <= cmax && (j < 0 ? !core : cnt[j] < need[j]) && !(it.g && usedG.has(it.g));
      if (canAdd) {
        let nex = ex, ok = true;
        if (useExtra) {
          nex = add4(ex, it);
          ok = nex.every((s, t) => s <= U[t] + 1e-9);
        }
        if (ok) {
          path.push(it);
          if (j >= 0) cnt[j]++;
          if (it.g) usedG.add(it.g);
          dfs(i + 1, cost + it.price, p + it.p, k + it.k, nex);
          if (it.g) usedG.delete(it.g);
          if (j >= 0) cnt[j]--;
          path.pop();
        }
      }
      dfs(i + 1, cost, p, k, ex);
    }
    try { dfs(0, 0, 0, 0, [0, 0, 0, 0]); } catch (e) { if (e === STOP) stopped = true; else throw e; }
    const t1 = now();
    return { combos: found, nodes, time: t1 - t0, stopped, candidates: n,
      note: stopped ? `탐색 제한 도달 (${t1 - t0 > timeLimitMs ? "시간" : "노드"}) - 순위가 정확하지 않을 수 있어요` : "" };
  }

  // 조합의 상품 하나를 '같은 유형·같은 가격'의 다른 상품으로 바꿔도 조건을 지키는 후보들.
  // 같은 가격이라도 단백질·칼로리가 달라서 바꾸면 조건이 깨질 수 있으므로 하나씩 확인한다.
  // 확인하는 것: 단백질 하한, 칼로리 범위, 선택 조건, 최소 조합(군더더기 없음). 같은 유형끼리라 개수 조건은 그대로.
  // pinned: 사용자가 '꼭 넣기'한 상품 id — 바꿔 담기 후보를 만들지 않고, 빼 볼 대상도 아니다.
  function addAlternatives(combo, cand, R, cmin, cmax, L, Q, pinned) {
    pinned = pinned || new Set();
    const inCombo = new Set(combo.items.map((it) => it.id));
    const qset = new Set(Q ? Object.keys(Q).filter((t) => Q[t] != null) : []);
    const ok = (its) => {
      let p = 0, k = 0, ex = [0, 0, 0, 0];
      for (const it of its) { p += it.p; k += it.k; ex = add4(ex, it); }
      if (p < R || k < cmin || k > cmax || !satisfied(L, ex)) return false;
      for (const it of its) {
        if (qset.has(it.type) || pinned.has(it.id)) continue;
        if (p - it.p >= R && k - it.k >= cmin && (L.carbMin == null || ex[0] - it.carb >= L.carbMin - 1e-9)) return false;
      }
      return true;
    };
    // 같은 상품의 다른 행(1개 / 행사 묶음)이 조합에 이미 있으면 바꿔 담기 후보가 아님
    const groupsBut = (idx) => new Set(combo.items.filter((x, j) => j !== idx && x.g).map((x) => x.g));
    combo.alts = combo.items.map((it, idx) => (pinned.has(it.id) ? [] :
      cand.filter((c) => c.type === it.type && c.price === it.price && (c.u || 1) === (it.u || 1) && !inCombo.has(c.id) &&
        !(c.g && groupsBut(idx).has(c.g)) &&
        ok(combo.items.map((x, j) => (j === idx ? c : x))))));
    return combo;
  }

  // 가격 상한·종류 체크를 반영한 상위 K개 + 없을 때 이유
  // opts.pinned  : 꼭 넣을 상품 id 목록 (종류 체크와 상관없이 들어감)
  // opts.excluded: 빼 둘 상품 id 목록
  // opts.timeLimitMs: B&B 시간 제한
  // 꼭 넣을 상품은 미리 담아 두고, 남은 조건(단백질·칼로리·예산·선택 조건·개수)만큼만 나머지에서 찾는다.
  function listCombos(items, types, R, cmin, cmax, L, cap, K, Q, opts) {
    opts = opts || {};
    L = L || NO_LIMITS;
    Q = Q || {};
    const allTypes = new Set(items.map((it) => it.type));
    const checked = new Set(types && types.length ? types : allTypes);
    const excluded = new Set(opts.excluded || []);
    const pinnedIds = new Set((opts.pinned || []).filter((id) => !excluded.has(id)));
    const pinned = items.filter((it) => pinnedIds.has(it.id));
    // 꼭 넣은 상품과 같은 상품의 다른 행(1개 / 행사 묶음)은 후보에서 뺀다 (같은 상품은 한 행만)
    const pinnedG = new Set(pinned.filter((it) => it.g).map((it) => it.g));
    const pool = items.filter((it) => checked.has(it.type) && !excluded.has(it.id) && !pinnedIds.has(it.id) && !(it.g && pinnedG.has(it.g)));
    const res = { combos: [], nodes: 0, time: 0, stopped: false, note: "", pool: pool.length, reasons: [], pinned };

    // 꼭 넣을 상품을 뺀 남은 조건
    const s = (f) => pinned.reduce((a, it) => a + it[f], 0);
    const pP = s("p"), pK = s("k"), pC = s("price");
    const pEx = [s("carb"), s("fat"), s("sugar"), s("na")];
    const R2 = Math.max(0, R - pP), cmin2 = cmin - pK, cmax2 = cmax - pK;
    const cap2 = cap == null ? null : cap - pC;
    const sub = (v, x) => (v == null ? null : v - x);
    const L2 = { carbMin: L.carbMin == null || L.carbMin - pEx[0] <= 0 ? null : L.carbMin - pEx[0],
      carbMax: sub(L.carbMax, pEx[0]), fatMax: sub(L.fatMax, pEx[1]), sugarMax: sub(L.sugarMax, pEx[2]), naMax: sub(L.naMax, pEx[3]) };
    const Q2 = {};
    let qBroken = "";
    for (const t of Object.keys(Q)) {
      if (Q[t] == null) continue;
      const have = pinned.filter((it) => it.type === t).length;
      if (have > Q[t]) qBroken = `꼭 넣을 상품 중 ${t}가 ${have}개라 개수 ${Q[t]}개를 넘어요.`;
      Q2[t] = Q[t] - have;
    }
    if (pinned.length) {
      const over = [];
      if (cmax2 < 0) over.push(`칼로리 상한(${cmax}kcal)`);
      if (cap2 != null && cap2 < 0) over.push(`예산(${cap.toLocaleString()}원)`);
      [["carbMax", "탄수화물 상한"], ["fatMax", "지방 상한"], ["sugarMax", "당류 상한"], ["naMax", "나트륨 상한"]]
        .forEach(([k, lb]) => { if (L2[k] != null && L2[k] < -1e-9) over.push(lb); });
      if (over.length || qBroken) {
        if (over.length) res.reasons.push(`꼭 넣을 상품만으로 ${over.join(", ")}을 넘어요.`);
        if (qBroken) res.reasons.push(qBroken);
        return res;
      }
    }

    const run = bnbTopK(pool, R2, cmin2, cmax2, L2, cap2, K, Q2, opts.timeLimitMs);
    Object.assign(res, { nodes: run.nodes, time: run.time, stopped: run.stopped, note: run.note });
    res.combos = run.combos.map((c) => ({
      cost: c.cost + pC, key: c.key, items: pinned.concat(c.items),
      protein: c.protein + pP, kcal: c.kcal + pK,
    }));
    const cand = usable(pool, cmax, L).filter((it) => cap == null || it.price <= cap);
    res.combos.forEach((c) => addAlternatives(c, cand, R, cmin, cmax, L, Q, pinnedIds));
    if (res.combos.length) return res;

    // 없을 때 이유
    const hasQ = Object.keys(Q2).length > 0;
    if (hasQ) {
      const c2 = usable(pool, cmax2, L2).filter((it) => cap2 == null || it.price <= cap2);
      for (const t of Object.keys(Q2)) {
        const c = c2.filter((it) => it.type === t).length;
        if (c < Q2[t]) res.reasons.push(`${t}에서 쓸 수 있는 상품이 ${c}개뿐이라 ${Q2[t]}개를 더 고를 수 없어요.`);
      }
      const free = bnbTopK(pool, R2, cmin2, cmax2, L2, cap2, 1, null, opts.timeLimitMs);
      res.nodes += free.nodes; res.time += free.time;
      if (free.combos.length) {
        res.reasons.push(`개수 조건을 빼면 ${(free.combos[0].cost + pC).toLocaleString()}원 조합이 있어요. 정한 개수로는 단백질·칼로리·예산을 함께 맞출 수 없어요.`);
        return res;
      }
      if (res.reasons.length) return res;
    }
    if (cap2 != null) {
      const best = bnbTopK(pool, R2, cmin2, cmax2, L2, null, 1, Q2, opts.timeLimitMs);
      res.nodes += best.nodes; res.time += best.time;
      if (best.combos.length) {
        res.cheapest = best.combos[0].cost + pC;
        res.reasons.push(`예산을 빼면 가장 싼 조합이 ${res.cheapest.toLocaleString()}원이라, ${cap.toLocaleString()}원 안에는 조합이 없어요.`);
        return res;
      }
    }
    res.reasons = res.reasons.concat(diagnose(pool, R2, cmin2, cmax2, L2));
    if (pinned.length) res.reasons.push("꼭 넣을 상품을 빼면 조합이 생길 수 있어요.");
    return res;
  }

  // ---- 추천 (planner.py) ----
  function solve(items, R, cmin, cmax, L, algo) {
    if (algo === "greedy") return [greedy(items, R, cmin, cmax, L), ""];
    let note = "";
    if (algo === "dp") {
      if (!active(L)) return [dpSolve(items, R, cmin, cmax), ""];
      note = "선택 조건이 있어 DP 대신 B&B로 계산했어요. (DP는 영양성분마다 표 차원이 하나씩 늘어나서 지원하지 않음)";
    }
    const g = greedy(items, R, cmin, cmax, L);
    const r = bnb(items, R, cmin, cmax, L, g);
    r.time += g.time; // 초기해(Greedy) 시간 포함
    if (algo === "dp") r.algo = "B&B (DP 대신)";
    return [r, note];
  }

  function diagnose(pool, R, cmin, cmax, L) {
    if (!pool.length) return ["체크한 유형에 해당하는 상품이 없어요."];
    const msgs = [];
    const cand = usable(pool, cmax, L);
    if (cand.length < pool.length)
      msgs.push(`${pool.length - cand.length}개 상품은 1개만으로도 칼로리 상한${active(L) ? "이나 선택 조건" : ""}을 넘어서 쓸 수 없어요.`);
    if (!cand.length) return msgs.concat(["남는 상품이 없어요."]);
    const totP = cand.reduce((s, it) => s + it.p, 0);
    const totK = cand.reduce((s, it) => s + it.k, 0);
    if (totP < R) msgs.push(`쓸 수 있는 상품을 전부 사도 단백질이 ${totP}g이라 ${R}g을 못 채워요.`);
    if (totK < cmin) msgs.push(`쓸 수 있는 상품을 전부 사도 칼로리가 ${totK}kcal이라 ${cmin}kcal을 못 채워요.`);
    if (L.carbMin != null && cand.reduce((s, it) => s + it.carb, 0) < L.carbMin) msgs.push(`전부 사도 탄수화물이 ${L.carbMin}g에 못 미쳐요.`);
    if (totP >= R) {
      let need = R, kcal = 0;
      const sorted = cand.filter((x) => x.p > 0).sort((a, b) => a.k / a.p - b.k / b.p);
      for (const it of sorted) {
        const t = Math.min(1, need / it.p);
        kcal += t * it.k; need -= t * it.p;
        if (need <= 0) break;
      }
      if (kcal > cmax) msgs.push(`단백질 ${R}g을 채우려면 칼로리가 최소 약 ${Math.round(kcal)}kcal 필요해서 상한 ${cmax}kcal을 넘어요.`);
    }
    if (!msgs.some((m) => !m.includes("쓸 수 없어요")))
      msgs.push("남은 상품으로는 단백질·칼로리·선택 조건을 동시에 맞추는 조합이 없어요 (하나를 맞추면 다른 조건을 넘어요).");
    return msgs;
  }

  function actual(res, original) {
    if (res.cost == null) return res;
    const chosen = res.items.map((it) => original.get(it.id));
    return Object.assign({}, res, { items: chosen, cost: chosen.reduce((s, it) => s + it.price, 0) });
  }

  const LIMIT_NAMES = [["carbMin", "탄수화물 하한"], ["carbMax", "탄수화물 상한"], ["fatMax", "지방 상한"],
    ["sugarMax", "당류 상한"], ["naMax", "나트륨 상한"]];

  function recommend(items, types, R, cmin, cmax, L, algo) {
    const allTypes = new Set(items.map((it) => it.type));
    const checked = new Set(types && types.length ? types : allTypes);
    const whole = [...allTypes].every((t) => checked.has(t));
    const pool = items.filter((it) => checked.has(it.type));
    const rec = { status: "none", result: null, added: [], messages: [], alternatives: [], reasons: [] };

    let [res, note] = solve(pool, R, cmin, cmax, L, algo);
    if (note) rec.messages.push(note);
    if (res.cost != null) {
      rec.status = "ok"; rec.result = res;
      rec.messages.push(whole ? "전체 상품 중 최저가 조합이에요." : "체크한 유형 안에서 찾은 조합이에요.");
      return rec;
    }
    rec.lastTry = res;
    rec.messages.push((whole ? "전체 상품으로도" : "체크한 유형만으로는") + " 조건을 만족하는 조합이 없어요.");
    rec.reasonsAt = rec.messages.length; // 이유 목록을 이 메시지 바로 뒤에 보여줌
    if (algo === "greedy" && pool.length) rec.reasons.push("Greedy는 해가 있어도 못 찾을 수 있어요. " + (res.note || ""));
    rec.reasons = rec.reasons.concat(diagnose(pool, R, cmin, cmax, L));

    const original = new Map(items.map((it) => [it.id, it]));
    const penalized = items.map((it) => (checked.has(it.type) ? it : Object.assign({}, it, { price: it.price + BIG })));
    if (!whole) {
      const [r2] = solve(penalized, R, cmin, cmax, L, algo);
      if (r2.cost != null) {
        const r = actual(r2, original);
        rec.status = "expanded"; rec.result = r;
        rec.added = r.items.filter((it) => !checked.has(it.type));
        const kinds = [...new Set(rec.added.map((it) => it.type))].sort();
        rec.messages.push(`그래서 체크하지 않은 유형(${kinds.join(", ")})에서 ${rec.added.length}개를 추가했어요. 추가 개수를 가장 적게 하고, 그중 가장 싼 조합이에요.`);
        if (rec.added.length === r.items.length) rec.messages.push("체크한 유형의 상품은 이 조합에 들어가지 못했어요.");
        return rec;
      }
    }
    if (active(L)) {
      const options = [];
      for (const [key, label] of LIMIT_NAMES) {
        if (L[key] == null) continue;
        const relaxed = Object.assign({}, L, { [key]: null });
        const [r3] = solve(penalized, R, cmin, cmax, relaxed, algo);
        if (r3.cost != null) options.push([actual(r3, original), label]);
      }
      if (options.length) {
        options.sort((a, b) => a[0].cost - b[0].cost);
        const [best, label] = options[0];
        rec.status = "relaxed"; rec.result = best;
        rec.added = best.items.filter((it) => !checked.has(it.type));
        rec.messages.push(`상품을 추가해도 안 돼서 '${label}' 조건을 빼고 찾았어요.`);
        if (rec.added.length) rec.messages.push(`체크하지 않은 유형에서 ${rec.added.length}개도 추가됐어요.`);
        rec.alternatives = options.slice(1).map(([r, lb]) => `'${lb}' 조건을 빼면 ${r.cost.toLocaleString()}원 조합이 가능해요.`);
        return rec;
      }
    }
    if (!whole) {
      rec.messages.push("전체 상품으로 넓혀도 조합이 없어요.");
      rec.reasons = rec.reasons.concat(diagnose(items, R, cmin, cmax, L));
    }
    rec.messages.push("단백질 기준을 낮추거나 칼로리 범위를 넓혀 보세요.");
    return rec;
  }

  global.Algo = { greedy, dpSolve, bnb, bnbTopK, listCombos, addAlternatives, usable, recommend, active };
})(typeof window !== "undefined" ? window : globalThis);
