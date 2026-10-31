# -*- coding: utf-8 -*-
"""团员花名册核查：只依赖表格本身的三类问题
   1) 籍贯  —— 必须"省+市"，含县级/缺省名/省名错都算
   2) 重复  —— 同一人出现两次 / 学号撞车 / 同名同班
   3) 时间格式 —— 出生年月、入团时间必须 YYYY.M（精确到月，点号分隔）
"""
import glob
import json
import os
import re
import collections
import difflib

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

import conf
import roster

BASE = conf.BASE
AREA = conf.area_file()          # 首次运行会自动下载行政区划数据
OUT_DIR = conf.OUT_DIR
SRC = conf.roster_file()
COLLEGES = conf.COLLEGES      # 空 = 花名册里有哪些学院就核哪些

HEAD = ["学院", "学号", "专业班级", "姓名", "籍贯", "性别",
        "出生年月", "入团时间", "入团地点", "备注", "问题类型", "核查说明"]

MUNI = ("北京", "天津", "上海", "重庆")
SUFFIX = ("壮族自治区", "回族自治区", "维吾尔自治区", "特别行政区", "自治区",
          "自治州", "自治县", "省", "市", "地区", "盟", "县", "区", "旗")


def short(name):
    n = name
    for suf in SUFFIX:
        if n.endswith(suf) and len(n) > len(suf) + 1:
            return n[: -len(suf)]
    return n


class Area:
    """读 data/行政区划.csv（省,市,区县 三列），建三张查找表"""

    def __init__(self, path):
        self.prov = {}          # 省简称 -> 省全名
        self.city_alias = {}    # 省简称 -> {市别名: 市全名}
        self.county = {}        # (省简称, 区县简称) -> (市简称, 市全名)
        for ps, pf, cn, tn in self._raw(path):
            self.prov[ps] = pf
            alias = self.city_alias.setdefault(ps, {})
            if cn == pf:                          # 直辖市：区县挂在省下
                alias.setdefault(cn, cn)
                alias.setdefault(short(cn), cn)
                self.county.setdefault((ps, short(tn)), (ps, pf))
                continue
            cs = short(cn)
            alias[cn] = cn
            alias[cs] = cn
            if cn.endswith(("自治州", "地区", "盟")):
                alias[cs[:2]] = cn                # 黔南布依族苗族自治州 -> 黔南
            key = short(tn)
            self.county.setdefault((ps, key), (cs, cn))
            if len(key) > 3:                      # 镇宁布依族苗族 -> 镇宁
                self.county.setdefault((ps, key[:2]), (cs, cn))

    @staticmethod
    def _raw(path):
        rows = []
        with open(path, encoding="utf-8-sig") as f:
            for i, line in enumerate(f):
                if i == 0:
                    continue
                parts = line.rstrip("\n").split(",")
                if len(parts) != 3:
                    continue
                pf, cn, tn = parts
                rows.append((short(pf), pf, cn, tn))
        return rows


ADB = Area(AREA)


def check_jiguan(v):
    s = re.sub(r"\s+", "", str(v or ""))
    if not s:
        return False, "籍贯为空"

    ps = None
    for k in sorted(ADB.prov, key=len, reverse=True):
        if s.startswith(k) or s.startswith(ADB.prov[k]):
            ps = k
            break
    if not ps:
        return False, "看不出省份（应以省名开头，如“浙江杭州”）"

    rest = s[len(ps):]
    rest = re.sub(r"^(壮族自治区|回族自治区|维吾尔自治区|特别行政区|自治区|省|市)", "", rest)

    if ps in MUNI:
        if not rest:
            return True, ""
        for k in sorted((c[1] for c in ADB.county if c[0] == ps), key=len, reverse=True):
            if rest.startswith(k):
                return False, f"“{k}”是区县，应只写“{ps}”"
        return False, f"多写了内容：应只写“{ps}”"

    if not rest:
        return False, "只写了省，缺地级市"

    alias = ADB.city_alias.get(ps, {})
    for k in sorted(alias, key=len, reverse=True):
        if rest.startswith(k):
            tail = re.sub(r"^市", "", rest[len(k):])
            if not tail:
                return True, ""
            if tail.startswith(k):
                return False, f"市名重复写了两次（{k}{k}）"
            return False, f"多写了县级：应只到“{ps}{short(alias[k])}”"

    for k in sorted((c[1] for c in ADB.county if c[0] == ps), key=len, reverse=True):
        if k in rest:
            cs, cf = ADB.county[(ps, k)]
            if rest.startswith(k):
                return False, f"“{k}”是县级，应改为“{ps}{cs}”"
            return False, f"“{k}”属“{cf}”，应改为“{ps}{cs}”（地级市名字可能写错）"
    near = None
    best = 0
    for v in set(alias.values()):
        nm = short(v)
        if len(nm) == len(rest):
            s = sum(1 for a, b in zip(nm, rest) if a == b)
            if s > best:
                best, near = s, nm
    return False, f"“{rest}”不是该省的地级市" + (f"，疑似“{near}”（可能写错字）" if near else "")


