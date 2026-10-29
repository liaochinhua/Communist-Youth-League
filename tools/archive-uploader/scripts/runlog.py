# -*- coding: utf-8 -*-
"""把输出同时写到屏幕和 输出\\运行日志.txt，方便出问题时把日志带回来。"""
import os
import sys
import time

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "输出", "运行日志.txt")


class _Tee:
    def __init__(self, fh, out):
        self.fh, self.out = fh, out

    def write(self, s):
        try:
            self.out.write(s)
        except Exception:
            pass
        self.fh.write(s)
        self.fh.flush()

    def flush(self):
        try:
            self.out.flush()
        except Exception:
            pass
        self.fh.flush()

    def isatty(self):
        return False


def start(tag: str):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    out = sys.stdout
    try:
        out.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    fh = open(LOG, "a", encoding="utf-8")
    fh.write("\n" + "=" * 70 + "\n")
    fh.write(f"### {tag}    {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    fh.write("=" * 70 + "\n")
    fh.flush()
    sys.stdout = _Tee(fh, out)
    return LOG
