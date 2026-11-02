# -*- coding: utf-8 -*-
"""运行前检查

开始.bat 的「1 运行前检查」调的就是这里。
用脚本而不是 `python -c "import conf"` 的原因：
    conf.py 在 scripts/ 目录下，从工具根目录用 -c 执行时找不到它。
    写成脚本文件，Python 会自动把脚本所在目录加进搜索路径。

检查项：Python 版本、openpyxl、config.json、花名册路径、系统导出路径
"""
import os
import sys

# 让 `import conf` 不管从哪个目录执行都能找到
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ok(msg):
    print(f"  [OK]   {msg}")


def bad(msg, hint=""):
    print(f"  [!!]   {msg}")
    if hint:
        print(f"         → {hint}")
    return False


def main():
    print("=" * 56)
    print("  团员花名册核查工具 · 运行前检查")
    print("=" * 56)
    print()

    good = True

    # ---------- Python ----------
    v = sys.version_info
    if v >= (3, 8):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        good = bad(f"Python {v.major}.{v.minor} 太旧", "需要 3.8 或更高")

    # ---------- openpyxl ----------
    try:
        import openpyxl
        ok(f"openpyxl {openpyxl.__version__}")
    except ImportError:
        good = bad("缺少 openpyxl", "在命令行执行：pip install openpyxl")

    # ---------- config.json ----------
    cfg = os.path.join(BASE, "config.json")
    if not os.path.exists(cfg):
        good = bad("没有 config.json",
                   "把 config.example.json 复制一份，改名 config.json，再用记事本填路径")
        print()
        print("检查没通过，先建配置。")
        return 1
    ok("config.json 存在")

    # ---------- 读配置 ----------
    try:
        import conf
        ok("配置能正常解析")
    except SystemExit as e:
        code = e.code
        if isinstance(code, str) and code.strip():
            good = bad(f"配置有问题：{code}")
        else:
            good = bad("配置有问题，看上面的提示")
        return 1
    except Exception as e:
        good = bad(f"配置解析失败：{type(e).__name__}: {e}")
        return 1

    # ---------- 花名册 ----------
    try:
        p = conf.roster_file()
        ok(f"花名册：{p}")
    except SystemExit as e:
        good = bad(str(e), "检查 config.json 里的 roster 那一行")

    # ---------- 系统导出（可选） ----------
    try:
        if conf.C.get("sys_csv"):
            p = conf.sys_csv()
            ok(f"系统名单：{p}")
        else:
            print("  [--]   没配 sys_csv —— 将只做表格内核查，跳过与智慧团建对账")
    except SystemExit as e:
        print(f"  [--]   系统名单找不到（{e}）")
        print("         → 不影响表格内核查；要做出缺失统计才需要它")

    # ---------- 行政区划 ----------
    try:
        p = conf.area_file()
        ok(f"行政区划：{os.path.basename(p)}")
    except SystemExit as e:
        good = bad(str(e), "把 data/行政区划.csv 放回来")

    print()
    if good:
        print("检查通过，可以跑「2 读表检查」了。")
    else:
        print("上面标 [!!] 的地方先解决，再跑。")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
