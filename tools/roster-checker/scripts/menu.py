# -*- coding: utf-8 -*-
"""菜单（真正的入口）

为什么菜单写在 Python 里，而不是 开始.bat 里：
    cmd 读批处理时按当前代码页解码，文件里一有 UTF-8 中文，
    读缓冲区切的不是地方就会把一个汉字劈成两半，那一行就变成乱码命令，
    表现为「某些菜单行报 'xxx' 不是内部或外部命令」——而且每次坏的还不一样。
    所以 bat 只负责找到 Python，之后全部交给 Python 输出中文。

顺带也解决了「缺 openpyxl 不会自动装」的问题。
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

MENU = [
    ("1", "运行前检查 - 配置、依赖、路径", "自检.py"),
    ("2", "读表检查 - 确认脚本看懂你的表", "2_读表检查.py"),
    ("3", "生成 / 更新专业简称表", "8_生成简称表.py"),
    ("4", "核查表格自身问题 - 籍贯、时间格式、备注、重复", "3_核查_表格内.py"),
    ("5", "与智慧团建对账 - 缺失、班级不符", "4_对账.py"),
    ("6", "出名单 - 提交版 + 复核版", "5_出总表.py"),
    ("7", "人数统计 - 按学院 / 按班级 / 缺失名单", "6_人数统计.py"),
    ("8", "按学院拆分 - 发给学院负责人", "7_分学院.py"),
]


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def line(ch="=", n=60):
    print(ch * n)


def ensure_openpyxl():
    """缺库就当场装，不用让人去敲命令行"""
    try:
        import openpyxl  # noqa: F401
        return True
    except ImportError:
        pass

    print()
    print("  缺少 openpyxl —— 读写 Excel 要用的库。")
    print()
    try:
        ans = input("  现在自动安装吗？[Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if ans not in ("", "y", "yes"):
        print()
        print("  那需要你手动装：pip install openpyxl")
        return False

    print()
    print("  正在安装（用清华镜像，国内快一些）...")
    print()
    cmd = [sys.executable, "-m", "pip", "install", "openpyxl",
           "-i", "https://pypi.tuna.tsinghua.edu.cn/simple",
           "--disable-pip-version-check"]
    code = subprocess.call(cmd)
    print()
    if code == 0:
        print("  装好了。")
        return True
    print("  自动安装没成功。可以手动执行：")
    print("      pip install openpyxl")
    return False


def run(script):
    path = os.path.join(HERE, script)
    if not os.path.exists(path):
        print(f"  找不到脚本：{script}")
        return 1
    print()
    return subprocess.call([sys.executable, path])


def wait():
    try:
        input("\n按回车回菜单...")
    except (EOFError, KeyboardInterrupt):
        pass


def main():
    # 第一次用：还没配置，先走向导
    if not os.path.exists(os.path.join(BASE, "config.json")):
        clear()
        line()
        print("  第一次使用，先配一下路径")
        line()
        print()
        run("配置向导.py")
        wait()

    # 缺库先装上；装不上也照样进菜单，让人能跑「1 运行前检查」看情况
    if not ensure_openpyxl():
        print()
        print("  注意：没装 openpyxl，除了「1 运行前检查」，其它步骤都会失败。")
        wait()

    while True:
        clear()
        line()
        print("  团员花名册核查工具")
        line()
        print()
        for key, text, _ in MENU:
            print(f"  {key}  {text}")
        print("  9  一键全跑 - 4 到 8 依次执行")
        print()
        print(" 10  重新配置 - 换了电脑或文件路径时用")
        print()
        print("  0  退出")
        print()
        try:
            ch = input("请输入编号: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if ch == "0":
            return 0
        if ch == "10":
            clear()
            run("配置向导.py")
            wait()
            continue
        if ch == "9":
            clear()
            for _, label, script in MENU[1:]:      # 2 到 8
                line()
                print(f"  {label}")
                line()
                code = run(script)
                print()
                if code != 0 and script in ("3_核查_表格内.py", "4_对账.py"):
                    print("  这一步失败了，先看上面的报错。")
                    break
            wait()
            continue

        hit = [m for m in MENU if m[0] == ch]
        if not hit:
            continue
        clear()
        line()
        print(f"  {hit[0][1]}")
        line()
        run(hit[0][2])
        wait()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(0)
