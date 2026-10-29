#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2_生成匹配表.py  —— 把「本地文件」和「服务器记录」对上号

输入：
  1) records.csv        由 1_导出服务器清单.js 在浏览器里导出
  2) 本地档案根目录      在 config.json 的 local_root 里配

输出（都在 输出\\ 目录下）：
  upload_plan.csv   上传清单：服务器序号 / 题名 / 文件id / 对应本地文件 / 匹配分 / 状态
  本地清单.csv      本地所有文件的清单
  匹配报告.md       人看的核对报告：待确认项、没对上的记录、没用上的文件

用法：
  python 2_生成匹配表.py --records records.csv
  python 2_生成匹配表.py --records records.csv --root "D:\\档案"
"""
import argparse
import csv
import os
import re
import sys
import unicodedata
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "输出")

# 题名里到处都有的虚词，去掉才比得出差别；学校专名放 config.json 的 stop_words
STOP = ["关于", "的通知", "通知", "决定", "印发", "共青团", "委员会",
        "我校", "学校", "开展", "组织", "举办", "做好", "有关", "事项"] + \
       list(conf.get("stop_words", []))


def norm(s: str) -> str:
    """归一化：全角转半角、去标点/空格/时间戳/公章词 —— 但保留数字

    数字必须留：`团委书记例会提要【2025.5.23】` 和 `【2025.9.16】` 去掉数字就一模一样了，
    六份例会提要会互相抢位置，最后必然错位。
    """
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower()
    s = re.sub(r"_\d{8,}(?=\D*$)", " ", s)          # 结尾的 _20260710155121 时间戳
    s = re.sub(r"[\(（]\s*1\s*[\)）]", " ", s)       # 结尾的 (1) / （1）
    s = re.sub(r"\bpdf\b", " ", s)
    for w in STOP:
        s = s.replace(w, " ")
    s = re.sub(r"[^0-9a-z\u4e00-\u9fa5]+", "", s)   # 只留字和数字
    return s


def bigrams(s: str):
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def similarity(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    r = SequenceMatcher(None, a, b).ratio()
    ba, bb = bigrams(a), bigrams(b)
    j = len(ba & bb) / max(1, len(ba | bb))
    score = 0.45 * r + 0.55 * j
    if a in b or b in a:
        score = min(1.0, score + 0.18)
    return round(score, 4)


# ---------------------------------------------------------------- 本地文件
def leading_number(name: str):
    m = re.match(r"\s*(\d{1,3})\s*[.、．]\s*", name)
    return int(m.group(1)) if m else None


def folder_range_hint(rel_parts):
    """从父目录名里找 "65-70"、"（117-134）" 这种序号区间"""
    for p in reversed(rel_parts[:-1]):
        m = re.search(r"(?<!\d)(\d{1,3})\s*[-—~]\s*(\d{1,3})(?!\d)", p)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < a <= b <= 300:
                return (a, b)
    return None


# 这些目录里的文件不参与上传（主任没要求 / 不是档案正文件），在 config.json 的 exclude_dirs 里改
EXCLUDE_DIRS = list(conf.get("exclude_dirs", []))


def is_excluded(rel: str) -> bool:
    return any(d in rel for d in EXCLUDE_DIRS)


def scan_local(root: str):
    files = []
    for dirpath, _dirs, names in os.walk(root):
        for n in names:
            if not n.lower().endswith((".pdf", ".doc", ".docx", ".jpg", ".png", ".xls", ".xlsx")):
                continue
            full = os.path.join(dirpath, n)
            rel = os.path.relpath(full, root)
            parts = rel.split(os.sep)
            files.append({
                "path": full,
                "rel": rel,
                "name": n,
                "stem": os.path.splitext(n)[0],
                "dir": os.sep.join(parts[:-1]),
                "num": leading_number(n),
                "range": folder_range_hint(parts),
                "size": os.path.getsize(full),
            })
    # 目录按开头的类别号排（1.… 2.… 14.…），类内按文件名数字排
    def cat_key(rel):
        p = rel.split(os.sep)[0]
        m = re.match(r"(\d{1,3})", p)
        return int(m.group(1)) if m else 999
    def nat_key(s):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]
    files.sort(key=lambda f: (cat_key(f["rel"]), nat_key(f["rel"])))
    return files


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True, help="records.csv")
    ap.add_argument("--root", default=conf.local_root() or ".",
                    help="本地档案根目录（默认读 config.json 的 local_root）")
    ap.add_argument("--demo", action="store_true", help="只跑样例，不报错")
    ap.add_argument("--min-auto", type=float, default=0.80)
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)

    # 读服务器记录
    recs = []
    with open(args.records, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            o = (row.get("序号") or "").strip()
            if not o.isdigit():
                continue
            recs.append({
                "order": int(o),
                "dh": (row.get("档号") or "").strip(),
                "title": (row.get("题名") or "").strip(),
                "id": (row.get("文件id") or "").strip(),
                "fulltext": (row.get("全文数") or "").strip(),
            })
    recs.sort(key=lambda r: r["order"])
    print(f"服务器记录 {len(recs)} 条")

    all_files = scan_local(args.root)
    files = [f for f in all_files if not is_excluded(f["rel"])]
    skipped = [f for f in all_files if is_excluded(f["rel"])]
    print(f"本地文件 {len(all_files)} 个，参与匹配 {len(files)} 个"
          + (f"（按规则跳过 {len(skipped)} 个：{'、'.join(EXCLUDE_DIRS)}）" if skipped else ""))

    # ---- 1) 目录区间强的，先钉死
    # 说明：早期版本会按目录名里的「65-70」这种区间强行钉死序号，
    # 但那些数字是「文件序号」，跟服务器序号差 1 甚至差更多（中间会插入别的记录），
    # 硬套会把整段错位，所以这里只用题名相似度，序号只作为报告里的参考。
    forced = {}
    used = set()

    # ---- 2) 按题名相似度贪心配对
    # 题名完全相同的情况（比如 12 和 96 都叫「学代会新闻稿」）：
    # 优先给「已经有旧附件」的那条，因为它才是要替换范芸旧文件的那条
    cand = []
    for r in recs:
        bonus = 0.01 if (r.get("fulltext") or "0") not in ("", "0") else 0.0
        for f in files:
            if id(f) in used:
                continue
            s = round(similarity(r["title"], f["stem"]) + bonus, 4)
            if s >= 0.42:
                cand.append((s, r["order"], f))
    cand.sort(key=lambda x: -x[0])

    assign = dict(forced)          # 序号 -> file
    assigned_files = set(id(f) for f in assign.values())
    second = {}
    for s, o, f in cand:
        if o in assign or id(f) in assigned_files:
            continue
        assign[o] = f
        assigned_files.add(id(f))
        assign[o]["_score"] = s

    # 第二候选（用于判断把握大不大）
    for s, o, f in cand:
        if o in assign and assign[o] is not f:
            second.setdefault(o, (s, f))

    # ---- 2.5) 应用「手动指定.csv」：重跑也不会被覆盖
    # 表格两列：序号,本地文件 （本地文件留空 = 这条不上传、保留旧文件）
    man_path = os.path.join(OUT, "手动指定.csv")
    manual = {}
    if os.path.exists(man_path):
        by_rel = {os.path.normcase(os.path.relpath(f["path"], args.root)): f for f in files}
        with open(man_path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                o = (row.get("序号") or "").strip()
                if not o.isdigit():
                    continue
                rel = (row.get("本地文件") or "").strip()
                if not rel:
                    assign.pop(int(o), None)
                    manual[int(o)] = None
                    continue
                key = os.path.normcase(os.path.normpath(rel))
                f = by_rel.get(key)
                if f:
                    assign[int(o)] = dict(f, _score=1.0, _manual=True)
                    manual[int(o)] = rel
                else:
                    print(f"⚠️ 手动指定里的文件不存在：序号 {o} → {rel}")
        print(f"已应用手动指定 {len(manual)} 条")

    # ---- 3) 输出 upload_plan.csv
    plan_path = os.path.join(OUT, "upload_plan.csv")
    auto, review, missing = 0, 0, 0
    with open(plan_path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["序号", "档号", "服务器题名", "文件id", "本地文件", "匹配分", "状态", "备注"])
        for r in recs:
            f = assign.get(r["order"])
            if not f:
                missing += 1
                w.writerow([r["order"], r["dh"], r["title"], r["id"], "", "", "缺失",
                            "服务器有此记录，本地没找到对应文件"])
                continue
            score = f.get("_score", round(similarity(r["title"], f["stem"]), 4))
            margin = score - second.get(r["order"], (0, None))[0]
            if f.get("_manual"):
                status, note = "自动", "手动指定"
                auto += 1
            elif score >= args.min_auto and margin >= 0.05:
                status, note = "自动", "题名高度相似"
                auto += 1
            elif score >= 0.55:
                status = "待确认"
                note = f"相似度 {score:.2f}，次选只差 {margin:.2f}" if margin < 0.05 else f"相似度 {score:.2f}，请核对"
                review += 1
            else:
                status, note = "待确认", "匹配很弱，请人工指定"
                review += 1
            w.writerow([r["order"], r["dh"], r["title"], r["id"],
                        os.path.relpath(f["path"], args.root), round(score, 4), status, note])
    print(f"写 {plan_path}")

    # ---- 4) 本地清单
    inv_path = os.path.join(OUT, "本地清单.csv")
    with open(inv_path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["相对路径", "文件名", "开头编号", "目录区间", "大小KB"])
        for f in all_files:
            w.writerow([f["rel"], f["name"], f["num"] or "", f["range"] or "",
                        round(f["size"] / 1024)])
    print(f"写 {inv_path}")

    # ---- 5) 报告
    unused = [f for f in files if id(f) not in assigned_files]
    rep = os.path.join(OUT, "匹配报告.md")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write(f"# 匹配报告\n\n")
        fh.write(f"- 服务器记录：**{len(recs)}** 条\n- 本地文件：**{len(all_files)}** 个"
                 f"（参与匹配 {len(files)} 个）\n")
        if skipped:
            fh.write(f"- 已按规则跳过：**{len(skipped)}** 个（目录：{'、'.join(EXCLUDE_DIRS)}，不上传）\n")
        fh.write(f"- 自动对应：**{auto}**\n- 待确认：**{review}**\n- 服务器有、本地无：**{missing}**\n")
        fh.write(f"- 本地多出来、没用上：**{len(unused)}**\n\n")
        fh.write("## 待确认（一定要人工看）\n\n")
        for r in recs:
            f = assign.get(r["order"])
            if not f:
                continue
            score = f.get("_score", 0)
            if score < args.min_auto:
                fh.write(f"- 序号 {r['order']}　{r['title']}\n  → {f['rel']}　(分 {score})\n")
        fh.write("\n## 服务器有记录但本地没找到文件\n\n")
        for r in recs:
            if r["order"] not in assign:
                fh.write(f"- 序号 {r['order']}　{r['dh']}　{r['title']}\n")
        fh.write("\n## 本地没用上的文件\n\n")
        for f in unused:
            fh.write(f"- {f['rel']}\n")
    print(f"写 {rep}")
    print(f"\n小结：自动 {auto} / 待确认 {review} / 缺失 {missing} / 多余 {len(unused)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
