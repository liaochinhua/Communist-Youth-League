# -*- coding: utf-8 -*-
"""统一读取 config.json；改配置不用动代码。"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
EXAMPLE_PATH = os.path.join(BASE_DIR, "config.example.json")
OUT = os.path.join(BASE_DIR, "输出")

_CFG = {}
_path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else EXAMPLE_PATH
if os.path.exists(_path):
    try:
        with open(_path, encoding="utf-8-sig") as f:
            _CFG = json.load(f)
        if _path == EXAMPLE_PATH:
            print("[提示] 还没建 config.json，先用 config.example.json 的默认值跑；"
                  "复制一份改成本机路径即可")
    except Exception as e:                       # 配置写坏了不让程序直接炸
        print(f"[警告] 配置文件读不出来（{e}），将使用默认值")


def get(key, default=None):
    return _CFG.get(key, default)


def base_url() -> str:
    return str(get("base_url", "http://127.0.0.1")).rstrip("/")


def host_port():
    """把 http://ip:port 拆成 (host, port)"""
    import urllib.parse
    u = urllib.parse.urlparse(base_url())
    return u.hostname or "127.0.0.1", u.port or (443 if u.scheme == "https" else 80)


def local_root() -> str:
    p = get("local_root", "")
    return os.path.expandvars(os.path.expanduser(str(p))) if p else ""


def save(key, value):
    """把某个配置写回 config.json（首次配置向导用）"""
    cfg = dict(_CFG)
    cfg[key] = value
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    _CFG.clear()
    _CFG.update(cfg)
