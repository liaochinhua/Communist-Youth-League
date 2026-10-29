#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
4_核对.py —— 上传完再跑一遍 1_导出服务器清单.js，用它导出的 records.csv 核对结果

用法：
  python 4_核对.py --after 输出\\records_after.csv --plan 输出\\upload_plan.csv

输出：每个序号是否已经有全文（>0），列出还空着的记录。
"""
import argparse
import csv
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "输出")


def read(path, key="序号"):
    rows = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            k = (r.get(key) or "").strip()
            if k.isdigit():
                rows[int(k)] = r
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", required=True)
    ap.add_argument("--plan", default=os.path.join(OUT, "upload_plan.csv"))
    a = ap.parse_args()

    after = read(a.after)
    plan = read(a.plan)
    ok = bad = 0
    bad_list = []
    for order, p in sorted(plan.items()):
        if not (p.get("本地文件") or "").strip():
            continue
        rec = after.get(order)
        if not rec:
            bad_list.append((order, "服务器上找不到这条记录"))
            bad += 1
            continue
        ft = (rec.get("全文数") or "0").strip()
        n = int(ft) if ft.isdigit() else 0
        if n > 0:
            ok += 1
        else:
            bad += 1
            bad_list.append((order, f"全文数={ft}　{rec.get('题名','')[:30]}"))

    print(f"计划 {len(plan)} 条，其中已配本地文件的 {ok + bad} 条")
    print(f"✅ 已挂上附件：{ok}")
    print(f"❌ 还是空的：{bad}")
    for o, why in bad_list:
        print(f"   序号 {o}: {why}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
