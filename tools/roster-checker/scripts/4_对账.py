# -*- coding: utf-8 -*-
"""花名册（电子版） × 智慧团建（系统） 对账

规则（按团委口径）：
  · 系统有、本班表格没有 → 先全表找一遍
        在别的班找到  → 班级不符
        全表都没有    → 智慧团建有，电子版无
  · 表格有、本班系统没有 → 先看系统别的团支部有没有
        在别的支部    → 班级不符（反向）
        都没有        → 智慧团建无，电子版有
  · 只在表格内查：籍贯格式、时间格式、备注为空、同一人重复
"""
import csv
import difflib
import glob
import importlib.util
import os
import collections

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

import conf

BASE = conf.BASE
OUT_DIR = conf.OUT_DIR
SRC = conf.roster_file()
SYS_CSV = conf.sys_csv()
COLLEGES = conf.COLLEGES

# 花名册班级 -> 智慧团建团支部：由 scripts/namemap.py 按「专业简称+班号」自动配对
# （简称表在 data/专业简称.csv，可编辑；新增专业时改那张表即可）

# 幽灵支部：列表页不显示、组织树可进；成员名单只能人工抄，放在 config.json
# 的 ghost_branches 里（含真实姓名，不进仓库）
GHOST = conf.GHOST

IGNORE_ORG = ["研究生团支部"]      # 主任明确：研究生不算新生，整块不参与核查

HEAD = ["学院", "学号", "专业班级", "姓名", "籍贯", "性别", "出生年月",
        "入团时间", "入团地点", "备注", "问题类型", "核查说明"]


