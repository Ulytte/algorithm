# -*- coding: utf-8 -*-
"""
웹 페이지를 파일 하나로 묶는다 (더블클릭으로 바로 열리게: 브라우저는 file:// 에서 fetch 를 막으므로 데이터를 페이지 안에 넣는다)
  - web/index.html   + algo.js + items.json        -> web/단백질조합기.html
  - web/compare.html + algo.js + compare_data.json -> web/알고리즘비교.html
"""
import json
import os

WEB = os.path.join(os.path.dirname(__file__), "..", "web")

PAGES = [
    # (페이지, 데이터 파일, 페이지 안의 데이터 불러오기 코드, 바꿀 코드, 결과 파일)
    ("index.html", "items.json",
     'fetch("items.json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })',
     "Promise.resolve(window.__DATA__)", "단백질조합기.html"),
    ("compare.html", "compare_data.json",
     'const res = await fetch("compare_data.json");\n  D = await res.json();',
     "D = window.__DATA__;", "알고리즘비교.html"),
]


def read(name):
    with open(os.path.join(WEB, name), encoding="utf-8") as f:
        return f.read()


def bundle(page_name, data_name, old_fetch, new_fetch, out_name):
    page = read(page_name)
    algo = read("algo.js")
    data = json.loads(read(data_name))

    assert old_fetch in page, f"{page_name} 의 데이터 불러오기 코드가 바뀌었음"
    page = page.replace(old_fetch, new_fetch)
    data_js = "<script>window.__DATA__ = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";</script>\n"
    assert '<script src="algo.js"></script>' in page
    page = page.replace('<script src="algo.js"></script>', data_js + "<script>\n" + algo + "\n</script>")

    head = ('<!doctype html>\n<html lang="ko">\n<head>\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')
    # <style> 끝까지를 head 로, 나머지를 body 로
    i = page.index("</style>") + len("</style>")
    out = head + page[:i] + "\n</head>\n<body>\n" + page[i:] + "\n</body>\n</html>\n"
    path = os.path.join(WEB, out_name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print(f"{path}: {len(out.encode('utf-8')) // 1024}KB")


def main():
    for args in PAGES:
        if os.path.exists(os.path.join(WEB, args[1])):
            bundle(*args)


if __name__ == "__main__":
    main()
