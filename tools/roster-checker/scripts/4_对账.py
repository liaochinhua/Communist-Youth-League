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
SYS_CSV = conf.sys_csv() if conf.C.get("sys_csv") else None
COLLEGES = conf.COLLEGES      # 空 = 花名册里有哪些学院就核哪些

# 花名册班级 -> 智慧团建团支部：由 scripts/namemap.py 按「专业简称+班号」自动配对
# （简称表在 data/专业简称.csv，可编辑；新增专业时改那张表即可）

# 幽灵支部：列表页不显示、组织树可进；成员名单只能人工抄，放在 config.json
# 的 ghost_branches 里（含真实姓名，不进仓库）
GHOST = conf.GHOST

IGNORE_ORG = ["研究生团支部"]      # 主任明确：研究生不算新生，整块不参与核查

HEAD = ["学院", "学号", "专业班级", "姓名", "籍贯", "性别", "出生年月",
        "入团时间", "入团地点", "备注", "问题类型", "核查说明"]


def read_sections(path):
    """花名册读取：兼容「分段大表」和「单学院表」"""
    import roster
    _, secs = roster.load(path, conf.SINGLE_COLLEGE, conf.DATE_STYLE)
    return secs


# ---------- 模块级：读数据 + 自动配对（供 5/6 号脚本复用） ----------
import roster as NM_R

_nm = importlib.util.spec_from_file_location("nm", os.path.join(BASE, "scripts", "namemap.py"))
NM = importlib.util.module_from_spec(_nm)
_nm.loader.exec_module(NM)

SECTIONS = read_sections(SRC)
COLS = COLLEGES or [c for c in SECTIONS if SECTIONS[c]]
# 班级 -> 学院（直接来自花名册的分段，别再猜）
CLS2COL = {str(r[2]).strip(): col for col in COLS for r in SECTIONS.get(col, [])}


