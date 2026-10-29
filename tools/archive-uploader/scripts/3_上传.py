#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3_上传.py  —— 按 upload_plan.csv 批量上传到档案系统

默认是「演练模式」：只读页面、解析表单、打印计划，一个文件都不传。
加 --commit 才真的上传。

典型用法
  1) 先探一个，看表单解析对不对（不上传）：
     python 3_上传.py --cookie "ASPSESSIONIDxxx=..." --only 6 --probe
  2) 只传 1 个试试水：
     python 3_上传.py --cookie "..." --only 6 --commit
  3) 全部上传（断点续传，已成功的自动跳过）：
     python 3_上传.py --cookie "..." --commit

cookie 怎么拿：在服务器页面按 F12 → Console → 输入 document.cookie 回车，复制整串。
"""
import argparse
import csv
import html as html_mod
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conf  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE_DIR, "输出")
LOG = os.path.join(OUT, "upload_log.jsonl")


# ----------------------------------------------------------------- 工具
def decode_html(raw: bytes) -> tuple:
    m = re.search(rb'charset\s*=\s*["\']?\s*([\w\-]+)', raw[:4000], re.I)
    cs = m.group(1).decode("ascii", "ignore").lower() if m else "gbk"
    if cs in ("gb2312", "gb18030", "gbk"):
        cs = "gbk"
    try:
        return raw.decode(cs, "replace"), cs
    except LookupError:
        return raw.decode("utf-8", "replace"), "utf-8"


def is_404(html: str) -> bool:
    return ("404" in html and ("找不到" in html or "Not Found" in html)) or "HTTP 错误 404" in html


def enc(s: str, cs: str) -> bytes:
    for c in ([cs, "gbk", "utf-8"] if cs != "utf-8" else ["utf-8", "gbk"]):
        try:
            return s.encode(c)
        except UnicodeEncodeError:
            continue
    return s.encode("gbk", "replace")


def attr(tag: str, name: str):
    m = re.search(name + r'\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))', tag, re.I)
    if not m:
        return None
    return next(g for g in m.groups()[1:] if g is not None)


def resolve(base_url: str, action: str) -> str:
    return urllib.parse.urljoin(base_url, action)


# ----------------------------------------------------------------- 表单解析
def parse_form(html: str, page_url: str):
    """找出上传表单，返回 action / 字段 / file 控件 / 题名字段"""
    forms = re.findall(r"<form\b[^>]*>.*?</form>", html, re.S | re.I)
    if not forms:
        return None
    target = next((f for f in forms if re.search(r'type\s*=\s*["\']?file', f, re.I)), None)
    if not target:
        return None
    open_tag = re.match(r"<form\b[^>]*>", target, re.I).group(0)
    action = attr(open_tag, "action") or page_url
    action = resolve(page_url, action)

    fields = {}          # name -> value（hidden / text / textarea / select）
    radios = {}          # name -> [(value, label, checked)]
    file_field = None

    # 逐个 input 扫描，同时记录它后面的可见文字（当 label 用）
    for m in re.finditer(r"<input\b[^>]*>", target, re.I):
        tag = m.group(0)
        name = attr(tag, "name")
        if not name:
            continue
        typ = (attr(tag, "type") or "text").lower()
        val = html_mod.unescape(attr(tag, "value") or "")
        if typ == "file":
            if file_field is None:
                file_field = name
        elif typ == "hidden":
            fields[name] = val
        elif typ == "radio":
            rest = target[m.end():m.end() + 60]
            label = re.split(r"<", rest, 1)[0].strip()
            radios.setdefault(name, []).append((val, label, "checked" in tag.lower()))
        elif typ == "submit":
            # 只带上「上传」这个提交按钮，ASP 有时靠它区分动作
            if "上传" in val:
                fields[name] = val
            continue
        elif typ in ("button", "reset", "image"):
            continue
        else:  # text / password / checkbox
            if typ == "checkbox" and "checked" not in tag.lower():
                continue
            fields[name] = val

    # textarea：原样带回，避免把「全文」内容清空
    for m in re.finditer(r"<textarea\b([^>]*)>(.*?)</textarea>", target, re.S | re.I):
        nm = attr(m.group(1), "name")
        if nm:
            fields[nm] = html_mod.unescape(m.group(2))

    # select：带回当前选中项，避免把「位置/背景」等改掉
    for m in re.finditer(r"<select\b([^>]*)>(.*?)</select>", target, re.S | re.I):
        nm = attr(m.group(1), "name")
        if not nm:
            continue
        opts = re.findall(r"<option\b([^>]*)>(.*?)</option>", m.group(2), re.S | re.I)
        pick = None
        for oa, _ot in opts:
            if "selected" in oa.lower():
                pick = attr(oa, "value")
        if pick is None and opts:
            pick = attr(opts[0][0], "value")
        fields[nm] = html_mod.unescape(pick or "")

    # 上传方式 / 提取全文 这两组单选若不在同一个 form 里，就退回整页找
    def _has_mode(rs):
        txt = " ".join(o[1] for v in rs.values() for o in v)
        return ("上传整个文件" in txt) or ("提取全文" in txt)
    if not _has_mode(radios):
        page_radios = {}
        for m in re.finditer(r"<input\b[^>]*>", html, re.I):
            tag = m.group(0)
            name = attr(tag, "name")
            if not name or (attr(tag, "type") or "").lower() != "radio":
                continue
            rest = html[m.end():m.end() + 60]
            label = re.split(r"<", rest, 1)[0].strip()
            page_radios.setdefault(name, []).append((attr(tag, "value") or "", label, "checked" in tag.lower()))
        radios.update(page_radios)

    # 文件题名输入框：找「文件题名」后面的第一个 input（先表单内，再整页）
    title_field = None
    for scope in (target, html):
        idx = scope.find("文件题名")
        if idx >= 0:
            m = re.search(r"<input\b[^>]*>", scope[idx:], re.I)
            if m:
                title_field = attr(m.group(0), "name")
                if title_field:
                    break
    if not title_field:
        for n in fields:
            if re.search(r"title|timing|biaoti|^tm$", n, re.I):
                title_field = n
                break

    # 单选组：上传方式选「上传整个文件」，提取全文选「不提取全文」
    chosen = {}
    for n, opts in radios.items():
        labels = " ".join(o[1] for o in opts)
        if "只上传文件信息" in labels or "上传整个文件" in labels:
            for v, lab, _ in opts:
                if "上传整个文件" in lab:
                    chosen[n] = v
            continue
        if "提取全文" in labels:
            for v, lab, _ in opts:
                if "不提取全文" in lab:
                    chosen[n] = v
            continue
        # 其他组：取默认选中的
        for v, lab, ck in opts:
            if ck:
                chosen[n] = v
                break
    fields.update(chosen)

    return {
        "action": action,
        "fields": fields,
        "radios": {k: [o[1] for o in v] for k, v in radios.items()},
        "file_field": file_field,
        "title_field": title_field,
        "html": target,
    }


def build_multipart(fields: dict, file_field: str, filename: str, data: bytes,
                    title_field, title_value: str, cs: str, fname_mode: str):
    b = "----WebKitFormBoundary" + os.urandom(8).hex()
    out = []
    for k, v in fields.items():
        if title_field and k == title_field:
            v = title_value
        out.append(("--" + b + "\r\n").encode())
        out.append(('Content-Disposition: form-data; name="%s"\r\n\r\n' % k).encode("utf-8"))
        out.append(enc(str(v), cs) + b"\r\n")
    fn = filename if fname_mode == "orig" else ("up_" + re.sub(r"\W+", "_", filename)[-40:])
    out.append(("--" + b + "\r\n").encode())
    out.append(enc('Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
                   % (file_field, fn), cs))
    out.append(b"Content-Type: application/pdf\r\n\r\n")
    out.append(data + b"\r\n")
    out.append(("--" + b + "--\r\n").encode())
    return b"".join(out), "multipart/form-data; boundary=" + b


# ----------------------------------------------------------------- 网络
def make_opener(cookie: str, referer: str):
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    op.addheaders = [
        ("Cookie", cookie.strip().encode("latin-1", "ignore").decode("latin-1")),
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/140.0 Safari/537.36 Edg/140.0"),
        ("Referer", referer),
        ("Accept", "text/html,application/xhtml+xml,*/*"),
    ]
    return op


def http(op, url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with op.open(req, timeout=timeout) as r:
            return r.geturl(), r.read()
    except urllib.error.HTTPError as e:
        return url, e.read()


# ----------------------------------------------------------------- 主流程
def _cells(tr_html):
    return re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr_html, re.S | re.I)


def _rows(html):
    """切行：这个系统里 <tr> 常有缺 </tr> 的情况，按 <tr 的位置切更稳"""
    pos = [m.start() for m in re.finditer(r"<tr\b", html, re.I)]
    out = []
    for i, p in enumerate(pos):
        end = pos[i + 1] if i + 1 < len(pos) else len(html)
        chunk = html[p:end]
        cut = chunk.lower().find("</tr>")
        out.append(chunk[:cut] if cut > 0 else chunk)
    return out


def _text(cell_html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell_html or "")).strip()


def kb_of(size_text: str) -> float:
    """把页面上的「736.59 KB」「1.2 MB」转成 KB 数；认不出来返回 0"""
    s = (size_text or "").strip().upper().replace(",", "")
    m = re.search(r"([\d.]+)\s*(GB|MB|KB|B)?", s)
    if not m:
        return 0.0
    try:
        v = float(m.group(1))
    except ValueError:
        return 0.0
    u = m.group(2) or "KB"
    if m.group(2) is None and v > 10000:      # "754265 字节" 这种没写单位
        return v / 1024.0
    return v * {"B": 1 / 1024, "KB": 1, "MB": 1024, "GB": 1024 * 1024}[u]


def kb_uncertainty(size_text: str) -> float:
    """页面显示精度带来的误差（KB）。

    关键：超过 1 MB 之后页面只显示两位小数（如 1.11 MB），
    真实值可能是 1.105~1.115 MB，也就是 ±5.12 KB。
    按 1 KB 容差去比，同一份文件也会被判成"不符"。
    """
    s = (size_text or "").strip().upper().replace(",", "")
    m = re.search(r"([\d.]+)\s*(GB|MB|KB|B)", s)
    if not m:
        return 99.0                       # 认不出来，别拿它下结论
    v, u = m.group(1), m.group(2)
    dec = len(v.split(".")[1]) if "." in v else 0
    half_step = 0.5 * (10 ** -dec)        # 半个最小刻度
    return half_step * {"B": 1 / 1024, "KB": 1, "MB": 1024, "GB": 1024 * 1024}[u] + 0.05


def size_match(display_size: str, local_kb: float, base_tol: float = 1.0) -> bool:
    """页面上的大小文字 和 本地文件大小 是不是同一份（自动考虑显示精度）"""
    v = kb_of(display_size)
    if not v:
        return False
    tol = max(base_tol, kb_uncertainty(display_size))
    return abs(v - local_kb) <= tol


def _hdr(cell_html):
    """表头文字去掉排序箭头：'↑ 题名 ↓' → '题名'"""
    return re.sub(r"[^\u4e00-\u9fa5]", "", _text(cell_html))


def find_attachments(html: str):
    """解析「电子文件上传」那张表：每行 = 一个附件（题名 / 上传者 / 删除链接）

    这个系统的附件表每个单元格都带 class=mtbtl，而且 <tr>/<td> 经常不闭合，
    所以不按 <tr> 切，直接按 mtbtl 单元格每 11 个一组切行（表头也是 11 个）。
    """
    cells = re.findall(r'<td[^>]*class\s*=\s*["\']?mtbtl(?:"|\s)[^>]*>.*?</td>',
                       html, re.S | re.I)
    if len(cells) >= 22:                      # 至少 表头 + 1 行数据
        groups = [cells[i:i + 11] for i in range(0, len(cells) - 10, 11)]
        hdr = [_hdr(c) for c in groups[0]]
        if "上传者" in hdr and "删除" in hdr:
            cols = {t: i for i, t in enumerate(hdr)}
            out = []
            for g in groups[1:]:
                if len(g) < 11:
                    continue
                title, up = _text(g[cols["题名"]]), _text(g[cols["上传者"]])
                if not title or not re.match(r"^\d+$", _text(g[0])):
                    continue
                out.append({"title": title, "uploader": up, "del_html": g[cols["删除"]],
                            "size": _text(g[cols["长度"]]) if "长度" in cols else "",
                            "fmt": _text(g[cols["格式"]]) if "格式" in cols else ""})
            return out

    cols = None
    for row in _rows(html):
        texts = [_hdr(c) for c in _cells(row)]
        if "上传者" in texts and "删除" in texts and "题名" in texts:
            cols = {t: i for i, t in enumerate(texts)}
            break
    if not cols:
        # 退而求其次：找「电子文件上传」之后的第一张表，拿第一行当表头
        idx = html.find("电子文件上传")
        scope = html[idx:] if idx >= 0 else html
        m = re.search(r"<table\b[^>]*>(.*?)</table>", scope, re.S | re.I)
        if m:
            rows2 = _rows(m.group(1))
            if rows2:
                texts = [_hdr(c) for c in _cells(rows2[0])]
                if "上传者" in texts:
                    cols = {t: i for i, t in enumerate(texts)}
    if not cols:
        return []

    out = []
    for row in _rows(html):
        cells = _cells(row)
        if len(cells) < len(cols):
            continue

        def cell(name):
            i = cols.get(name)
            return cells[i] if i is not None and i < len(cells) else ""

        title, up = _text(cell("题名")), _text(cell("上传者"))
        if not title or _hdr(cell("题名")) in ("题名", "序号", ""):
            continue
        out.append({"title": title, "uploader": up, "del_html": cell("删除"),
                    "size": _text(cell("长度")), "fmt": _text(cell("格式"))})
    return out


def del_url(cell_html: str, page_url: str):
    """从「删除」那一格里抠出真正的删除地址"""
    if not cell_html:
        return None
    m = re.search(r'href\s*=\s*["\']?([^"\'>\s]+)', cell_html, re.I)
    if m and "javascript" not in m.group(1).lower():
        return resolve(page_url, html_mod.unescape(m.group(1)))
    for m in re.finditer(r"""['"]([^'"]*(?:op=|act=|del)[^'"]*)['"]""", cell_html, re.I):
        cand = m.group(1)
        if "asp" in cand.lower() or "/" in cand:
            return resolve(page_url, html_mod.unescape(cand))
    return None


def preflight(form):
    """自己判断表单长得对不对，不依赖人眼。返回问题列表（空 = 可以传）"""
    bad = []
    if not form.get("file_field"):
        bad.append("没找到 <input type=file> 控件")
    if not form.get("title_field"):
        bad.append("没找到「文件题名」输入框")
    txt = " ".join(lab for v in form.get("radios", {}).values() for lab in v)
    if "上传整个文件" not in txt:
        bad.append("没找到「上传方式：上传整个文件」这个单选")
    if "不提取全文" not in txt:
        bad.append("没找到「提取全文：不提取全文」这个单选")
    return bad


def load_plan(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("本地文件") or "").strip():
                rows.append(r)
    return rows


def do_dedup(args, op, rows):
    """清理重复附件：同一记录里，同一上传者、长度完全相同的附件，只留一个"""
    only = {int(x) for x in re.findall(r"\d+", args.only)} if args.only else None
    print(f"\n=== 检查重复附件（上传者含「{args.me}」且长度相同，视为同一份）===")
    found = deleted = 0
    for r in rows:
        o = int(r["序号"])
        if only and o not in only:
            continue
        if not (args.start <= o <= args.end):
            continue
        rid = (r.get("文件id") or "").strip()
        if not rid.isdigit():
            continue
        url = f"{args.base}/file/qw/qw_main.asp?id={rid}&op=edit"
        try:
            _f, raw = http(op, url)
        except Exception as e:
            print(f"序号{o} 打不开：{e}")
            continue
        html, _ = decode_html(raw)
        atts = [a for a in find_attachments(html) if args.me and args.me in a["uploader"]]
        by_size = {}
        for a in atts:
            if a.get("size"):
                by_size.setdefault(a["size"], []).append(a)
        for size, g in by_size.items():
            if len(g) < 2:
                continue
            found += 1
            keep = next((x for x in g if x["title"].strip() == (r.get("服务器题名") or "").strip()), g[0])
            print(f"\n序号{o}：{len(g)} 个附件都是 {size}")
            for x in g:
                print(f"   [{'保留' if x is keep else '删除'}] {x['title'][:42]}")
            if not args.commit:
                continue
            for x in g:
                if x is keep:
                    continue
                du = del_url(x["del_html"], url)
                if not du:
                    print(f"   ⚠️ 找不到删除链接：{x['title'][:30]}")
                    continue
                try:
                    http(op, du)
                    deleted += 1
                    print(f"   🗑 已删 {x['title'][:30]}")
                except Exception as e:
                    print(f"   ⚠️ 删除失败：{e}")
    print(f"\n共 {found} 组重复；" + (f"已删 {deleted} 个" if args.commit else "演练，没删任何东西"))
    return 0


def _local_kb(args, r):
    rel = (r.get("本地文件") or "").strip()
    if not rel:
        return 0.0
    p = os.path.join(args.root, rel) if not os.path.isabs(rel) else rel
    return os.path.getsize(p) / 1024.0 if os.path.exists(p) else 0.0


def do_audit(args, op):
    """全库体检：逐条打开记录，拿「本地文件大小」和「线上附件大小」对账

    注意：不能按上传者判断新旧——同一个账号（甚至同一人换了台电脑）会反复上传，
    唯一可靠的判据是文件大小是否与本地那份一致。
    """
    with open(args.plan, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("文件id") or "").strip().isdigit()]
    print(f"\n=== 全库体检：{len(rows)} 条，逐条打开记录（大约 2~3 分钟）===\n")
    rep = os.path.join(OUT, "体检报告.txt")
    fh = open(rep, "w", encoding="utf-8")
    stat = {"ok": [], "diff": [], "extra": [], "empty": [], "nolocal": [], "err": []}
    for i, r in enumerate(rows, 1):
        o, rid = int(r["序号"]), r["文件id"].strip()
        title = (r.get("服务器题名") or "").strip()
        lk = _local_kb(args, r)
        url = f"{args.base}/file/qw/qw_main.asp?id={rid}&op=edit"
        try:
            _f, raw = http(op, url)
        except Exception as e:
            stat["err"].append((o, title, []))
            fh.write(f"{o:>3}  [打不开] {e}\n")
            continue
        html, _ = decode_html(raw)
        atts = find_attachments(html)
        sizes = [a.get("size", "") for a in atts]
        hit = [a for a in atts if lk and size_match(a.get("size", ""), lk, args.kb_tol)]

        if not atts:
            bucket, tag = "empty", "空"
        elif not lk:
            bucket, tag = "nolocal", "本地无文件"
        elif not hit:
            bucket, tag = "diff", "大小不符"
        elif len(atts) > 1:
            bucket, tag = "extra", "多余附件"
        else:
            bucket, tag = "ok", "OK"
        stat[bucket].append((o, title, atts))
        detail = "、".join(s for s in sizes) or "—"
        fh.write(f"{o:>3}  [{tag}]  本地 {lk:.2f} KB | 线上 {detail}　{title[:34]}\n")
        if bucket not in ("ok", "nolocal"):
            print(f"{o:>3}  [{tag}]  本地 {lk:.2f} KB | 线上 {detail}　{title[:30]}")
        if i % 40 == 0:
            print(f"   …… 已检查 {i}/{len(rows)}")
    fh.close()

    print("\n" + "=" * 60)
    print(f"✅ 大小与本地一致：{len(stat['ok'])}")
    print(f"⚠️ 有附件但大小都不对（还是旧文件）：{len(stat['diff'])}")
    print(f"⚠️ 大小对了但还挂着旧附件：{len(stat['extra'])}")
    print(f"○  一个附件都没有：{len(stat['empty'])}")
    print(f"-  本地没文件、未参与：{len(stat['nolocal'])}")
    print(f"✗  打不开：{len(stat['err'])}")
    for key, name in (("diff", "大小不符"), ("extra", "多余"), ("empty", "空")):
        if stat[key]:
            print(f"\n{name}：", ",".join(str(o) for o, _, _ in stat[key]))
    print(f"\n详细清单：{rep}")
    print("  修法：python scripts/3_上传.py --cookie ... --reconcile --commit")
    print("=" * 60)
    return 0