def check_date(v, label):
    """时间格式：默认只认 2005.7；config 里 date_style=cn 时认 2005年07月"""
    s = "" if v is None else str(v).strip()
    if not s:
        return False, f"{label}为空"

    if getattr(conf, "DATE_STYLE", "dot") == "cn":
        m = re.fullmatch(r"(\d{4})年(\d{1,2})月", s)
        if m:
            mo = int(m.group(2))
            return (True, "") if 1 <= mo <= 12 else (False, f"{label}月份不合法（{mo}）")
        if re.fullmatch(r"\d{4}年\d{1,2}月\d{1,2}日", s):
            return False, f"{label}多写了日，只写到月"
        if re.fullmatch(r"\d{4}", s):
            return False, f"{label}只写到年，缺月份"
        return False, f"{label}格式不对（应为 2005年7月 这种）"

    if re.fullmatch(r"\d{4}\.\d{1,2}", s):
        m = int(s.split(".")[1])
        return (True, "") if 1 <= m <= 12 else (False, f"{label}月份不合法（{m}）")
    if re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}", s):
        return False, f"{label}多写了日，只写到月"
    if re.fullmatch(r"\d{4}", s):
        return False, f"{label}只写到年，缺月份"
    return False, f"{label}格式不对（应为 2024.9 这种）"


def read_sections(path):
    """花名册读取：兼容「分段大表」和「单学院表」，具体交给 roster.py"""
    import roster
    _, secs = roster.load(path, conf.SINGLE_COLLEGE, conf.DATE_STYLE)
    return secs


def main():
    sections = read_sections(SRC)
    cols = COLLEGES or [c for c in sections if sections[c]]
    issues, class_stat = [], collections.Counter()

    # 两个学院一起建索引，才能抓到「同一人同时在两个学院」的情况
    by_id = collections.defaultdict(list)
    for col in cols:
        for r in sections.get(col, []):
            by_id[str(r[1]).strip()].append(r)

    for col in cols:
        rows = sections.get(col, [])

        for r in rows:
            # 写了情况注明、或被标黄的行：团委已经知道，整行不做问题汇总
            if roster.skip_row(r):
                continue
            types, notes = [], []
            note10 = r[10] if len(r) > 10 else ""      # 「情况注明」列

            def skip(label, _n=note10):
                """情况注明里已经说明过的，不算问题"""
                return roster.explained(_n, label)

            ok, why = check_jiguan(r[4])
            if not ok and not skip("籍贯有误"):
                types.append("籍贯有误")
                notes.append(why)
            for idx, label in ((6, "出生年月"), (7, "入团时间")):
                ok, why = check_date(r[idx], label)
                if not ok and not skip("时间格式错误"):
                    types.append("时间格式错误")
                    notes.append(why)
            # 备注：只查空，不查内容（预备党员/中共党员都是正常的）
            if not str(r[9] or "").strip() and not skip("备注为空"):
                types.append("备注为空")
                notes.append("备注没填（应填共青团员/预备党员/中共党员）")

            # 重复：只看「同一个人整行出现两次」
            # （两个人共用一个学号属于学号问题，团委明确不管，这里不报）
            same_id = by_id[str(r[1]).strip()]
            if len(same_id) > 1:
                names = {str(x[3]).strip() for x in same_id}
                if len(names) == 1:
                    where = {str(x[2]).strip() for x in same_id}
                    types.append("出现两次")
                    notes.append(f"同一人（学号 {r[1]}）出现 {len(same_id)} 次"
                                 + (f"，跨 {'、'.join(sorted(where))}" if len(where) > 1 else ""))
                else:
                    types.append("学号重复")
                    notes.append(f"学号 {r[1]} 被 {'、'.join(sorted(names))} 共用")

            if types:
                seen, tl = set(), []
                for t in types:
                    if t not in seen:
                        seen.add(t)
                        tl.append(t)
                issues.append((col, r, "、".join(tl), "；".join(notes)))
                class_stat[(col, str(r[2]))] += 1

    os.makedirs(OUT_DIR, exist_ok=True)
    wb = openpyxl.Workbook()
    thin = Side(style="thin", color="D0D0D0")

    ws = wb.active
    ws.title = "问题明细"
    for j, h in enumerate(HEAD, 1):
        c = ws.cell(1, j, h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="C00000")
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for i, (col, r, t, note) in enumerate(issues, 2):
        vals = [col] + list(r[1:10]) + [t, note]
        for j, v in enumerate(vals, 1):
            if j == 3 and isinstance(v, (int, float)):
                v = str(int(v))
            cell = ws.cell(i, j, v)
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            cell.alignment = Alignment(vertical="center",
                                       horizontal="center" if j in (1, 6, 7, 8) else "left")
    for j, w in enumerate([11, 13, 24, 9, 22, 6, 10, 10, 28, 10, 20, 46], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:L{len(issues) + 1}"

    ws2 = wb.create_sheet("按班级汇总")
    ws2.append(["学院", "专业班级", "问题条数", "涉及学生"])
    for j in range(1, 5):
        c = ws2.cell(1, j)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E79")
    for (col, cls), n in sorted(class_stat.items()):
        names = [str(r[3]) for c2, r, t, _ in issues if c2 == col and str(r[2]) == cls]
        ws2.append([col, cls, n, "、".join(dict.fromkeys(names))])
    for j, w in enumerate([12, 26, 10, 70], 1):
        ws2.column_dimensions[get_column_letter(j)].width = w

    path = os.path.join(OUT_DIR, "核查结果-表格内问题.xlsx")
    wb.save(path)

    print(f"源文件: {os.path.basename(SRC)}")
    for col in cols:
        print(f"\n{col}  {len(sections.get(col, []))} 人  问题 {sum(1 for i in issues if i[0] == col)} 条")
    print("\n按类型：")
    for t, n in collections.Counter(i[2] for i in issues).most_common():
        print(f"  {t:26} {n}")
    print(f"\n明细: {path}")


if __name__ == "__main__":
    main()
