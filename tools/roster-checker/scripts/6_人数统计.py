# -*- coding: utf-8 -*-
"""人数统计：每个学院、每个班，花名册多少、系统内多少、差多少、问题多少"""
import os
import re
import csv
import glob
import importlib.util
import collections

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

import conf

BASE = conf.BASE
OUT = conf.OUT_DIR
DST = os.path.join(OUT, "团员人数统计.xlsx")

spec = importlib.util.spec_from_file_location("recon", os.path.join(BASE, "scripts", "4_对账.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

_nm = importlib.util.spec_from_file_location("nm", os.path.join(BASE, "scripts", "namemap.py"))
NM = importlib.util.module_from_spec(_nm)
_nm.loader.exec_module(NM)
org_short = NM.org_short

thin = Side(style="thin", color="D9D9D9")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)


COLS = R.COLS                                              # 花名册里实际出现的学院
CLS2COL = {str(r[2]).strip(): col
           for col in COLS for r in R.SECTIONS.get(col, [])}


def head(ws, cols, color="C00000"):
    for j, h in enumerate(cols, 1):
        c = ws.cell(1, j, h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=color)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BOX
    ws.row_dimensions[1].height = 30


def widths(ws, ws_list):
    for j, w in enumerate(ws_list, 1):
        ws.column_dimensions[get_column_letter(j)].width = w


# ---------- 数据 ----------
sections = R.read_sections(R.SRC)
sys_by_org = collections.defaultdict(set)
if R.SYS_CSV:                       # 没配系统导出时，系统内人数一律算 0
    with open(R.SYS_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            sys_by_org[r["团支部"].strip()].add(r["姓名"].strip())

# 每个班的问题数（来自已有的两张明细表）
def read_issues(path):
    ws = openpyxl.load_workbook(path, data_only=True).active
    return [list(r) + [None] * (12 - len(r)) for r in ws.iter_rows(min_row=2, values_only=True)]


rows_a = read_issues(os.path.join(OUT, "核查结果-表格内问题.xlsx"))
rows_b = read_issues(os.path.join(OUT, "对账结果.xlsx"))

stat = {}
for cls, org in R.MAPPING.items():
    col = CLS2COL.get(cls, "")      # 学院来自花名册的分段，不靠名字猜
    rows_cls = [r for r in sections[col] if str(r[2]).strip() == cls]
    roster_all = {str(r[3]).strip() for r in rows_cls}
    # 标黄/写了情况注明的人算在花名册人数里，但不参与「系统里没有」的统计
    roster = {str(r[3]).strip() for r in rows_cls if not R.NM_R.skip_row(r)}
    if org:
        sysn = sys_by_org.get(org, set())
    else:
        sysn = set(R.GHOST.get(cls, []))
    stat[cls] = {
        "学院": col,
        "花名册": len(roster_all),   # 按姓名去重（张三在表里有两行）
        "系统": len(sysn),
        "系统无": len(roster - sysn),
        "系统多": len(sysn - roster),
        "缺姓名": "、".join(sorted(roster - sysn)),
    }

# 没提供系统名单时，系统相关列留空，别写成"缺 503 人"这种误导数字
if not R.SYS_CSV:
    for v in stat.values():
        v["系统"] = ""
        v["系统无"] = 0
        v["系统多"] = 0
        v["缺姓名"] = ""

# 各问题按班级计数
for r in rows_a + rows_b:
    cls = str(r[2] or "")
    t = str(r[10] or "")
    if cls not in stat:
        continue
    for lab, key in (("班级不符", "班级不符"),
                     ("学号重复", "学号重复"), ("出现两次", "出现两次"),
                     ("备注为空", "备注为空"), ("智慧团建成无对应支部", "无支部")):
        if lab in t:
            stat[cls][key] = stat[cls].get(key, 0) + 1

wb = openpyxl.Workbook()

# ---------- 按学院 ----------
ws = wb.active
ws.title = "按学院"
head(ws, ["学院", "花名册人数", "系统内人数", "系统里没有", "系统里多出", "差额",
          "其他问题", "问题合计"], "1F4E79")
tot = collections.Counter()
for col in COLS:
    ss = [v for k, v in stat.items() if v["学院"] == col]
    roster = sum(v["花名册"] for v in ss)
    sysn = sum(int(v["系统"] or 0) for v in ss)
    miss = sum(int(v["系统无"] or 0) for v in ss)
    extra = sum(int(v["系统多"] or 0) for v in ss)
    other = sum(v.get(k, 0) for v in ss for k in ("班级不符", "学号重复", "出现两次", "备注为空"))
    ws.append([col, roster, sysn, miss, extra, roster - sysn, other, miss + extra + other])
    tot.update({"r": roster, "s": sysn, "m": miss, "e": extra, "o": other})
ws.append(["合计", tot["r"], tot["s"], tot["m"], tot["e"], tot["r"] - tot["s"],
           tot["o"], tot["m"] + tot["e"] + tot["o"]])
for c in ws[ws.max_row]:
    c.font = Font(bold=True)
widths(ws, [14, 12, 12, 12, 12, 10, 12, 12])
r0 = ws.max_row + 2
ws.cell(r0, 1, "注：花名册人数按姓名去重（张三在表里出现两行）；差额 = 花名册 − 系统内。").font = Font(italic=True, color="808080")

# ---------- 按班级 ----------
ws2 = wb.create_sheet("按班级")
head(ws2, ["学院", "专业班级", "花名册人数", "系统内人数", "系统里没有", "缺失人员名单",
           "系统里多出", "班级不符", "学号重复", "出现两次", "备注为空", "需处理人数"])
for cls, v in sorted(stat.items(), key=lambda x: (COLS.index(x[1]["学院"]) if x[1]["学院"] in COLS else 99, x[0])):
    need = v["系统无"] + v.get("班级不符", 0) + v.get("学号重复", 0) + v.get("出现两次", 0) + v.get("备注为空", 0)
    ws2.append([v["学院"], cls, v["花名册"], v["系统"], v["系统无"], v["缺姓名"],
                v["系统多"], v.get("班级不符", 0), v.get("学号重复", 0),
                v.get("出现两次", 0), v.get("备注为空", 0), need])
widths(ws2, [12, 24, 11, 11, 11, 58, 11, 10, 10, 10, 10, 12])
for row in ws2.iter_rows(min_row=2, max_row=ws2.max_row):
    row[5].alignment = Alignment(wrap_text=True, vertical="center")
ws2.freeze_panes = "A2"

# ---------- 问题清单（一人一行，多个问题并成一句话） ----------
ws3 = wb.create_sheet("问题清单")
head(ws3, ["学院", "专业班级", "姓名", "学号", "问题说明"])

people = {}


def slot(r):
    k = (str(r[3] or ""), str(r[1] or ""), str(r[2] or ""))
    if k not in people:
        people[k] = {"学院": r[0], "班级": r[2], "姓名": r[3], "学号": r[1],
                     "缺": False, "共用": "", "不符": "", "两次": False, "备注": False}
    return people[k]


for r in rows_b + rows_a:
    t = str(r[10] or "")
    note = str(r[11] or "") if len(r) > 11 else ""
    p = slot(r)
    if "智慧团建无，电子版有" in t:
        p["缺"] = True
    if "班级不符" in t:
        m = re.search(r"智慧团建在[“\"]([^”\"]+)[”\"]", note)
        p["不符"] = m.group(1) if m else "（其它支部）"
    if "学号重复" in t:
        m = re.search(r"被\s*(.+?)\s*共用", note)
        others = [x for x in (m.group(1).replace("、", "/").split("/") if m else [])
                  if x and x != p["姓名"]]
        p["共用"] = others[0] if others else ""
    if "出现两次" in t:
        p["两次"] = True
    if "备注为空" in t:
        p["备注"] = True

rows3 = []
for p in people.values():
    if not (p["缺"] or p["共用"] or p["不符"] or p["两次"] or p["备注"]):
        continue
    rest = []
    if p["共用"]:
        rest.append("学号与" + p["共用"] + "相同")
    if p["不符"]:
        rest.append(f"智慧团建上为{org_short(p['不符'])}，与表格上不符")
    if p["两次"]:
        rest.append("表格里出现两次")
    if p["备注"]:
        rest.append("备注为空")
    if p["缺"]:
        text = "智慧团建无，表格里有" + "".join("，且" + x for x in rest)
    else:
        text = "，".join(rest)
    rows3.append([p["学院"], p["班级"], p["姓名"], p["学号"], text])

rows3.sort(key=lambda x: (COLS.index(x[0]) if x[0] in COLS else 99, str(x[1]), str(x[2])))
for row in rows3:
    ws3.append(row)
widths(ws3, [12, 26, 12, 16, 56])
for row in ws3.iter_rows(min_row=2, max_row=ws3.max_row):
    row[4].alignment = Alignment(wrap_text=True, vertical="center")
ws3.freeze_panes = "A2"

wb.save(DST)

print("=== 按学院 ===")
for r in ws.iter_rows(min_row=2, values_only=True):
    print("  ", " | ".join(str(x) for x in r))
print("\n=== 差额最大的班 ===")
for r in sorted(ws2.iter_rows(min_row=2, values_only=True), key=lambda x: -int(x[4] or 0))[:6]:
    print("  ", r[1], f"花名册{r[2]} 系统{r[3]} 差{r[4]}")
print(f"\n已写出: {DST}")