def _load_sys():
    by_org = collections.defaultdict(dict)
    if not SYS_CSV:                 # 没配系统导出：跳过对账，只做表格内核查
        return by_org
    with open(SYS_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            by_org[r["团支部"].strip()][NM_R.norm_name(r["姓名"])] = r
    return by_org


SYS_BY_ORG = _load_sys()
CLASSES = list(dict.fromkeys(
    str(r[2]).strip() for c in COLS for r in SECTIONS.get(c, [])))
MAPPING, UNMATCHED, EXTRA_ORGS = NM.auto_map(CLASSES, list(SYS_BY_ORG), conf.ORG_ALIASES)
for _c in GHOST:                       # 幽灵支部：系统里查不到，用人工抄的名单
    MAPPING.setdefault(_c, None)


def report_guesses():
    """相似度猜出来的配对，必须让人看一眼"""
    if not getattr(NM, "LAST_GUESSES", None):
        return
    print("以下配对是按名字相似度猜的，请确认：")
    for cls, org, r in NM.LAST_GUESSES:
        print(f"   {cls}  ↔  {org}   相似度 {r}")
    print()


def main():
    secs = SECTIONS
    sys_by_org = SYS_BY_ORG
    sys_rows = [r for d in sys_by_org.values() for r in d.values()]

    # 花名册索引
    roster = collections.defaultdict(list)          # 班级 -> [行]
    name_index = collections.defaultdict(list)      # 姓名 -> [(学院,行)]
    for col in COLS:
        for r in secs.get(col, []):
            roster[str(r[2]).strip()].append((col, r))
            name_index[NM_R.norm_name(r[3])].append((col, r))

    names_in_org = collections.defaultdict(set)     # 姓名 -> 出现的团支部
    for org, d in sys_by_org.items():
        for n in d:
            names_in_org[n].add(org)

    report_guesses()

    issues = []
    mm = collections.defaultdict(lambda: {"表格": set(), "系统": set(), "col": ""})

    # ---------- 哪些学院真的被系统名单覆盖了 ----------
    # 选了「全部学院」但只抓了部分学院时，没抓的学院不该算成"系统里没有"
    covered_cols = set()
    for cls, org in MAPPING.items():
        if org:
            col = CLS2COL.get(cls, "")
            if col:
                covered_cols.add(col)
    skipped_cols = [c for c in COLS if c not in covered_cols and sys_by_org]
    if skipped_cols:
        print("⚠ 这些学院在系统名单里没有对应支部，本次跳过对账：")
        print("   " + "、".join(skipped_cols))
        print("   （只做表格内核查；要核对它们，先把这些学院也抓一遍）")
        print()

    # ---------- 按「简称」把写法不同的班级合并成一组 ----------
    # 同一个班在花名册里可能写成「材料科学与工程261班」「材料科学与工程261」，
    # 简称都是 材料261 —— 必须当成一个班来比，否则会互相把对方的人看成"不在本班"。
    groups = collections.OrderedDict()
    excluded_classes = []
    for cls, org in MAPPING.items():
        if conf.class_excluded(cls):        # 研究生班等，团委明确不用管的
            excluded_classes.append(cls)
            continue
        k = NM.cls_short(cls)
        g = groups.setdefault(k, {"org": None, "classes": []})
        if org and not g["org"]:
            g["org"] = org
        g["classes"].append(cls)

    if excluded_classes:
        n = sum(len(roster[c]) for c in excluded_classes if c in roster)
        print(f"按配置跳过 {len(excluded_classes)} 个班级（{n} 人）：")
        print("   " + "、".join(excluded_classes))
        print("   （config.json 里的 exclude_classes，一般用来排除研究生班）")
        print()

    # ---------- 逐班对账 ----------
    for k, g in (groups.items() if sys_by_org else []):
        org = g["org"]
        classes = g["classes"]
        cls_names = {str(r[3]).strip() for c in classes for _, r in roster[c]}
        cls_rows = {str(r[3]).strip(): r for c in classes for _, r in roster[c]}
        col = next((CLS2COL.get(c, "") for c in classes if CLS2COL.get(c)), "")
        if col and col in skipped_cols:
            continue

        if org is None:
            # 幽灵支部：系统组织树里能点进去，但列表页不显示（系统 bug），
            # 名单是人工从页面上抄下来的
            ghost_cls = next((c for c in classes if c in GHOST), None)
            if ghost_cls:
                sys_names = set(GHOST[ghost_cls])
                for n in sorted(cls_names - sys_names):
                    r = cls_rows[n]
                    if difflib.get_close_matches(n, list(sys_names), n=1, cutoff=0.5):
                        continue
                    issues.append((col, r, "智慧团建无，电子版有",
                                   f"花名册有《{n}》，该支部系统中查不到"
                                   f"（注：本支部在系统列表页不可见，数据为人工核对）"))
                for n in sorted(sys_names - cls_names):
                    if not difflib.get_close_matches(n, list(cls_names), n=1, cutoff=0.5):
                        issues.append((col, ["", "", ghost_cls, n, "", "", "", "", "", ""],
                                       "智慧团建有，电子版无",
                                       f"系统该支部有《{n}》，花名册找不到（人工核对）"))
                continue
            # 整班没有支部：按班级汇总（见「支部对账」表）。
            # 但如果这个"班"只有一两个人，多半是那个人自己把年级/班级写错了，
            # 按班级报看不出是谁，所以这种小班仍然按人报，方便直接找人改。
            total = sum(len(roster[c]) for c in classes)
            if total <= 2:
                for c in classes:
                    for cc, r in roster[c]:
                        issues.append((cc, r, "智慧团建无对应支部",
                                       f"系统里找不到与“{c}”对应的团支部"
                                       f"（这个班一共 {len(roster[c])} 人，可能是班级名写错了）"))
            continue

        sys_names = set(sys_by_org.get(org, {}))

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
                issues.append((col, ["", "", classes[0], n, "", "", "", "", "", ""],
                               "智慧团建有，电子版无", f"系统“{org}”里有 {n}，花名册全表也找不到"))

        # 本班有、系统没有
        for n in sorted(cls_names - sys_names):
            row = cls_rows[n]
            others = names_in_org[n]
            if others:
                mm[n]["表格"].add(str(row[2]).strip())
                mm[n]["系统"] |= set(others)
                mm[n]["col"] = mm[n]["col"] or col
            else:
                issues.append((col, row, "智慧团建无，电子版有",
                               f"花名册有 {n}（{str(row[2]).strip()}），系统里查不到"))

    # ---------- 把「班级不符」合并成一条 ----------
    for n, info in mm.items():
        tb = "、".join(sorted(x for x in info["表格"] if x))
        xt = "、".join(sorted(x for x in info["系统"] if x))
        row = next((r for _, r in name_index.get(n, [])), ["", "", "", n, "", "", "", "", "", ""])
        issues.append((info["col"] or row[0], row, "班级不符",
                       f"表格在“{tb}”，智慧团建在“{xt}”"))

    extra_orgs = [o for o in sys_by_org if o not in MAPPING.values() and o not in IGNORE_ORG]

    # ---------- 支部层问题：整班没有支部 / 支部没有班 ----------
    # 这类不该按人报（一个班 20 人就是 20 条），单独汇总成一张表
    org_issues = []
    for c in excluded_classes:
        pass
    for k, g in (groups.items() if sys_by_org else []):
        if g["org"] is not None:
            continue
        classes = [c for c in g["classes"] if c not in excluded_classes]
        if not classes or any(c in GHOST for c in classes):
            continue
        col = next((CLS2COL.get(c, "") for c in classes if CLS2COL.get(c)), "")
        n = sum(len(roster[c]) for c in classes)
        if n <= 2:
            continue          # 一两个人的"班"多半是个人写错，按人报更清楚
        org_issues.append((col, "、".join(classes), n, "花名册有，系统里没有这个支部",
                           f"花名册有 {n} 人，但智慧团建里找不到对应的团支部"))
    for o in extra_orgs:
        n = len(sys_by_org.get(o, {}))
        col = next((CLS2COL.get(c, "") for c in MAPPING if MAPPING[c] == o), "")
        org_issues.append((col, o, n, "系统里有，花名册没有这个班",
                           f"系统该支部 {n} 人，花名册里没有对应的班级"))
    print("=== 对账结果 ===")
    print(f"花名册 {sum(len(v) for k, v in roster.items() if k in MAPPING)} 人，"
          f"系统 {len(sys_rows)} 人，系统团支部 {len(sys_by_org)} 个")
    print("\n按类型：")
    for t, n in collections.Counter(i[2] for i in issues).most_common():
        print(f"  {t:22} {n}")
    if org_issues:
        print("\n支部层面的问题：")
        for col, name, n, t, _ in org_issues:
            print(f"  [{t}] {name}  {n} 人")

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

    if org_issues:
        ws2 = wb.create_sheet("支部对账")
        head2 = ["学院", "班级 / 支部", "人数", "问题类型", "说明"]
        for j, h in enumerate(head2, 1):
            c = ws2.cell(1, j, h)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="C00000")
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        for i, (col, name, n, t, note) in enumerate(org_issues, 2):
            for j, v in enumerate([col, name, n, t, note], 1):
                cell = ws2.cell(i, j, v)
                cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
                cell.alignment = Alignment(vertical="center",
                                           horizontal="center" if j in (1, 3) else "left")
        for j, w in enumerate([11, 46, 8, 28, 46], 1):
            ws2.column_dimensions[get_column_letter(j)].width = w
        ws2.freeze_panes = "A2"

    path = os.path.join(OUT_DIR, "对账结果.xlsx")
    wb.save(path)
    print(f"\n明细: {path}")


if __name__ == "__main__":
    main()
