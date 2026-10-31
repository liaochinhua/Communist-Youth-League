# -*- coding: utf-8 -*-
"""花名册读取

支持两种版式：
  A. 分段大表（全校汇总）—— 每个学院前面有一行"学院名"，表头在中间
      2026级：行1 标题 / 行2 商学院 / 行3 表头 / 行4+ 数据 …
  B. 单学院表 —— 表头在第 1 行，下面全是数据
      机能学院：行1 表头 / 行2+ 数据

按【表头文字】取列，所以列顺序变化、多出"情况注明"之类的列都不影响。

统一返回 12 个字段：
    0 序号  1 学号  2 专业班级  3 姓名  4 籍贯  5 性别
    6 出生年月  7 入团时间  8 入团地点  9 备注
    10 情况注明   11 标黄标记（"Y" 表示该行被标黄）

标黄或写了情况注明的行 = 团委已经知道并记录过的，一律不做问题汇总。
"""
import datetime

import openpyxl

FIELDS = ["序号", "学号", "专业班级", "姓名", "籍贯", "性别",
          "出生年月", "入团时间", "入团地点", "备注"]
EXTRA = ["情况注明"]

ALIAS = {
    "序号": ["序号", "编号"],
    "学号": ["学号", "学籍号"],
    "专业班级": ["专业班级", "班级", "专业", "支部"],
    "姓名": ["姓名", "名字"],
    "籍贯": ["籍贯", "籍贯地"],
    "性别": ["性别"],
    "出生年月": ["出生年月", "出生日期", "生日"],
    "入团时间": ["入团时间", "入团年月", "入团日期"],
    "入团地点": ["入团地点", "入团单位"],
    "备注": ["备注", "政治面貌"],
    "情况注明": ["情况注明"],
}

# 「情况注明」里出现这些词，就认为对应问题已经说明过
EXPLAINED_BY = {
    "籍贯有误": ["籍贯"],
    "时间格式错误": ["出生日期", "出生年月", "入团时间", "入团地点", "时间", "日期"],
    "备注为空": ["备注", "政治面貌"],
    "智慧团建无，电子版有": ["智慧团建", "未接收", "没有账号", "退团"],
    "智慧团建有，电子版无": ["智慧团建", "退团"],
    "班级不符": ["原班级", "转班", "账号在"],
    "出现两次": ["重复"],
    "学号重复": ["学号", "重复"],
}

YELLOW = ("FFFFFF00",)          # Excel 的"黄色"填充


def _clean(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _is_yellow(cell):
    f = getattr(cell, "fill", None)
    if not f or not f.patternType:
        return False
    try:
        rgb = getattr(f.start_color, "rgb", None)
    except Exception:
        return False
    return isinstance(rgb, str) and rgb.upper() in YELLOW


def _fix_date(v, style):
    """把 Excel 的日期单元格 / 日期序列号 统一成文本

    有些老花名册里日期是「真正的日期格式」，读出来是 datetime 或 38626 这种序列号；
    直接当文本比较会全部误报格式错误，所以这里先归一化。
    """
    d = None
    if isinstance(v, (datetime.datetime, datetime.date)):
        d = v
    elif isinstance(v, (int, float)) and 20000 < float(v) < 60000:
        try:
            d = datetime.date(1899, 12, 30) + datetime.timedelta(days=int(v))
        except Exception:
            d = None
    if d is None:
        return _clean(v)
    if style == "cn":
        return f"{d.year}年{d.month:02d}月"
    return f"{d.year}.{d.month}"


def _find_header(raw):
    """找出表头行：同时含"学号"和"姓名"的那一行"""
    for i, (vals, _) in enumerate(raw[:20]):
        cells = [_clean(c) for c in vals]
        if "学号" in cells and "姓名" in cells:
            return i, cells
    return None, []


def _colmap(header):
    """表头文字 -> 列号；先精确匹配，再按前缀（表头可能带括号说明）"""
    idx = {}
    for f, names in ALIAS.items():
        for j, h in enumerate(header):
            if h in names:
                idx[f] = j
                break
        if f in idx:
            continue
        for j, h in enumerate(header):
            if any(len(n) >= 2 and h.startswith(n) for n in names):
                idx[f] = j
                break
    return idx


def _extract(vals, idx, date_style):
    out = []
    for f in FIELDS:
        j = idx.get(f)
        raw = vals[j] if j is not None and j < len(vals) else None
        if f in ("出生年月", "入团时间"):
            out.append(_fix_date(raw, date_style))
        else:
            out.append(_clean(raw))
    for f in EXTRA:
        j = idx.get(f)
        out.append(_clean(vals[j]) if j is not None and j < len(vals) else "")
    return out


def _is_section_row(vals):
    """只有第一列有内容，且不是表头、不是合计 —— 判定为学院名"""
    cells = [_clean(c) for c in vals]
    first, rest = cells[0], [c for c in cells[1:] if c]
    if not first or rest:
        return False
    if first in ("序号", "合计") or first.startswith("合计"):
        return False
    if first.startswith("团员花名册"):
        return False
    return True


def explained(note, label):
    """情况注明里已经提到的，就不再当问题汇总"""
    s = _clean(note)
    if not s:
        return False
    return any(k in s for k in EXPLAINED_BY.get(label, []))


def skip_row(r):
    """这一行要不要整体跳过：写了情况注明，或者被标黄"""
    note = r[10] if len(r) > 10 else ""
    yellow = r[11] if len(r) > 11 else ""
    return bool(note) or yellow == "Y"


def load(path, single_college="未命名学院", date_style="dot"):
    """返回 (rows, sections)

    rows     : [(学院, [12 个字段]), …]
    sections : {学院: [[12 个字段], …]}
    """
    ws = openpyxl.load_workbook(path, data_only=True).active
    raw = []
    for row in ws.iter_rows():
        vals = [c.value for c in row]
        yellow = "Y" if any(_is_yellow(c) for c in row) else ""
        raw.append((vals, yellow))

    header_idx, header = _find_header(raw)
    sections, cur, buf = {}, None, []
    mode = "single"
    if header_idx is not None and any(_is_section_row(v) for v, _ in raw[:header_idx]):
        mode = "sections"

    def rec(vals, yellow, idx):
        out = _extract(vals, idx, date_style)
        out.append(yellow)
        return out

    if mode == "sections":
        idx = None
        for vals, yellow in raw:
            if _is_section_row(vals):
                if cur:
                    sections[cur] = buf
                cur, buf = _clean(vals[0]), []
                # 分段表只有第一个学院带表头，切换分段时不要清空列映射
                continue
            cells = [_clean(c) for c in vals]
            if "序号" in cells or (idx is None and "学号" in cells):
                idx = _colmap(cells)
                continue
            if cur and idx:
                r = rec(vals, yellow, idx)
                if r[3]:
                    buf.append(r)
        if cur:
            sections[cur] = buf
    else:
        idx = _colmap(header) if header else {}
        for vals, yellow in raw[header_idx + 1:]:
            r = rec(vals, yellow, idx)
            if r[3]:
                buf.append(r)
        sections[single_college] = buf

    sections = {k: v for k, v in sections.items() if v}
    rows = [(col, r) for col, rs in sections.items() for r in rs]
    return rows, sections
