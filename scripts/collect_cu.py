# -*- coding: utf-8 -*-
"""
CU 공식 사이트(cu.bgfretail.com) 상품 목록 수집 스크립트

- 수집 항목: 상품명, 가격(원), 바코드(이미지 파일명), 카테고리, 행사 배지, 상세 ID, 수집일
- 영양정보는 CU 사이트에 없으므로 여기서는 수집하지 않는다 (match_mfds.py 에서 별도 매칭).
- 서버 부담을 줄이기 위해 요청 사이에 지연을 두고, 결과는 CSV로 저장해 재사용한다.

사용법: python scripts/collect_cu.py
출력:   data/raw/cu_products.csv
"""
import csv
import datetime
import html
import os
import re
import time
import urllib.parse
import urllib.request

AJAX_URL = "https://cu.bgfretail.com/product/productAjax.do"

# CU 사이트의 대분류 코드 (사이트 확인 결과)
# 10: 간편식사, 20: 즉석조리, 30: 과자류, 40: 아이스크림, 50: 식품, 60: 음료, (70: 생활용품 - 제외)
# 즉석조리(20)는 내부코드(2202...)라 외부 DB 연결이 불가능하지만 비교를 위해 수집은 한다.
CATEGORIES = {10: "간편식사", 20: "즉석조리", 30: "과자류", 40: "아이스크림", 50: "식품", 60: "음료"}

REQUEST_DELAY_SEC = 0.7   # 요청 간 지연
MAX_PAGES = 60            # 카테고리당 안전 상한

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "cu_products.csv")

# 상품 하나(<li class="prod_list">)를 파싱하기 위한 정규식
ITEM_RE = re.compile(r'<li class="prod_list">(.*?)</li>\s*(?=<li class="prod_list">|</ul>)', re.S)
NAME_RE = re.compile(r'<div class="name"[^>]*>\s*<p>(.*?)</p>', re.S)
PRICE_RE = re.compile(r'<div class="price">\s*<strong>([\d,]+)</strong>', re.S)
IMG_RE = re.compile(r'<img src="[^"]*/([^/"]+)\.(?:jpg|png|gif)"', re.I)
VIEW_RE = re.compile(r'view\((\d+)\)')
BADGE_RE = re.compile(r'<span class="(plus1|plus2|new|best)[^"]*"', re.I)


def fetch_page(category: int, page: int) -> str:
    """대분류 category의 page번째 목록 HTML 조각을 가져온다."""
    form = {
        "pageIndex": page, "searchMainCategory": category, "searchSubCategory": "",
        "listType": 0, "searchCondition": "setA", "searchUseYn": "", "gdIdx": 0,
        "codeParent": category, "user_id": "", "search1": "", "search2": "", "searchKeyword": "",
    }
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(AJAX_URL, data=data, headers={
        "User-Agent": "Mozilla/5.0 (student algorithm project; low-rate)",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_items(fragment: str):
    """HTML 조각에서 상품 정보를 추출한다."""
    for block in ITEM_RE.findall(fragment):
        name = NAME_RE.search(block)
        price = PRICE_RE.search(block)
        if not name or not price:
            continue
        img = IMG_RE.search(block)
        code = img.group(1) if img else ""
        view = VIEW_RE.search(block)
        badges = sorted(set(b.lower() for b in BADGE_RE.findall(block)))
        yield {
            "name": html.unescape(name.group(1)).strip(),
            "price": int(price.group(1).replace(",", "")),
            "barcode": code if code.isdigit() else "",
            "gd_idx": view.group(1) if view else "",
            "badges": ";".join(badges),   # plus1=1+1, plus2=2+1 행사
        }


def main():
    today = datetime.date.today().isoformat()
    rows, seen = [], set()
    for cat, cat_name in CATEGORIES.items():
        for page in range(1, MAX_PAGES + 1):
            items = list(parse_items(fetch_page(cat, page)))
            new = [it for it in items if it["gd_idx"] not in seen]
            if not new:          # 더 이상 새 상품이 없으면 종료
                break
            for it in new:
                seen.add(it["gd_idx"])
                it.update(category=cat_name, collected_at=today,
                          source=f"https://cu.bgfretail.com/product/view.do?category=product&gdIdx={it['gd_idx']}")
                rows.append(it)
            print(f"[{cat_name}] page {page}: +{len(new)} (누적 {len(rows)})")
            time.sleep(REQUEST_DELAY_SEC)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    fields = ["name", "price", "barcode", "category", "badges", "gd_idx", "source", "collected_at"]
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"저장 완료: {os.path.abspath(OUT_PATH)} ({len(rows)}개)")


if __name__ == "__main__":
    main()
