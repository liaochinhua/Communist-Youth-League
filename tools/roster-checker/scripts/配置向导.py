# -*- coding: utf-8 -*-
"""配置向导

第一次用，或者路径变了，跑这个就行——不用手动编辑 config.json。

技巧：提示输入路径时，可以直接把文件**从资源管理器拖进这个黑窗口**，
路径会自动贴上，比手打快也不容易错。
"""
import os
import sys
import json
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(BASE, "config.json")
EXAMPLE = os.path.join(BASE, "config.example.json")


def load_existing():
    for p in (CFG, EXAMPLE):
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8-sig"))
            except Exception:
                pass
    return {}


def ask(label, default="", tip=""):
    if tip:
        print(f"    {tip}")
    shown = f" [{default}]" if default else ""
    try:
        v = input(f"  {label}{shown}：")
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit("\n已取消，没改动任何文件。")
    v = v.strip().strip('"').strip("'")
    return v or default


def check_path(pattern, what):
    """路径可能带通配符；返回命中的文件，找不到返回 None"""
    if not pattern:
        return None
    hits = glob.glob(pattern)
    if not hits:
        print(f"    ⚠ 找不到 {what}：{pattern}")
        return None
    if len(hits) > 1:
        hits.sort(key=os.path.getmtime, reverse=True)
        print(f"    找到 {len(hits)} 个，取最新的：{os.path.basename(hits[0])}")
    return hits[0]


def main():
    print("=" * 60)
    print("  团员花名册核查工具 · 配置向导")
    print("=" * 60)
    print()
    print("提示：输入路径时，可以直接把文件拖进这个窗口，路径会自动贴上来。")
    print()

    cfg = load_existing()

    # ---------- 花名册 ----------
    print("【1/7】花名册 Excel（各学院分段的那份大表）")
    old = cfg.get("roster", "")
    roster = ask("花名册路径", old)
    while roster and not check_path(roster, "花名册"):
        roster = ask("重新输入（直接回车跳过）", "")
        if not roster:
            break
    if roster:
        cfg["roster"] = roster

    # ---------- 智慧团建导出 ----------
    print()
    print("【2/7】智慧团建导出的 csv（团支部,姓名,手机号,职务）")
    print("    没有就先回车跳过——只做表格内核查，不跟系统对账")
    old = cfg.get("sys_csv", "")
    csvp = ask("csv 路径", old)
    if csvp and check_path(csvp, "系统导出"):
        cfg["sys_csv"] = csvp
    elif csvp:
        print("    先留空，之后有了再回来填")
        cfg["sys_csv"] = ""
    else:
        cfg["sys_csv"] = ""

    # ---------- 年级 ----------
    print()
    print("【3/7】年级（用在输出文件名里）")
    cfg["grade"] = ask("年级", cfg.get("grade", "2026级"), "比如 2026级、2022-2026级")

    # ---------- 学院 ----------
    print()
    print("【4/7】要核查哪些学院")
    print("    花名册里怎么写就怎么写，多个用逗号分隔")
    print("    想核全部学院：输入 all（或者 全部 / *），不用一个个列")
    old = cfg.get("colleges") or []
    print(f"    当前：{'、'.join(old) if old else '全部学院（花名册里有几个就核几个）'}")
    v = ask("学院", "")
    if v:
        if v.lower() in ("all", "全部", "*", "所有"):
            cfg["colleges"] = []
            print("    已设为：全部学院")
        else:
            cfg["colleges"] = [x.strip() for x in v.replace("，", ",").split(",") if x.strip()
                               and x.strip().lower() not in ("all", "全部", "*", "所有")]

    # 全学院 + 系统名单：提醒一句，免得把没抓到的学院全算成"缺失"
    if not cfg.get("colleges") and cfg.get("sys_csv"):
        print()
        print("    提醒：你选了全部学院，但系统名单里只有抓过的那些支部。")
        print("    没抓到的学院会被算成「系统里没有」。要么把各学院都抓一遍再导出，")
        print("    要么这一步只填要核的那几个学院。")

    # ---------- 日期格式 ----------
    print()
    print("【5/7】时间格式规范")
    print("    dot = 2008.8    cn = 2008年08月")
    print(f"    当前：{cfg.get('date_style', 'dot')}")
    v = ask("用哪个（dot/cn，直接回车保持不变）", "")
    if v in ("dot", "cn"):
        cfg["date_style"] = v

    # ---------- 籍贯严格度 ----------
    print()
    print("【6/7】籍贯是否严格到「不许出现省、市两个字」？")
    print()
    print("    严格：浙江丽水 ✅   浙江省丽水市 ❌")
    print("    宽松：浙江丽水 ✅   浙江省丽水市 ✅")
    print()
    print("    提示：实测 394 人里有 85 人（34%）写了省/市字。")
    print("    多数团委把它当共性问题，不逐人报，所以默认宽松。")
    print(f"    当前：{'严格' if cfg.get('jiguan_strict') else '宽松'}")
    v = ask("要用严格模式吗（y/t = 严格，n/f = 宽松，回车不变）", "").lower()
    if v in ("y", "t", "yes", "true", "是"):
        cfg["jiguan_strict"] = True
    elif v in ("n", "f", "no", "false", "否"):
        cfg["jiguan_strict"] = False

    # ---------- 整班跳过 ----------
    print()
    print("【7/7】有没有整班不用管的？研究生班、成教班之类")
    print()
    print("    花名册里没有「学历层次」这一列，脚本没法自己判断，只能你点名。")
    print("    按名字包含匹配，写关键词即可，多个用逗号分隔。")
    cur = cfg.get("exclude_classes") or []
    print("    当前：" + ("、".join(cur) if cur else "（不跳过任何班）"))
    v = ask("要跳过的班级关键词（回车保持不变）", "")
    if v:
        cfg["exclude_classes"] = [x.strip() for x in v.replace("，", ",").split(",") if x.strip()]

    # ---------- 写文件 ----------
    # 路径统一改成正斜杠：
    #   JSON 里反斜杠是转义符，手写容易出错；Windows 上正斜杠完全可用。
    for k in ("roster", "sys_csv"):
        if isinstance(cfg.get(k), str) and cfg[k]:
            cfg[k] = cfg[k].replace("\\", "/")
    cfg.setdefault("output_dir", "输出")
    cfg.setdefault("ghost_branches", {})
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print(f"已保存到：{CFG}")
    print()
    print("  花名册  ：", cfg.get("roster", "（未设置）"))
    print("  系统名单：", cfg.get("sys_csv") or "（未设置，将跳过对账）")
    print("  年级    ：", cfg.get("grade", ""))
    print("  学院    ：", "、".join(cfg.get("colleges") or []) or "（全部）")
    print("  时间格式：", cfg.get("date_style", "dot"))
    print("  籍贯口径：", "严格（不许出现省/市字）" if cfg.get("jiguan_strict") else "宽松")
    _ex = cfg.get("exclude_classes") or []
    print("  整班跳过：", "、".join(_ex) if _ex else "（无）")
    print("=" * 60)
    print()
    print("下一步：回到菜单选「2 读表检查」，确认脚本看懂你的表。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已取消，没改动任何文件。")
        sys.exit(1)
