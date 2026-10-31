# -*- coding: utf-8 -*-
"""专业简称 + 班级配对

简称表放在 data/专业简称.csv，可以直接编辑：
    学院,专业全称,简称,人数

关键函数：
    cls_short("智能制造工程261")            -> "智造261"
    org_short("智能制造工程专业2026级1班团支部") -> "智造263"
    auto_map(花名册班级, 系统团支部)          -> {班级: 团支部}, 未匹配的两边
"""
import os
import re
import csv

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = os.path.join(BASE, "data", "专业简称.csv")

# 简称表读不到时的兜底
FALLBACK = [
    ("机械设计制造及其自动化", "机制"), ("机械设计制造及自动化", "机制"),
    ("智能制造工程", "智造"), ("计算机科学与技术", "计算机"),
    ("数据科学与大数据技术", "数据"), ("智能科学与技术", "智能"),
    ("信息与计算科学", "信计"), ("宇树创新班", "宇树"),
]

_MAJOR2SHORT = None


def table():
    """读 data/专业简称.csv -> {专业全称: 简称}；文件不存在就用兜底"""
    global _MAJOR2SHORT
    if _MAJOR2SHORT is not None:
        return _MAJOR2SHORT
    m = {}
    if os.path.exists(TABLE):
        with open(TABLE, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                full, short = (r.get("专业全称") or "").strip(), (r.get("简称") or "").strip()
                if full and short:
                    m[full] = short
    if not m:
        m = dict(FALLBACK)
    _MAJOR2SHORT = m
    return m


def _norm(name):
    s = str(name or "").strip().replace(" ", "").replace("\u3000", "")
    s = re.sub(r"[（(]\s*[）)]$", "", s)
    s = re.sub(r"班$", "", s)
    s = re.sub(r"\d+$", "", s)
    s = s.replace("专业", "")
    return s.replace("(", "（").replace(")", "）")


def _prefix(name):
    n = _norm(name)
    t = table()
    if n in t:
        return t[n]
    if "专升本" in n:
        base = n.replace("（专升本）", "").replace("专升本", "")
        s = t.get(base) or next((v for k, v in t.items() if k.startswith(base)), base)
        return s + "专升本"
    for full, short in sorted(t.items(), key=lambda x: -len(x[0])):
        if n.startswith(full) or full.startswith(n):
            return short
    for full, short in FALLBACK:
        if n.startswith(full):
            return short
    return n


def cls_short(cls):
    """‘智能制造工程261’ -> ‘智造261’"""
    s = str(cls or "").strip()
    m = re.match(r"(.+?)(\d+)$", s)
    if not m:
        return _prefix(s)
    return f"{_prefix(m.group(1))}{m.group(2)}"


def org_short(org):
    """‘信息与计算科学专业2026级1班团支部’ -> ‘信计261’"""
    s = str(org or "").strip()
    if "待转接" in s:
        return s.replace("团委", "").replace("团支部", "支部")
    if "研究生" in s:
        return s.replace("团支部", "")
    s = s.replace("团支部", "")
    m = re.match(r"(.+?)(\d{4})级(\d+)班$", s)
    if not m:
        return _prefix(s)
    return f"{_prefix(m.group(1))}{m.group(2)[2:]}{m.group(3)}"


def auto_map(classes, orgs):
    """花名册班级 与 系统团支部 自动配对

    返回 (mapping, 花名册多出来的, 系统多出来的)
        mapping: {班级: 团支部 or None}
    """
    by_short = {}
    for o in orgs:
        by_short.setdefault(org_short(o), []).append(o)

    mapping, left = {}, []
    for c in classes:
        k = cls_short(c)
        cand = by_short.get(k) or []
        if cand:
            mapping[c] = cand.pop(0)
        else:
            mapping[c] = None
            left.append(c)
    used = {v for v in mapping.values() if v}
    extra = [o for o in orgs if o not in used]
    return mapping, left, extra
