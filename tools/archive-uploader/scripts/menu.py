# -*- coding: utf-8 -*-
"""档案批量上传工具 · 菜单

菜单写在 Python 里，不在 bat 里。原因见 开始.bat 顶部的注释：
    cmd 解码批处理文件时会按代码页来，文件里有中文就可能被读缓冲区劈成两半，
    那一行变成乱码命令。Python 输出中文不受这个影响。
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
sys.path.insert(0, HERE)

# 控制台统一按 UTF-8 输出，避免不同终端下中文变乱码
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OUT = os.path.join(BASE, "输出")


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def line(n=58):
    print("=" * n)


def py(script, *args):
    path = os.path.join(HERE, script)
    cmd = [sys.executable, path] + list(args)
    print("  >", " ".join(cmd[1:]))
    print()
    return subprocess.call(cmd)


def wait(msg="按回车回菜单..."):
    try:
        input("\n" + msg)
    except (EOFError, KeyboardInterrupt):
        pass


def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def need(path, hint):
    if os.path.exists(path):
        return True
    print(f"  [x] 找不到 {os.path.relpath(path, BASE)}")
    print(f"      {hint}")
    return False


def get_cookie():
    """拿 cookie。每次进来都问，不缓存——避免用一个过期 cookie 反复失败"""
    clear()
    line()
    print("  需要 cookie")
    line()
    print()
    print("  1. 浏览器打开档案系统，随便进一个页面")
    print("  2. 按 F12 → Console/控制台")
    print("  3. 输入  document.cookie  回车，复制整串")
    print("  4. 粘到下面（形如 ASPSESSIONIDXXXX=...）")
    print()
    ck = ask("cookie：")
    if not ck:
        print("  没输入，返回菜单。")
        wait()
        return None
    return ck


def main():
    while True:
        clear()
        line(58)
        print("           团委档案批量上传工具")
        line(58)
        print(f"  输出目录 : {OUT}")
        plan = os.path.join(OUT, "upload_plan.csv")
        print(f"  清单     : {'已生成' if os.path.exists(plan) else '还没生成'}")
        line(58)
        print("  [1] 自检        检查网络、配置文件、依赖")
        print("  [2] 生成配对表  读 输出\\records.csv，出 输出\\upload_plan.csv")
        print("  [3] 演练        只打印，看看会上传哪些")
        print("  [4] 先传 1 条   真的传一条，验证没问题")
        print("  [5] 全量上传    断了重跑会自动跳过已完成的")
        print("  [6] 核对结果    对比上传前后的 records.csv")
        print("  [7] 抓页面结构  需要看页面 HTML 时用")
        print("  [8] 清理重复    同一条记录多个同尺寸附件的，只留一个")
        print("  [9] 全库体检    逐条按文件大小核对")
        print(" [10] 差额清理    删掉多了的、补上少了的")
        print("  [0] 退出")
        line(58)

        ch = ask("请输入编号后回车：")

        if ch == "0":
            return 0

        if ch == "1":
            py("0_自检.py")
            wait()

        elif ch == "2":
            if not need(os.path.join(OUT, "records.csv"),
                        "先按说明把服务器清单 records.csv 放进 输出\\ 目录"):
                wait()
                continue
            py("2_生成匹配表.py", "--records", os.path.join(OUT, "records.csv"))
            print()
            print("  配对表已生成：输出\\upload_plan.csv")
            print("  用 Excel 打开，重点看「状态」那一列。")
            wait()

        elif ch == "3":
            ck = get_cookie()
            if not ck:
                continue
            py("3_上传.py", "--cookie", ck, "--limit", "5")
            wait()

        elif ch == "4":
            ck = get_cookie()
            if not ck:
                continue
            py("3_上传.py", "--cookie", ck, "--limit", "1", "--commit")
            print()
            print("  去系统页面确认一下：文件真的上去了吗？")
            print("  没问题的话，再回来跑 5 全量上传。")
            wait()

        elif ch == "5":
            ck = get_cookie()
            if not ck:
                continue
            print()
            print("  全量上传中。按 Ctrl+C 可临时停下，重跑会接着上次的进度。")
            print()
            py("3_上传.py", "--cookie", ck, "--commit")
            wait()

        elif ch == "6":
            if not need(os.path.join(OUT, "records_after.csv"),
                        "先用浏览器导出器再抓一次，存成 records_after.csv 放进 输出\\"):
                wait()
                continue
            py("4_核对.py", "--after", os.path.join(OUT, "records_after.csv"))
            wait()

        elif ch == "7":
            ck = get_cookie()
            if not ck:
                continue
            fid = ask("记录 id（直接回车用默认 1462）：") or "1462"
            py("3_上传.py", "--cookie", ck, "--dump-form", fid)
            print()
            print(f"  已保存 输出\\form_{fid}.html")
            wait()

        elif ch == "8":
            ck = get_cookie()
            if not ck:
                continue
            print()
            print("  === 第一遍：只检查，不删除 ===")
            print()
            py("3_上传.py", "--cookie", ck, "--dedup")
            print()
            yn = ask("确认删除重复的？每组只保留一个，输入 y 回车（其他键跳过）：")
            if yn.lower() == "y":
                py("3_上传.py", "--cookie", ck, "--dedup", "--commit")
            wait()

        elif ch == "9":
            ck = get_cookie()
            if not ck:
                continue
            print("  全库体检：逐条核对附件大小，大约 2~3 分钟。")
            print()
            py("3_上传.py", "--cookie", ck, "--audit")
            wait()

        elif ch == "10":
            ck = get_cookie()
            if not ck:
                continue
            print()
            print("  === 只生成方案，不改动系统 ===")
            print()
            py("3_上传.py", "--cookie", ck, "--reconcile")
            print()
            yn = ask("确认按上面的清单增删？输入 y 回车（其他键跳过）：")
            if yn.lower() == "y":
                py("3_上传.py", "--cookie", ck, "--reconcile", "--commit")
            wait()

        else:
            continue


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(0)