def do_reconcile(args, op, rows):
    """对账修正：让每条记录最终只留下「和本地文件大小一致」的那一个附件

    1) 已经有大小一致的 → 只删多余的旧附件
    2) 没有大小一致的 → 补传，然后再删旧附件
    3) 本地没文件 → 不碰
    """
    only = {int(x) for x in re.findall(r"\d+", args.only)} if args.only else None
    print(f"\n=== 对账修正（{'真改' if args.commit else '只报告，不改'}）===\n")
    fixed = uploaded = deleted = 0
    for r in rows:
        o = int(r["序号"])
        if only and o not in only:
            continue
        if not (args.start <= o <= args.end):
            continue
        rid = (r.get("文件id") or "").strip()
        if not rid.isdigit():
            continue
        rel = (r.get("本地文件") or "").strip()
        local = os.path.join(args.root, rel) if not os.path.isabs(rel) else rel
        if not rel or not os.path.exists(local):
            continue
        title = (r.get("服务器题名") or "").strip()
        lk = os.path.getsize(local) / 1024.0
        url = f"{args.base}/file/qw/qw_main.asp?id={rid}&op=edit"
        try:
            _f, raw = http(op, url)
        except Exception as e:
            print(f"序号{o} 打不开：{e}")
            continue
        html, cs = decode_html(raw)
        atts = find_attachments(html)
        hit = [a for a in atts if size_match(a.get("size", ""), lk, args.kb_tol)]

        if not hit:
            if not args.commit:
                print(f"序号{o} 需要补传（本地 {lk:.2f} KB，线上 {'、'.join(a['size'] for a in atts) or '空'}）")
                continue
            form = parse_form(html, url)
            if not form or preflight(form):
                print(f"序号{o} ❌ 表单结构不对，跳过")
                continue
            body, ctype = build_multipart(
                form["fields"], form["file_field"], os.path.basename(local),
                open(local, "rb").read(), form["title_field"], title, cs,
                "ascii" if args.ascii_filename else "orig")
            try:
                http(op, form["action"], data=body, headers={"Content-Type": ctype})
                uploaded += 1
                print(f"序号{o} ⬆ 已补传 {os.path.basename(local)[:34]}")
            except Exception as e:
                print(f"序号{o} ❌ 补传失败：{e}")
                continue
            time.sleep(args.sleep)
            _f, raw = http(op, url)
            html, cs = decode_html(raw)
            atts = find_attachments(html)
            hit = [a for a in atts if size_match(a.get("size", ""), lk, args.kb_tol)]

        if not hit:
            print(f"序号{o} ⚠️ 补传后仍未看到大小一致的文件，跳过删除")
            continue
        keep = hit[0]
        drop = [a for a in atts if a is not keep]
        if not drop:
            continue
        if not args.commit:
            print(f"序号{o} 需要删 {len(drop)} 个旧附件：{'、'.join(a['size'] for a in drop)}")
            continue
        for a in drop:
            du = del_url(a["del_html"], url)
            if not du:
                print(f"序号{o}   ⚠️ 找不到删除链接：{a['size']}")
                continue
            try:
                http(op, du)
                deleted += 1
                print(f"序号{o}   🗑 删掉旧附件 {a['size']}（{a['uploader']}）")
            except Exception as e:
                print(f"序号{o}   ⚠️ 删除失败：{e}")
        fixed += 1
        time.sleep(args.sleep)

    print(f"\n结果：补传 {uploaded}，清理记录 {fixed}，删附件 {deleted}"
          + ("" if args.commit else "（演练，未改动）"))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=os.path.join(OUT, "upload_plan.csv"))
    ap.add_argument("--root", default=conf.local_root() or ".")
    ap.add_argument("--base", default=conf.base_url())
    ap.add_argument("--cookie", default="")
    ap.add_argument("--only", default="", help="只做某个序号，如 6 或 6,7,8")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=9999)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.4)
    ap.add_argument("--commit", action="store_true", help="真的上传（不加就是演练）")
    ap.add_argument("--probe", action="store_true", help="打印表单解析结果后退出")
    ap.add_argument("--dump-form", default="", help="把某个 id 的表单 HTML 存下来")
    ap.add_argument("--ascii-filename", action="store_true", help="用 ASCII 文件名上传")
    ap.add_argument("--max-fail", type=int, default=3,
                    help="连续失败几次就停下（默认 3，防止配置错了空跑 200 多次）")
    ap.add_argument("--old-owner", default=conf.get("old_uploader", "范芸"),
                    help="旧附件的上传者名字（默认读 config.json 的 old_uploader）")
    ap.add_argument("--no-delete", action="store_true", help="只上传，不删旧文件")
    ap.add_argument("--id-base", type=int, default=int(conf.get("id_base", 0) or 0),
                    help="记录id = 序号 + 这个数（清单里没有 id 时用；默认从 1448 开始试）")
    ap.add_argument("--no-check", action="store_true",
                    help="不核对页面上的档号（如果因为页面显示别的档号而误停，加这个）")
    ap.add_argument("--me", default=conf.get("me", ""),
                    help="你自己的上传者名字（默认读 config.json 的 me）")
    ap.add_argument("--force", action="store_true", help="即使已传过也再传一遍")
    ap.add_argument("--dedup", action="store_true",
                    help="检查/清理重复附件（同一记录里同长度同上传者的只留一个）")
    ap.add_argument("--audit", action="store_true",
                    help="全库体检：逐条比对本地文件大小和线上附件大小")
    ap.add_argument("--reconcile", action="store_true",
                    help="对账修正：缺的补传、大小不符的旧附件删掉，只留和本地一致的那份")
    ap.add_argument("--kb-tol", type=float, default=1.0,
                    help="大小比对容差（KB），默认 1.0")
    args = ap.parse_args()

    import runlog
    runlog.start("3_上传")

    if not args.cookie:
        print("缺少 --cookie，先在浏览器 console 里执行 document.cookie 取值")
        return 1
    op = make_opener(args.cookie, args.base.rstrip("/") + "/")
    os.makedirs(OUT, exist_ok=True)

    if args.dump_form:
        d = args.dump_form.strip()
        if "://" in d:
            url = d                                   # 直接给完整地址
        elif d.startswith("/"):
            url = args.base.rstrip("/") + d
        else:
            url = f"{args.base}/file/qw/qw_main.asp?id={d}&op=edit"
        try:
            final, raw = http(op, url)
        except Exception as e:
            print(f"\n❌ 打不开 {url}")
            print(f"   {e.__class__.__name__}: {e}")
            print("   → 多半是没连校园网，或 cookie 过期了。")
            return 5
        html, cs = decode_html(raw)
        p = os.path.join(OUT, f"form_{args.dump_form}.html")
        open(p, "w", encoding="utf-8").write(html)
        print(f"已保存 {p}（{len(raw)} 字节，页面编码 {cs}）")
        if is_404(html):
            print("❌ 服务器返回 404 —— 地址或 id 不对，内容没取到。")
            print(f"   请到浏览器点开同一条记录，看地址栏真实的 id 是多少。")
            return 6
        n_att = len(find_attachments(html))
        print(f"页面里解析到 {n_att} 个附件行")
        plain = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
        plain = re.sub(r"<[^>]+>", " ", plain)
        plain = re.sub(r"\s+", " ", plain).strip()
        print(f"页面开头文字：{plain[:220]}")
        for a in find_attachments(html):
            u = del_url(a["del_html"], url)
            print(f"   · 题名={a['title'][:24]}  上传者={a['uploader']}  删除链接={'有' if u else '❌没解析到'}")
            if u:
                print(f"     {u}")
            else:
                print(f"     删除单元格原始内容：{a['del_html'][:200]}")
        return 0

    rows = load_plan(args.plan)
    print(f"上传清单 {len(rows)} 条（只含已配好本地文件的）")

    # 「本地文件缺失的条目，保留旧文件」—— 这些记录根本不进 todo，不会上传也不会删
    try:
        with open(args.plan, encoding="utf-8-sig", newline="") as fh:
            nofile = [r for r in csv.DictReader(fh) if not (r.get("本地文件") or "").strip()]
        if nofile:
            print(f"另有 {len(nofile)} 条没有本地文件，本次【不碰】——旧文件原样保留："
                  f"{','.join(r['序号'] for r in nofile[:15])}"
                  + ("…" if len(nofile) > 15 else ""))
    except Exception:
        pass

    if args.audit:
        return do_audit(args, op)

    if args.reconcile:
        return do_reconcile(args, op, rows)

    if args.dedup:
        return do_dedup(args, op, rows)

    only = {int(x) for x in re.findall(r"\d+", args.only)} if args.only else None
    done = set()
    if os.path.exists(LOG):
        for line in open(LOG, encoding="utf-8"):
            try:
                d = json.loads(line)
                if d.get("ok"):
                    done.add(int(d["order"]))
            except Exception:
                pass
        print(f"日志里已成功 {len(done)} 条，会自动跳过")

    todo = []
    for r in rows:
        o = int(r["序号"])
        if only and o not in only:
            continue
        if not (args.start <= o <= args.end):
            continue
        if o in done:
            continue
        todo.append(r)

    print(f"本次待处理 {len(todo)} 条"
          + (f"（最多真传 {args.limit} 条，已传过的会自动越过去）" if args.limit else "")
          + f"；模式 = {'🔴 真实上传' if args.commit else '🟢 演练（不写服务器）'}")

    ok = fail = skip = 0
    consec = 0
    attempted = 0            # 只数"真的动手传"的条数，跳过的不算
    for i, r in enumerate(todo, 1):
        if args.limit and attempted >= args.limit:
            break
        order = int(r["序号"])
        rid = (r.get("文件id") or "").strip()
        title = (r.get("服务器题名") or "").strip()
        rel = (r.get("本地文件") or "").strip()
        local = os.path.join(args.root, rel) if not os.path.isabs(rel) else rel
        tag = f"[{i}/{len(todo)}] 序号{order}"

        if not rid.isdigit():
            # 清单里没有 id 才需要推算；现在已知 id 不是连续的（别的案卷会插进来），
            # 所以没明确给 --id-base 就直接拒绝，不瞎猜
            if not args.id_base:
                print(f"{tag} ❌ 清单里没有「文件id」，又不让推算，已停止。")
                print("   → 请用新版导出脚本重跑一次，把 id 列填上。")
                return 8
            rid = str(args.id_base + order)
        if not os.path.exists(local):
            print(f"{tag} 跳过：本地文件不存在 {local}")
            fail += 1
            continue

        url = f"{args.base}/file/qw/qw_main.asp?id={rid}&op=edit"
        try:
            final, raw = http(op, url)
        except Exception as e:
            print(f"{tag} 打不开页面：{e}")
            fail += 1
            continue
        html, cs = decode_html(raw)
        if "登录" in html and ("password" in html.lower() or "验证码" in html):
            print("❌ 会话失效（跳到登录页），请重新拿 cookie 后再跑")
            return 2
        if is_404(html):
            print(f"{tag} ❌ 打不开 id={rid}（404）")
            print(f"   推算公式是 id = 序号 + {args.id_base or 1448}，说明偏移不对。")
            print("   请到浏览器点开任意一条记录，看地址栏里的 id 是多少，"
                  "再用 --id-base 指定（id 减序号）。")
            return 6

        # 核对：页面上出现的档号必须和清单里这条对得上，防止 id 错位传到别人头上
        dh = (r.get("档号") or "").strip()
        norm_dh = lambda s: re.sub(r"\s+", "", s).upper()
        if dh and not args.no_check:
            found = {norm_dh(x) for x in re.findall(r"NIT-\d{4}-[A-Z0-9]+-[\d.]+", html, re.I)}
            if found and norm_dh(dh) not in found:
                print(f"{tag} ❌ id={rid} 打开的是 {sorted(found)[:2]}，不是 {dh}")
                print("   id 偏移不对，已停止，一个都没传。用 --id-base 指定正确偏移。")
                return 7

        # 已处理判定：看「大小」不看「谁传的」
        # 这个系统的记录会被同一账号反复上传，光看上传者会误判成"已经传好了"
        atts_now = find_attachments(html)
        local_kb = os.path.getsize(local) / 1024.0
        same = [a for a in atts_now if size_match(a.get("size", ""), local_kb, args.kb_tol)]
        if same and not args.force:
            extra = len(atts_now) - len(same)
            msg = f"{tag} ⏭ 跳过：已有同一份（{same[0]['size']}，与本地 {local_kb:.2f} KB 一致）"
            if extra > 0:
                msg += f"；另外还有 {extra} 个大小不符的旧附件，可用 --reconcile 清"
            print(msg)
            skip += 1
            continue

        form = parse_form(html, final)
        if not form:
            print(f"{tag} ❌ 没找到上传表单，先跑 --dump-form {rid} 把 HTML 发我看看")
            fail += 1
            continue

        problems = preflight(form)

        if args.probe:
            print(f"\n=== 检查序号{order}（id={rid}） ===")
            print("  提交地址  :", form["action"])
            print("  file 控件 :", form["file_field"] or "（没找到！）")
            print("  题名字段  :", form["title_field"] or "（没找到！）")
            print("  已选单选  :", json.dumps({k: v for k, v in form["fields"].items()
                                             if k in form["radios"]}, ensure_ascii=False))
            print("  会带上的字段:", ", ".join(form["fields"].keys()))
            print("  页面编码  :", cs)
            if problems:
                print("\n  ❌ 检查不通过：")
                for p in problems:
                    print("     -", p)
                print(f"\n  请把这条命令的输出（或 输出\\form_{rid}.html）发给我，我按真页面改。")
            else:
                print("\n  ✅ 检查通过，可以试着传一个了。")
            return 0

        if problems:
            print(f"{tag} ❌ 页面结构和预期不符：{'；'.join(problems)}")
            print("     已停止。请把 输出\\运行日志.txt 发给我。")
            return 3

        data = open(local, "rb").read()
        atts_before = find_attachments(html)
        n_before = len(atts_before)
        body, ctype = build_multipart(
            form["fields"], form["file_field"], os.path.basename(local), data,
            form["title_field"], title, cs,
            "ascii" if args.ascii_filename else "orig")

        attempted += 1
        if not args.commit:
            print(f"{tag} 演练：{os.path.basename(local)} → {title[:24]}… "
                  f"({len(data)//1024}KB，原有附件 {n_before} 个)")
            continue

        try:
            http(op, form["action"], data=body, headers={"Content-Type": ctype})
        except Exception as e:
            print(f"{tag} ❌ 上传请求失败：{e}")
            fail += 1
            consec += 1
            if consec >= args.max_fail:
                print(f"连续失败 {consec} 次，已停止。请把 输出\\运行日志.txt 发给我。")
                return 4
            continue

        # 拿上传后的页面当凭证（比看返回内容可靠）
        try:
            _f3, raw3 = http(op, url)
        except Exception as e:
            print(f"{tag} ⚠️ 传完了但取不到页面复核：{e}")
            raw3 = b""
        html3, _ = decode_html(raw3) if raw3 else ("", cs)
        atts_after = find_attachments(html3)
        why = []
        if any(title and title.strip() == a["title"].strip() for a in atts_after):
            why.append("附件表里出现了这个题名")
        elif len(atts_after) > n_before:
            why.append(f"附件 {n_before}→{len(atts_after)} 个")
        good = bool(why)
        rec = {"order": order, "id": rid, "title": title, "file": rel,
               "ok": bool(good), "why": why,
               "time": time.strftime("%Y-%m-%d %H:%M:%S"),
               "resp": html3[:200]}
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if good:
            ok += 1
            consec = 0
            print(f"{tag} ✅ {os.path.basename(local)}　（{'／'.join(why)}）")
            # ---- 上传成功后再清理旧附件：只留和本地文件大小一致的那份
            # （不能按「范芸」删了——同一账号以前传的旧文件也会混在里面）
            if not args.no_delete:
                lk = os.path.getsize(local) / 1024.0
                keep = [a for a in atts_after if size_match(a.get("size", ""), lk, args.kb_tol)]
                drop = [a for a in atts_after if a not in keep]
                if not keep:
                    print("     ⚠️ 传完没在页面上看到大小一致的文件，为安全起见不删旧的")
                elif not drop:
                    print("     （没有多余的旧附件，无需删除）")
                else:
                    for a in drop:
                        du = del_url(a["del_html"], url)
                        if not du:
                            print(f"     ⚠️ 旧附件「{a['title'][:20]}」找不到删除链接，请手动删")
                            continue
                        try:
                            http(op, du)
                            print(f"     🗑 已删大小不符的旧附件（{a['uploader']}，{a['size']}）")
                        except Exception as e:
                            print(f"     ⚠️ 删除失败：{e}")
        else:
            fail += 1
            consec += 1
            print(f"{tag} ⚠️ 没看出成功迹象，请到页面确认这条（已记日志）")
            if consec >= args.max_fail:
                print(f"连续失败 {consec} 次，已停止。请把 输出\\运行日志.txt 发给我。")
                return 4
        time.sleep(args.sleep)

    print(f"\n结果：成功 {ok}，失败 {fail}，跳过 {skip}")
    if not args.commit:
        print("这是演练。确认没问题后加 --commit 再跑。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
