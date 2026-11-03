# -*- coding: utf-8 -*-
"""专业简称 + 班级配对

简称表放在 data/专业简称.csv，可以直接编辑：
    学院,专业全称,简称,人数

关键函数：
    cls_short("智能制造工程261")            -> "智造261"
    org_short("智能制造工程专业2026级1班团支部") -> "智造263"
    auto_map(花名册班级, 系统团支部)          -> {班级: 团支部}, 未匹配的两边
"""
import csv
import difflib
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = os.path.join(BASE, "data", "专业简称.csv")

# 简称表读不到时的兜底
FALLBACK = [
    ("机械设计制造及其自动化", "机制"), ("机械设计制造及自动化", "机制"),
    ("智能制造工程", "智造"), ("计算机科学与技术", "计算机"),
    ("数据科学与大数据技术", "数据"), ("智能科学与技术", "智能"),
    ("信息与计算科学", "信计"), ("宇树创新班", "宇树"),
]

# 花名册里常见的写法变体 -> 规范名（错别字、多余的字）
ALIAS = {
    "国家经济与贸易": "国际经济与贸易",          # 「国」打成「国?」——真事：有人写成"国家经济与贸易"
    "国际经贸": "国际经济与贸易",
    "国家经济与贸易（中外合作办学）": "国际经济与贸易（中外合作办学）",
    "高分子材料和工程": "高分子材料与工程",
    "数字媒体艺术专业专升本": "数字媒体艺术（专升本）",
    "材料工程2601班（卓工能源电子）": "材料工程（卓工能源电子）",
}

_MAJOR2SHORT = None

# 最后一次 auto_map 里「靠相似度猜出来」的配对，供上层提示人工确认
LAST_GUESSES = []


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


# 括号里的这些是「层次/办学类型」，不能当噪音删掉——
# 「金融学（中外合作办学）261」和「金融学261」是两个不同的班。
TAG_RE = re.compile(r"（?(专升本|中外合作办学|中美合作办学|中外|中美)）?")


def split_tag(s):
    """把名字里的层次标签拆出来：返回 (去掉标签的名字, 标签)

    专升本 -> "专升本"；中外/中美合作办学 -> "中外"（两者当同一类）
    """
    tag = ""
    m = TAG_RE.search(s)
    if m:
        raw = m.group(1)
        tag = "专升本" if raw == "专升本" else "中外"
        s = TAG_RE.sub("", s)
    return s, tag


def _norm(name):
    s = str(name or "").strip().replace(" ", "").replace("\u3000", "")
    s = s.replace("(", "（").replace(")", "）")
    s = re.sub(r"（\s*）", "", s)                  # 空括号
    s, _tag = split_tag(s)                        # 专升本/中外 先摘出来
    s = re.sub(r"（[^）]*）", "", s)                 # 其余说明性括号是噪音，删掉
    s = re.sub(r"班$", "", s)
    s = re.sub(r"(?:20)?\d{2}级", "", s)           # 年份（2026级 / 26级）
    s = re.sub(r"\d+$", "", s)
    s = s.replace("专业", "")
    s = ALIAS.get(s, s)          # 错别字/多余的字统一成规范名
    return s


def _prefix(name):
    n = _norm(name)
    t = table()
    if n in t:
        return t[n]
    if "专升本" in n:
        base = n.replace("（专升本）", "").replace("专升本", "")
        if base.endswith("类"):
            base = base[:-1]
        s = t.get(base) or next((v for k, v in t.items() if k.startswith(base)), base)
        return s + "专升本"
    for full, short in sorted(t.items(), key=lambda x: -len(x[0])):
        if n.startswith(full) or full.startswith(n):
            return short
    # 「土木类」「机械类」这种带「类」的写法，去掉类再试一次
    if n.endswith("类"):
        base = n[:-1]
        if base in t:
            return t[base]
        for full, short in sorted(t.items(), key=lambda x: -len(x[0])):
            if base.startswith(full):
                return short
    for full, short in FALLBACK:
        if n.startswith(full):
            return short
    return n


def cls_short(cls):
    """花名册的班级 -> 简称+班号

    ‘智能制造工程261’          -> ‘智造261’
    ‘材料科学与工程261班’       -> ‘材料261’    （末尾带"班"字）
    ‘金融学（中外合作办学）261’   -> ‘金融中外261’
    ‘化学工程与工艺（专升本）261’  -> ‘化工专升本261’
    ‘工业智能宇树创新班（系统方向）261班’ -> ‘工智宇树261’
    """
    s = str(cls or "").strip().replace(" ", "").replace("\u3000", "")
    s = s.replace("(", "（").replace(")", "）")
    s = re.sub(r"（\s*）", "", s)
    s, tag = split_tag(s)                   # 专升本 / 中外
    s = re.sub(r"班$", "", s)
    m = re.search(r"(\d+)$", s)
    if not m:
        return f"{_prefix(s)}{tag}"
    return f"{_prefix(s[:m.start()])}{tag}{m.group(1)}"


