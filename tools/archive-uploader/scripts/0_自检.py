#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
0_自检.py —— 上传前先跑这个，30 秒知道「现在能不能开工」

检查项：
  1. Python 环境
  2. 能不能连上档案服务器（这一条不对，说明你现在不在校园网）
  3. upload_plan.csv 是否齐整：多少条自动、多少条待确认、多少条缺失
  4. 每条记录的本地文件是不是真的存在、大小对不对
  5. 有没有同一个文件被排到两个位置
"""
import csv
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conf  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE_DIR, "输出")
PLAN = os.path.join(OUT, "upload_plan.csv")
ROOT = conf.local_root()
HOST, PORT = conf.host_port()


def main():
    import runlog
    logpath = runlog.start("0_自检")

    print("=" * 60)
    print(" 团委档案上传 · 开工前自检")
    print("=" * 60)

    print(f"\n[1] Python：{sys.version.split()[0]}  ({sys.executable})")

    print(f"\n[2] 连服务器 {HOST}:{PORT} ……", end=" ")
    ok_net = False
    try:
        s = socket.create_connection((HOST, PORT), timeout=4)
        s.close()
        ok_net = True
        print("✅ 通，你现在在校园网里")
    except Exception as e:
        print(f"❌ 不通（{e.__class__.__name__}）")
        print("    → 这说明你现在不在校园网/VPN 里，先把网络切过去再跑上传。")

    if not os.path.exists(PLAN):
        print(f"\n[3] ❌ 找不到 {PLAN}")
        print("    → 先跑第 1 步（浏览器里导出 records.csv），再跑第 2 步生成匹配表。")
        print(f"\n自检结束，日志：{logpath}")
        return 1

    rows = []
    with open(PLAN, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    st = {}
    for r in rows:
        st[(r.get("状态") or "?").strip()] = st.get((r.get("状态") or "?").strip(), 0) + 1
    print(f"\n[3] 匹配表 {len(rows)} 条：", "，".join(f"{k} {v}" for k, v in st.items()))

    empty = [r for r in rows if not (r.get("本地文件") or "").strip()]
    print(f"    其中没有对应本地文件的：{len(empty)} 条（这些不会被上传）")

    print("\n[4] 检查本地文件 ……")
    missing, seen = [], {}
    for r in rows:
        rel = (r.get("本地文件") or "").strip()
        if not rel:
            continue
        p = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
        if not os.path.exists(p):
            missing.append((r.get("序号"), rel))
            continue
        if os.path.getsize(p) == 0:
            missing.append((r.get("序号"), rel + " （0 字节）"))
            continue
        seen.setdefault(rel.lower(), []).append(r.get("序号"))

    if missing:
        print(f"    ❌ 有 {len(missing)} 条找不到文件：")
        for o, rel in missing[:10]:
            print(f"       序号 {o}: {rel}")
        if len(missing) > 10:
            print(f"       …… 还有 {len(missing) - 10} 条，见日志")
    else:
        print("    ✅ 全部存在且非空")

    dup = {k: v for k, v in seen.items() if len(v) > 1}
    print("\n[5] 同一个文件被排到多个位置：", f"{len(dup)} 处" if dup else "无 ✅")
    for k, v in list(dup.items())[:10]:
        print(f"    {k}  →  序号 {', '.join(v)}")

    review = st.get("待确认", 0)
    print("\n" + "=" * 60)
    if not ok_net:
        print("结论：网络没通，现在只能做本地准备，不能上传。")
    elif missing:
        print("结论：有文件缺失，先把 upload_plan.csv 里这些行补好再上传。")
    elif review > 20:
        print(f"结论：还有 {review} 条待确认，建议先在 Excel 里过一遍再做。")
    else:
        print(f"结论：可以上传。建议先跑「先传 1 个试试」（待确认还剩 {review} 条）。")
    print("=" * 60)
    print(f"\n日志已写入：{logpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
