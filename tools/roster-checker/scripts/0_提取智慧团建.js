/* ============================================================================
 * 智慧团建 · 团员名单提取
 * ----------------------------------------------------------------------------
 * 用法：
 *   1. 浏览器登录智慧团建，进「团员管理 → 团员列表」
 *   2. 点进某个学院，让页面显示该学院的团支部列表
 *   3. 按 F12 → Console，把本文件整段粘进去，回车
 *   4. 跑完会提示执行 导出团员()，再粘一次导出函数并执行，得到 CSV
 *
 * 脚本只在你自己已登录的浏览器里跑，用你页面自带的登录态，
 * 不会也不需要你的账号密码。导出的数据包含真实姓名，请勿外传。
 *
 * 已知问题：
 *   · 有些团支部「组织树里能点进去、列表页却不显示」（系统 bug），
 *     脚本抓不到，需要手动点进去跑文件末尾的【单个支部抓取】。
 *   · 只按团支部名筛选，往届/待转接支部请改 FILTER。
 * ==========================================================================*/

(async () => {
  const KEY = 'zhtj_members_v1';        // localStorage 里的暂存键

  // ★ 每年只需要改这一行 ★
  // 只抓新生：['2027']
  // 连老团员一起抓：['2023','2024','2025','2026']
  const YEARS = ['2026'];
  const FILTER = new RegExp('(' + YEARS.join('|') + ')级');

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const store = JSON.parse(localStorage.getItem(KEY) || '{}');
  const log = (...a) => console.log('[抓取]', ...a);

  // 当前页的团支部行（学院层级）
  const orgRows = () => [...document.querySelectorAll('table tr')]
    .map(tr => ({ tr, cells: [...tr.cells].map(c => c.innerText.trim()) }))
    .filter(o => o.cells.length >= 4 && o.cells.some(c => c.includes('团支部')));

  // 页签名：用第一行的支部名判断有没有翻页成功
  const sig = () => (orgRows()[0]?.cells[1] || '').slice(0, 20);

  // 分页按钮（首页/上一页/下一页/末页）
  const btn = t => [...document.querySelectorAll('a,button,span')]
    .find(e => e.innerText.trim() === t);

  const waitFor = async (fn, ms = 8000) => {
    const t = Date.now();
    while (Date.now() - t < ms) { if (fn()) return true; await sleep(200); }
    return false;
  };

  const PAGE = async (dir) => {
    const b = btn(dir);
    if (!b) return false;
    const before = sig();
    b.click();
    return await waitFor(() => sig() !== before, 6000);
  };

  // 团员表：有 11 位手机号的行才算
  const phoneRows = () => [...document.querySelectorAll('table tr')]
    .map(tr => [...tr.cells].map(c => c.innerText.trim()))
    .filter(cs => cs.some(c => /^1\d{10}$/.test(c)))
    .map(cs => {
      const i = cs.findIndex(c => /^1\d{10}$/.test(c));
      return { name: cs[i - 1], phone: cs[i], duty: cs[i + 2] || '' };
    });

  // ---------- 阶段一：把所有页的团支部列出来 ----------
  log('阶段一：收集团支部清单…');
  await PAGE('首页');
  await sleep(500);
  const names = new Set(), seen = new Set();
  for (let p = 0; p < 20; p++) {
    orgRows().forEach(o => {
      const n = o.cells[1].replace(/\s+/g, '');
      if (FILTER.test(n)) names.add(n);
    });
    if (seen.has(sig())) break;
    seen.add(sig());
    if (!await PAGE('下一页')) break;
  }
  const targets = [...names];
  log(`符合 ${FILTER} 的团支部 ${targets.length} 个`);
  if (!targets.length) {
    console.warn('一个都没匹配上。当前页看到的支部名：');
    orgRows().forEach(o => console.log('   ', o.cells[1]));
    return;
  }

  // ---------- 阶段二：逐个钻进去抓 ----------
  for (let i = 0; i < targets.length; i++) {
    const name = targets[i];
    if (store[name] && Object.keys(store[name]).length) {
      log(`跳过（已有）${name}`);
      continue;
    }

    await PAGE('首页');                       // 每次都从首页找，避免只往后翻
    await sleep(400);
    let row = null;
    for (let p = 0; p < 20; p++) {
      row = orgRows().find(o => o.cells[1].replace(/\s+/g, '') === name);
      if (row) break;
      if (!await PAGE('下一页')) break;
    }
    if (!row) { log(`✗ 找不到 ${name}`); continue; }

    log(`(${i + 1}/${targets.length}) 进入 ${name}`);
    (row.tr.querySelector('i,svg,a,button,[class*="icon"]') || row.tr.cells[3]).click();
    if (!await waitFor(() => phoneRows().length > 0, 10000)) {
      log('  ✗ 没等到团员列表');
      btn('返回上一级')?.click();
      await sleep(1200);
      continue;
    }

    store[name] = {};
    for (let p = 0; p < 30; p++) {
      const rs = phoneRows();
      rs.forEach(r => { if (r.name) store[name][r.phone || r.name] = { ...r }; });
      log(`  ${name} 第${p + 1}页 +${rs.length} → ${Object.keys(store[name]).length}`);
      const before = rs[0]?.name;
      const nb = btn('下一页');
      if (!nb) break;
      nb.click();
      if (!await waitFor(() => phoneRows()[0]?.name !== before, 6000)) break;
    }

    localStorage.setItem(KEY, JSON.stringify(store));
    btn('返回上一级')?.click();
    await waitFor(() => orgRows().length > 0, 8000);
    await sleep(500);
  }

  const total = Object.values(store).reduce((s, o) => s + Object.keys(o).length, 0);
  log(`✅ 完成：${Object.keys(store).length} 个团支部，${total} 人`);
  log('💡 接着执行：导出团员()');
})();


