# -*- coding: utf-8 -*-
"""扫描花名册，把所有专业汇总出来，生成 data/专业简称.csv

简称规则（改这张表就行，脚本会自动读）：
  · 取专业名里最有辨识度的两三个字
  · 专升本 / 中外合作 / 卓工 等后缀保留
用法：python 8_生成简称表.py
"""
import os
import re
import csv
import glob
import collections

import openpyxl

import conf

BASE = conf.BASE
DATA = conf.DATA
SRC = conf.roster_file()

# 专业全称 -> 简称（手动维护，新增专业时在这里加一行，或直接改 csv）
SHORT = {
    # 商学院
    "财务管理": "财务", "金融学": "金融", "金融学（中美合作办学）": "金融（中美）",
    "金融学（中外合作办学）": "金融（中外）", "国际经济与贸易": "国贸",
    "国际经济与贸易（中外合作办学）": "国贸（中外）", "国际经济与贸易（中美合作办学）": "国贸（中美）",
    "电子商务": "电商", "电子商务（专升本）": "电商专升本",
    "物流管理": "物流", "物流管理（专升本）": "物流专升本",
    "国际商务": "国商", "国际商务（专升本）": "国商专升本", "数字经济": "数经",
    # 材能学院
    "材料科学与工程": "材料", "能源与环境系统工程": "能源",
    "能源与环境系统工程（专升本）": "能源专升本",
    "高分子材料与工程": "高分子", "高分子材料与工程（专升本）": "高分子专升本",
    "材料工程": "材工", "材料工程（卓工能源电子）": "材工（卓工）",
    # 传播学院
    "英语": "英语", "英语（专升本）": "英语专升本", "法学": "法学",
    "网络与新媒体": "网媒", "新闻学": "新闻", "新闻学（专升本）": "新闻专升本", "日语": "日语",
    # 机械学院
    "机械设计制造及自动化": "机制", "智能制造工程": "智造",
    # 信息学院
    "电子信息工程": "电信", "电子信息工程（专升本）": "电信专升本",
    "电气工程及其自动化": "电气", "自动化": "自动化",
    "工业智能": "工智", "工业智能宇树创新班（系统方向）": "工智宇树",
    # 土木学院
    "智能建造": "智建", "工程管理": "工管", "土木工程": "土木", "土木": "土木",
    # 生化学院
    "化学工程与工艺": "化工", "化学工程与工艺（专升本）": "化工专升本",
    "生物工程": "生工", "生物工程（专升本）": "生工专升本",
    # 设计学院
    "智能交互设计": "智交", "工业设计": "工设", "环境设计": "环设",
    "数字媒体艺术": "数媒", "数字媒体艺术（专升本）": "数媒专升本", "建筑学": "建筑",
    # 人工智能学院
    "计算机科学与技术": "计算机", "数据科学与大数据技术": "数据",
    "信息与计算科学": "信计", "信息与计算科学（专升本）": "信计专升本",
    "智能科学与技术": "智能", "宇树创新班（大脑方向）": "宇树",
}

# 花名册里常见的写法变体 -> 规范名
ALIAS = {
    "国家经济与贸易（中外合作办学）": "国际经济与贸易（中外合作办学）",
    "高分子材料和工程": "高分子材料与工程",
    "数字媒体艺术专业专升本": "数字媒体艺术（专升本）",
    "材料工程2601班（卓工能源电子）": "材料工程（卓工能源电子）",
}


def clean(cls):
    s = str(cls).strip().replace(" ", "").replace("\u3000", "")
    s = re.sub(r"[（(]\s*$", "", s)
    s = re.sub(r"班$", "", s)
    s = re.sub(r"\d+$", "", s)
    s = re.sub(r"专业$", "", s)
    s = s.replace("(", "（").replace(")", "）")
    return ALIAS.get(s, s)


def read_sections(path):
    ws = openpyxl.load_workbook(path, data_only=True, read_only=True).active
    secs, cur, buf = {}, None, []
    for row in ws.iter_rows(min_row=1, values_only=True):
        a, rest = row[0], [c for c in row[1:] if c not in (None, "")]
        if a not in (None, "") and not rest:
            if cur:
                secs[cur] = buf
            name = str(a).strip()
            cur = None if name.startswith("合计") or name.startswith("团员") else name
            buf = []
            continue
        if cur and row[3] and str(row[0]).strip() != "序号":
            buf.append(list(row[:10]))
    if cur:
        secs[cur] = buf
    return secs


def main():
    secs = read_sections(SRC)
    rows, missing = [], []
    for col, data in secs.items():
        c = collections.Counter(clean(r[2]) for r in data)
        for major, n in sorted(c.items(), key=lambda x: -x[1]):
            s = SHORT.get(major)
            if not s:
                missing.append((col, major, n))
            rows.append([col, major, s or "", n])
    rows.sort(key=lambda r: (r[0], -r[3]))

    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, "专业简称.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["学院", "专业全称", "简称", "人数"])
        w.writerows(rows)

    print(f"已写出 {path}")
    print(f"共 {len(rows)} 个专业，覆盖 {len(secs)} 个学院")
    for col in secs:
        n = sum(1 for r in rows if r[0] == col)
        print(f"  {col:8} {n:2} 个专业")
    if missing:
        print("\n⚠️ 这些专业还没配简称，请在 CSV 里补上：")
        for col, m, n in missing:
            print(f"   {col} | {m} | {n} 人")


if __name__ == "__main__":
    main()
