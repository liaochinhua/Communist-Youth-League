/* =====================================================================
   1_导出服务器清单.js  (v2)
   用途：把服务器上的记录导出成 records.csv（序号 / 档号 / 题名 / 文件id / 全文数）

   用法：
   1) Edge 登录档案系统，打开 238 条记录的那个列表页
   2) F12 → 控制台 → 粘贴本文件全部内容 → 回车
   3) 它会自动翻页；翻不动也没关系 —— 手动点"下一页"，再按一下"上箭头回车"重跑一次
      （结果存在浏览器里自动合并，不重复、不覆盖）

   想清空重来：控制台里输入   清空导出()   回车
   ===================================================================== */
(async () => {
  const KEY = 'tuanwei_records_v3';
  const TOTAL = 238;   // ← 你这个案卷一共多少条记录，按实际改（只影响最后"缺哪些序号"的提示）
  const DH_RE = /^NIT[-\s]/i;   // ← 档号前缀，按你的系统改（如 /^WS[-\s]/i）
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /* ---------- 1. 找到装着表格的 document（可能有 iframe） ---------- */
  function allDocs(root, out = [], depth = 0) {
    if (!root || depth > 4) return out;
    let frames = [];
    try { frames = Array.from(root.querySelectorAll('iframe, frame')); } catch (e) { }
    for (const f of frames) {
      let d = null;
      try { d = f.contentDocument; } catch (e) { d = null; }
      if (d) { out.push(d); allDocs(d, out, depth + 1); }
    }
    return out;
  }
  function pickDoc() {
    const docs = [document, ...allDocs(document)];
    for (const d of docs) {
      try {
        const txt = d.body ? d.body.innerText : '';
        if (/档号/.test(txt) && d.querySelectorAll('tr').length > 3) return d;
      } catch (e) { }
    }
    return document;
  }
  const doc = pickDoc();

  /* ---------- 2. 抓当前页 ---------- */
  function grabPage() {
    const rows = [];
    for (const tr of doc.querySelectorAll('tr')) {
      const tds = Array.from(tr.cells || []);
      if (!tds.length) continue;
      const cells = tds.map((td) => (td.innerText || '').replace(/\s+/g, ' ').trim());

      const dh = cells.find((c) => DH_RE.test(c)) || '';
      if (!dh) continue;

      let order = null;
      for (const c of cells) if (/^\d{1,3}$/.test(c)) { order = parseInt(c, 10); break; }
      if (order === null) continue;

      let title = '';
      for (const c of cells) {
        if (!c || DH_RE.test(c) || /^\d+$/.test(c)) continue;
        if (c.length > title.length && /[\u4e00-\u9fa5]/.test(c)) title = c;
      }

      // 文件 id：一列一列地试，谁先命中用谁
      // ① 行内复选框/隐藏域的 value（这类系统最常见的做法）  ② qw_main.asp?...id=  ③ onclick 里的数字
      const raw = tr.innerHTML || '';
      let id = null;
      for (const inp of tr.querySelectorAll('input')) {
        const v = (inp.value || '').trim();
        if (/^\d{3,6}$/.test(v)) { id = parseInt(v, 10); break; }
      }
      if (!id) {
        let m = raw.match(/qw_main\.asp\?[^"'<>]*?id=(\d+)/i);
        if (m) id = parseInt(m[1], 10);
      }
      if (!id) {
        let m = raw.match(/(?:open|show|view|edit|file|qw)[A-Za-z_]*\s*\(\s*['"]?\d*['"]?\s*[,({'"]?\s*(\d{3,6})/i);
        if (m) id = parseInt(m[1], 10);
      }
      if (!id) {
        let m = raw.match(/[?&]id=(\d{3,6})/);
        if (m) id = parseInt(m[1], 10);
      }

      const numCells = cells.filter((c) => /^\d{1,3}$/.test(c));
      const fulltext = numCells.length >= 2 ? numCells[1] : '';

      rows.push({ order, dh, title, id, fulltext });
    }
    return rows;
  }

  /* ---------- 3. 合并进浏览器存储（按【序号】存，不能按档号！） ---------- */
  // 坑：序号 11 和 12 的档号都是 NIT-2025-DQ17-1.0010，按档号存会把 11 覆盖掉
  const store = JSON.parse(localStorage.getItem(KEY) || '{}');
  const rows = grabPage();
  let added = 0;
  for (const r of rows) {
    if (!store[r.order]) added++;
    store[r.order] = Object.assign(store[r.order] || {}, r);
  }
  localStorage.setItem(KEY, JSON.stringify(store));
  console.log(`本页 ${rows.length} 行，新增 ${added}，累计 ${Object.keys(store).length} 条`);

  /* ---------- 4. 试着自动翻页（翻不动就靠手动） ---------- */
  const sig = () => grabPage().map((r) => r.dh).join('|');
  const before = sig();
  let next = null;
  for (const el of doc.querySelectorAll('a, input, button, span, img, td, div')) {
    const t = ((el.innerText || el.value || el.getAttribute('alt') || el.title || '') + '').trim();
    const oc = el.getAttribute('onclick') || '';
    if (/^(下一页|下页|›|»|>)$/.test(t) || /nextpage|NextPage|pageNext/i.test(oc)) { next = el; break; }
  }
  if (next) {
    next.click();
    for (let i = 0; i < 25; i++) {
      await sleep(200);
      if (sig() && sig() !== before) { console.log('翻到下一页了，再抓一次…'); break; }
    }
    const rows2 = grabPage();
    if (rows2.map((r) => r.dh).join('|') !== before) {
      const st2 = JSON.parse(localStorage.getItem(KEY) || '{}');
      let add2 = 0;
      for (const r of rows2) { if (!st2[r.order]) add2++; st2[r.order] = Object.assign(st2[r.order] || {}, r); }
      localStorage.setItem(KEY, JSON.stringify(st2));
      console.log(`第 2 页再 +${add2}，累计 ${Object.keys(st2).length} 条`);
    }
  } else {
    console.log('没找到"下一页"按钮 —— 手动点下一页，再跑一次本脚本，会自动合并。');
  }

  /* ---------- 5. 导出 ---------- */
  const all = Object.values(JSON.parse(localStorage.getItem(KEY) || '{}'))
    .sort((a, b) => a.order - b.order);
  const esc = (v) => {
    const s = (v === null || v === undefined) ? '' : String(v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const lines = ['序号,档号,题名,文件id,全文数'];
  for (const r of all) lines.push([r.order, r.dh, r.title, r.id ?? '', r.fulltext].map(esc).join(','));
  const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'records.csv';
  document.body.appendChild(a); a.click(); a.remove();

  const have = new Set(all.map((r) => r.order));
  const miss = [];
  for (let i = 1; i <= TOTAL; i++) if (!have.has(i)) miss.push(i);
  const noId = all.filter((r) => !r.id);

  console.log(`%c✅ 共 ${all.length} 条，已下载 records.csv`, 'color:#0a0;font-weight:bold');
  if (miss.length) console.warn('缺这些序号：', miss.join(','));
  if (noId.length) {
    console.warn(`有 ${noId.length} 条没抓到文件id（不影响，上传脚本会按 序号+偏移 推算）`);
    // 抽一行把「全文」那一带的 HTML 打出来，供排查
    const trs = Array.from(doc.querySelectorAll('tr'));
    const one = trs.find((t) => (t.innerHTML || '').includes('NIT-'));
    if (one) {
      const cells = Array.from(one.cells || []).map((c, i) => `[${i}]${(c.innerHTML || '').slice(0, 90)}`);
      console.log('样例行每个单元格的 HTML：');
      cells.forEach((c) => console.log('   ', c));
    }
  }
  window.清空导出 = () => { localStorage.removeItem(KEY); console.log('已清空，重新跑一次即可'); };
  return all.length;
})();
