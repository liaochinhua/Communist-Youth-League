# -*- coding: utf-8 -*-
"""读表检查：正式核查前先跑这个

作用只有一个——确认脚本「看懂」了你的表。
很多问题不是核查逻辑错，而是读表就错了（版式认错、日期格式对不上、
列名改了），那种情况下跑出来的数字全是假的。

输出：
  · 识别成哪种版式（分段大表 / 单学院表）
  · 每个学院多少人、多少班
  · 日期写法抽样（判断 date_style 配得对不对）
  · 有没有「情况注明」列、多少行被标黄
  · 哪些专业还没配简称
"""
import collections

import conf
import roster


def main():
    path = conf.roster_file()
    print(f"花名册：{path}\n")

    rows, sections = roster.load(path, conf.SINGLE_COLLEGE, conf.DATE_STYLE)

    # ---------- 版式 ----------
    layout = "分段大表（按学院分块）" if len(sections) > 1 else "单学院表（或只有一个学院）"
    print(f"识别版式：{layout}")
    print(f"总人数　：{len(rows)} 人\n")

    print("学院分布：")
    for col, rs in sections.items():
        ncls = len({str(r[2]).strip() for r in rs})
        print(f"  {col:12} {len(rs):5} 人   {ncls:3} 个班")

    # ---------- 跳过情况 ----------
    skip = [r for _, r in rows if roster.skip_row(r)]
    yellow = sum(1 for r in skip if len(r) > 11 and r[11] == "Y")
    noted = sum(1 for r in skip if len(r) > 10 and r[10])
    print(f"\n整行跳过：{len(skip)} 人"
          f"（标黄 {yellow}，写了情况注明 {noted}）")
    if not skip:
        print("  这张表没有「情况注明」列，也没有标黄行")

    # ---------- 日期格式 ----------
    print("\n日期写法抽样（出生年月）：")
    sample = [r[6] for _, r in rows if r[6]][:5]
    for s in sample:
        print(f"  {s}")
    style = conf.DATE_STYLE
    matched = 0
    for _, r in rows:
        for v in (r[6], r[7]):
            if v and (("年" in v and "月" in v) == (style == "cn")):
                matched += 1
                break
    total = sum(1 for _, r in rows if r[6] or r[7])
    if total:
        pct = matched * 100 // total
        print(f"\n与 date_style=\"{style}\" 匹配：{pct}%")
        if pct < 60:
            other = "dot" if style == "cn" else "cn"
            print(f"  ⚠ 匹配偏低，可能应该改成 \"{other}\"（config.json 里的 date_style）")

    # ---------- 专业简称 ----------
    import namemap as NM

    majors = collections.Counter()
    for _, r in rows:
        majors[NM._norm(str(r[2]).strip())] += 1     # 去掉班号/“班”/“专业”，与简称表同一套归一化

    table = NM.table()
    shorts = set(table.values())
    missing = [m for m in majors
               if m not in shorts and not any(m.startswith(k) or k.startswith(m) for k in table)]
    print(f"\n专业：{len(majors)} 个", end="")
    if missing:
        print(f"，其中 {len(missing)} 个还没配简称：")
        for m in sorted(missing)[:10]:
            print(f"  {m}  ({majors[m]} 人)")
        print("  → 跑 8_生成简称表.py 重新生成简称表")
    else:
        print("，简称都配好了")

    print("\n✅ 读表正常，可以跑 3_核查_表格内.py 了")


if __name__ == "__main__":
    main()
