# -*- coding: utf-8 -*-
"""统一的路径与配置

所有脚本都从这里拿路径，不再各自写死。
配置放在工具根目录的 config.json（已被 .gitignore 排除），读不到就用 config.example.json。
"""
import os
import json
import glob

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")


def _load():
    for name in ("config.json", "config.example.json"):
        p = os.path.join(BASE, name)
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8-sig"))   # 兼容记事本存的 BOM
            except Exception as e:
                raise SystemExit(f"读不了 {name}：{e}")
    raise SystemExit("找不到 config.json，请把 config.example.json 复制一份改名为 config.json")


C = _load()
OUT_DIR = os.path.join(BASE, C.get("output_dir") or "输出")
COLLEGES = C.get("colleges") or []

# 幽灵支部：系统组织树里能点、列表页却不显示的支部，成员名单只能人工抄
# 放在 config.json 的 ghost_branches 里，形如 {"智能制造工程264": ["姓名1", "姓名2"]}
GHOST = C.get("ghost_branches") or {}


def _pick(pattern, what):
    """支持通配符；有多个时取最新修改的那个"""
    if not pattern:
        raise SystemExit(f"config.json 里没填 {what}")
    hits = glob.glob(pattern)
    if not hits:
        raise SystemExit(f"找不到 {what}：{pattern}")
    if len(hits) > 1:
        hits.sort(key=os.path.getmtime, reverse=True)
    return hits[0]


def roster_file():
    """花名册 xlsx"""
    return _pick(C.get("roster"), "花名册（roster）")


def sys_csv():
    """智慧团建导出的名单 csv"""
    return _pick(C.get("sys_csv"), "智慧团建导出（sys_csv）")


# 行政区划数据：仓库里已带一份精简版（省/市/区县，103 KB），离线可用。
# 文件丢了才需要联网下载，这里给了多个源。
AREA_CSV = os.path.join(DATA, "行政区划.csv")
AREA_URLS = [
    "https://unpkg.com/china-division@2.7.0/dist/pcas-code.json",
    "https://cdn.jsdelivr.net/gh/modood/Administrative-divisions-of-China@master/dist/pcas-code.json",
]


def _convert_area(src_json, dst_csv):
    """把官方的四级 JSON 压成三级 CSV（省,市,区县）"""
    import json
    data = json.load(open(src_json, encoding="utf-8"))
    skip = ("市辖区", "县", "省直辖县级行政区划", "自治区直辖县级行政区划")
    rows = []
    for p in data:
        for c in p.get("children", []):
            if c["name"] in skip:          # 直辖市：区县直接挂在省下
                for t in c.get("children", []):
                    rows.append((p["name"], p["name"], t["name"]))
                continue
            for t in c.get("children", []):
                rows.append((p["name"], c["name"], t["name"]))
    with open(dst_csv, "w", encoding="utf-8-sig", newline="") as f:
        f.write("省,市,区县\n")
        for r in rows:
            f.write(",".join(r) + "\n")
    return len(rows)


def area_file():
    """返回行政区划 CSV 的路径；仓库自带，缺失时才联网补"""
    if os.path.exists(AREA_CSV):
        return AREA_CSV
    import urllib.request
    os.makedirs(DATA, exist_ok=True)
    tmp = AREA_CSV + ".download"
    for url in AREA_URLS:
        try:
            print(f"缺少行政区划数据，正在从 {url.split('/')[2]} 下载…")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                open(tmp, "wb").write(r.read())
            n = _convert_area(tmp, AREA_CSV)
            os.remove(tmp)
            print(f"已生成 {AREA_CSV}（{n} 条）")
            return AREA_CSV
        except Exception as e:
            print(f"  失败：{type(e).__name__}")
    raise SystemExit("行政区划数据缺失且下载失败。请手动放一份 data/行政区划.csv（列：省,市,区县）")