/* ---------------------------------------------------------------------------
 * 导出函数：装一次，随时 `导出团员()` 下载 CSV
 * -------------------------------------------------------------------------*/
window.导出团员 = () => {
  const store = JSON.parse(localStorage.getItem('zhtj_members_v1') || '{}');
  const lines = ['团支部,姓名,手机号,职务'];
  let n = 0;
  for (const org in store) {
    for (const k in store[org]) {
      const r = store[org][k];
      lines.push([org, r.name, r.phone, r.duty].join(','));
      n++;
    }
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(
    new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
  a.download = '智慧团建-团员名单.csv';
  a.click();
  console.log('导出', n, '条');
};


/* ---------------------------------------------------------------------------
 * 【单个支部抓取】—— 应对「组织树可进、列表页不显示」的幽灵支部
 *   手动点进那个支部，让它显示名单，再跑这段
 * -------------------------------------------------------------------------*/
window.抓取当前支部 = async () => {
  const KEY = 'zhtj_members_v1';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const store = JSON.parse(localStorage.getItem(KEY) || '{}');

  const m = document.body.innerText.match(/(\S{2,60}?团支部)\s*共有团员\s*(\d+)\s*人/);
  if (!m) {
    console.warn('没识别到支部名（有些异常支部连标题都不显示），请手工建一个 key');
    return;
  }
  const org = m[1].replace(/\s+/g, ''), total = +m[2];

  const rows = () => [...document.querySelectorAll('table tr')]
    .map(tr => [...tr.cells].map(c => c.innerText.trim()))
    .filter(cs => cs.some(c => /^1\d{10}$/.test(c)))
    .map(cs => {
      const i = cs.findIndex(c => /^1\d{10}$/.test(c));
      return { name: cs[i - 1], phone: cs[i], duty: cs[i + 2] || '' };
    });

  store[org] = {};
  for (let p = 0; p < 20; p++) {
    const rs = rows();
    rs.forEach(r => { if (r.name) store[org][r.phone || r.name] = { ...r }; });
    console.log(`${org} 第${p + 1}页 +${rs.length} → ${Object.keys(store[org]).length}/${total}`);
    const nb = [...document.querySelectorAll('a,button,span')]
      .find(e => e.innerText.trim() === '下一页');
    if (!nb) break;
    const before = rs[0]?.name;
    nb.click();
    let ok = false;
    for (let i = 0; i < 20; i++) { await sleep(200); if (rows()[0]?.name !== before) { ok = true; break; } }
    if (!ok) break;
  }
  localStorage.setItem(KEY, JSON.stringify(store));
  console.log(`✅ ${org} 共 ${Object.keys(store[org]).length} 人`);
};