def org_short(org):
    """系统团支部 -> 简称+班号

    ‘信息与计算科学专业2026级1班团支部’      -> ‘信计261’
    ‘土木类专业26级1班团支部’                -> ‘土木261’   （年份省了20）
    ‘化学工程与工艺2026级专升本1班团支部’     -> ‘化工专升本261’（专升本写在级后面）
    ‘金融学（中外合作办学）专业2026级1班团支部’ -> ‘金融中外261’
    ‘工业智能专业2026级宇树创新班团支部’      -> ‘工智宇树’  （没有班号，靠后面兜底配对）
    """
    s = str(org or "").strip().replace(" ", "").replace("\u3000", "")
    s = s.replace("(", "（").replace(")", "）")
    s = s.replace("团支部", "").replace("团支书", "")
    if "待转接" in s:
        return s.replace("团委", "") + "支部"
    if "研究生" in s:
        return s

    s, tag = split_tag(s)
    m = re.match(r"(.+?)(\d{4}|\d{2})级(?:专升本)?(\d+)班$", s)
    if not m:
        return f"{_prefix(s)}{tag}"          # 没有班号
    year = m.group(2)
    yy = year[2:] if len(year) == 4 else year
    return f"{_prefix(m.group(1))}{tag}{yy}{m.group(3)}"


def auto_map(classes, orgs, aliases=None):
    """花名册班级 与 系统团支部 自动配对

    同一个班在花名册里可能有几种写法（多了空格、全角/半角括号、"班"字有无），
    它们算出来的简称相同 —— 这些写法都要指向同一个支部，不能只配上一个。

    还有两类写法差异靠规则猜不出来，留给 aliases（config.json 的 org_aliases）：
        「工业智能专业2026级宇树创新班团支部」   ← 没有班号
        「XX专业2026级1班团支部」                ← 花名册里叫别的名字

    aliases: {系统支部名（可以是关键词）: 花名册班级名}

    返回 (mapping, 花名册多出来的, 系统多出来的)
        mapping: {班级: 团支部 or None}
    """
    aliases = aliases or {}
    LAST_GUESSES.clear()
    by_class = {str(c).strip(): c for c in classes}

    mapping, left = {}, []
    for c in classes:
        mapping[c] = None

    # 1. 人工指定的优先
    for key, cls in aliases.items():
        hit_cls = by_class.get(str(cls).strip())
        if not hit_cls:
            continue
        hit_org = next((o for o in orgs if str(key) in o), None)
        if hit_org:
            mapping[hit_cls] = hit_org

    # 2. 按简称自动配（人工已经配好的不动）
    by_short = {}
    taken = set(mapping.values())
    for o in orgs:
        if o in taken:
            continue
        by_short[org_short(o)] = o

    for c in classes:
        if mapping[c]:
            continue
        k = cls_short(c)
        org = by_short.get(k)
        mapping[c] = org
        if not org:
            left.append(c)
        else:
            taken.add(org)

    # 3. 兜底：支部名里没有班号（如「…2026级宇树创新班」），
    #    如果只剩一个同类班级没配上，就认给它
    used = {v for v in mapping.values() if v}
    for o in orgs:
        if o in used:
            continue
        short = org_short(o)
        if any(ch.isdigit() for ch in short[-1:]):
            continue                       # 有班号的走上面那步，别乱配
        cand = [c for c in left if cls_short(c).startswith(short)]
        if len(cand) == 1:
            mapping[cand[0]] = o
            left.remove(cand[0])
            used.add(o)

    # 4. 剩下的按「看起来像不像」兜底 —— 人也是这么猜的
    #    但只在班号一致时才允许，否则会把 1 班配到 2 班
    rest_cls = [c for c in classes if not mapping[c]]
    rest_org = [o for o in orgs if o not in used]
    pairs = []
    for c in rest_cls:
        for o in rest_org:
            a, b = cls_short(c), org_short(o)
            da = re.search(r"(\d+)$", a)
            db = re.search(r"(\d+)$", b)
            if da and db and da.group(1) != db.group(1):
                continue                      # 班号都不一样，肯定不是同一个班
            r = difflib.SequenceMatcher(None, a, b).ratio()
            if r >= 0.72:
                pairs.append((r, c, o))
    pairs.sort(reverse=True)
    for r, c, o in pairs:
        if mapping[c] or o in used:
            continue
        mapping[c] = o
        used.add(o)
        left.remove(c)
        LAST_GUESSES.append((c, o, round(r, 2)))

    extra = [o for o in orgs if o not in used]
    return mapping, left, extra