def read_sections(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    secs, cur, buf = {}, None, []
    for row in ws.iter_rows(min_row=1, values_only=True):
        a, rest = row[0], [c for c in row[1:] if c not in (None, "")]
        if a not in (None, "") and not rest:
            if cur:
                secs[cur] = buf
            name = str(a).strip()
            cur = None if name.startswith("合计") else name
            buf = []
            continue
        if cur and row[3] and str(a).strip() != "序号":
            buf.append(list(row[:10]))
    if cur:
        secs[cur] = buf
    return secs


# ---------- 模块级：读数据 + 自动配对（供 5/6 号脚本复用） ----------
_nm = importlib.util.spec_from_file_location("nm", os.path.join(BASE, "scripts", "namemap.py"))
NM = importlib.util.module_from_spec(_nm)
_nm.loader.exec_module(NM)

SECTIONS = read_sections(SRC)


def _load_sys():
    by_org = collections.defaultdict(dict)
    with open(SYS_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            by_org[r["团支部"].strip()][r["姓名"].strip()] = r
    return by_org


SYS_BY_ORG = _load_sys()
CLASSES = list(dict.fromkeys(
    str(r[2]).strip() for c in COLLEGES for r in SECTIONS.get(c, [])))
MAPPING, UNMATCHED, EXTRA_ORGS = NM.auto_map(CLASSES, list(SYS_BY_ORG))
for _c in GHOST:                       # 幽灵支部：系统里查不到，用人工抄的名单
    MAPPING.setdefault(_c, None)


def main():
    secs = SECTIONS
    sys_by_org = SYS_BY_ORG
    sys_rows = [r for d in sys_by_org.values() for r in d.values()]

    # 花名册索引
    roster = collections.defaultdict(list)          # 班级 -> [行]
    name_index = collections.defaultdict(list)      # 姓名 -> [(学院,行)]
    for col in COLLEGES:
        for r in secs.get(col, []):
            roster[str(r[2]).strip()].append((col, r))
            name_index[str(r[3]).strip()].append((col, r))

    names_in_org = collections.defaultdict(set)     # 姓名 -> 出现的团支部
    for org, d in sys_by_org.items():
        for n in d:
            names_in_org[n].add(org)

    issues = []
    mm = collections.defaultdict(lambda: {"表格": set(), "系统": set(), "col": ""})

    # ---------- 逐班对账 ----------
    for cls, org in MAPPING.items():
        col = next((c for c in COLLEGES if cls in {str(r[2]).strip() for _, r in roster[cls]}), "")

        if org is None:
            # 幽灵支部：系统组织树里能点进去，但列表页不显示（系统 bug），
            # 这 6 个名字是人工从页面上抄下来的
            if cls in GHOST:
                sys_names = set(GHOST[cls])
                cls_names = {str(r[3]).strip() for _, r in roster[cls]}
                for n in sorted(cls_names - sys_names):
                    c, r = next((c, r) for c, r in roster[cls] if str(r[3]).strip() == n)
                    # 姓名写法差异属于个人问题，按团委口径不汇总，只有"确实没有"才报
                    if difflib.get_close_matches(n, list(sys_names), n=1, cutoff=0.5):
                        continue
                    else:
                        issues.append((c, r, "智慧团建无，电子版有",
                                       f"花名册有《{n}》，该支部系统中查不到"
                                       f"（注：本支部在系统列表页不可见，数据为人工核对）"))
                for n in sorted(sys_names - cls_names):
                    if not difflib.get_close_matches(n, list(cls_names), n=1, cutoff=0.5):
                        issues.append((col, ["", "", cls, n, "", "", "", "", "", ""],
                                       "智慧团建有，电子版无",
                                       f"系统该支部有《{n}》，花名册找不到（人工核对）"))
                continue
            for c, r in roster[cls]:
                issues.append((c, r, "智慧团建无对应支部",
                               f"系统里找不到与“{cls}”对应的团支部（该班 {len(roster[cls])} 人全部无归属）"))
            continue

        sys_names = set(sys_by_org.get(org, {}))
        cls_names = {str(r[3]).strip() for _, r in roster[cls]}
        col = roster[cls][0][0] if roster[cls] else ""

        # 系统有、本班没有
        for n in sorted(sys_names - cls_names):
            others = names_in_org[n] - {org}
            if n in name_index:      # 表格里别处有这个人 -> 班级不符
                where = "、".join(sorted({str(r[2]).strip() for _, r in name_index[n]}))
                mm[n]["表格"].add(where)
                mm[n]["系统"].add(org)
                mm[n]["col"] = mm[n]["col"] or col
            elif others:
                mm[n]["表格"].add("（未在表格出现）")
                mm[n]["系统"].add(org)
                mm[n]["col"] = mm[n]["col"] or col
            else:
                issues.append((col, ["", "", cls, n, "", "", "", "", "", ""],
                               "智慧团建有，电子版无", f"系统“{org}”里有 {n}，花名册全表也找不到"))

        # 本班有、系统没有
        for n in sorted(cls_names - sys_names):
            row = next(r for _, r in roster[cls] if str(r[3]).strip() == n)
            others = names_in_org[n]
            if others:
                mm[n]["表格"].add(cls)
                mm[n]["系统"] |= set(others)
                mm[n]["col"] = mm[n]["col"] or col
            else:
                issues.append((col, row, "智慧团建无，电子版有", f"花名册有 {n}（{cls}），系统里查不到"))

    # ---------- 把「班级不符」合并成一条 ----------
    for n, info in mm.items():
        tb = "、".join(sorted(x for x in info["表格"] if x))
        xt = "、".join(sorted(x for x in info["系统"] if x))
        row = next((r for _, r in name_index.get(n, [])), ["", "", "", n, "", "", "", "", "", ""])
        issues.append((info["col"] or row[0], row, "班级不符",
                       f"表格在“{tb}”，智慧团建在“{xt}”"))

    extra_orgs = [o for o in sys_by_org if o not in MAPPING.values() and o not in IGNORE_ORG]
    print("=== 对账结果 ===")
    print(f"花名册 {sum(len(v) for k, v in roster.items() if k in MAPPING)} 人，"
          f"系统 {len(sys_rows)} 人，系统团支部 {len(sys_by_org)} 个")
    print("\n按类型：")
    for t, n in collections.Counter(i[2] for i in issues).most_common():
        print(f"  {t:22} {n}")
    if extra_orgs:
        print("\n系统里多出来的支部（未参与对账）：")
        for o in extra_orgs:
            print(f"  {o}  {len(sys_by_org[o])} 人")

    # ---------- 写表 ----------
    os.makedirs(OUT_DIR, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "对账明细"
    thin = Side(style="thin", color="D0D0D0")
    for j, h in enumerate(HEAD, 1):
        c = ws.cell(1, j, h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="C00000")
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for i, (col, r, t, note) in enumerate(issues, 2):
        vals = [col] + list(r)[1:10] + [t, note] if isinstance(r, list) else \
               [col] + list(r[1:10]) + [t, note]
        for j, v in enumerate(vals, 1):
            cell = ws.cell(i, j, v)
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            cell.alignment = Alignment(vertical="center",
                                       horizontal="center" if j in (1, 6, 7, 8) else "left")
    for j, w in enumerate([11, 13, 22, 9, 20, 6, 10, 10, 26, 10, 22, 52], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:L{len(issues) + 1}"

    path = os.path.join(OUT_DIR, "对账结果.xlsx")
    wb.save(path)
    print(f"\n明细: {path}")


if __name__ == "__main__":
    main()
