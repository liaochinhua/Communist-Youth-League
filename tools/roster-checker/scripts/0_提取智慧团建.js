/* ============================================================================
 * 智慧团建 · 团员名单提取
 * ----------------------------------------------------------------------------
 * 用法：
 *   1. 浏览器登录智慧团建，进「团员管理 → 团员列表」
 *   2. 停在【校级】（左边选校团委，右边列出各学院）
 *        → 直接粘本文件，回车：脚本自己遍历所有学院，一个不落
 *      或停在【某个学院】（右边是该学院的支部列表）
 *        → 就只抓这一个学院
 *   3. 跑完在控制台敲：导出      （两个字，回车就下载 CSV）
 *
 * 想手动控制也行：
 *   抓全部学院()     遍历所有学院
 *   抓当前学院()     只抓当前这个学院的支部
 *
 * 脚本只在你自己已登录的浏览器里跑，用你页面自带的登录态，
 * 不会也不需要你的账号密码。导出的数据包含真实姓名，请勿外传。
 *
 * 已知问题：
 *   · 有些团支部「组织树里能点进去、列表页却不显示」（系统 bug），
 *     脚本抓不到，需要手动点进去跑 抓取当前支部()。
 *   · 默认只抓 2026 级；换年级见文件开头「抓哪几届」的说明。
 * ==========================================================================*/

(() => {

// 粘本脚本之前可以先在控制台敲一行来改：
//     要抓的年级 = ['2027']            只抓 2027 级
//     要抓的年级 = 'all'               所有年级
//     排除支部   = /研究生|待转接|教师/
//     只抓这些学院 = ['商学院', '设计学院']     （不设就抓全部学院）
const _want = (typeof window.要抓的年级 !== 'undefined') ? window.要抓的年级 : ['2026'];
const YEARS = (_want === 'all')
  ? []
  : (Array.isArray(_want) ? _want.map(String) : [String(_want)]);

// 年级有两种写法：2026级（大部分）和 26级（有的支部建的时候省了「20」）
const yearPat = YEARS.length
  ? YEARS.map(y => (String(y).length === 4 ? `${y}|${String(y).slice(2)}` : `(?:20)?${y}`)).join('|')
  : '20\\d{2}|\\d{2}';
const FILTER = new RegExp(`(?:${yearPat})级`);

// 支部层要排除的：研究生、待转接
const EXCLUDE = (typeof window.排除支部 !== 'undefined')
  ? new RegExp(window.排除支部)
  : /研究生|待转接/;

// 学院层要排除的：成教、继续教育之类，不是我们要统计的
const COLLEGE_EXCLUDE = /研究生|待转接|成教|继续教育|函授|夜大/;

// 只抓这几个学院（留空 = 全部）
const ONLY = (typeof window.只抓这些学院 !== 'undefined')
  ? window.只抓这些学院
  : (typeof window.只抓学院 !== 'undefined' ? window.只抓学院 : null);

const KEY = 'zhtj_members_v1';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log('[抓取]', ...a);
const warn = (...a) => console.warn('[抓取]', ...a);

const store = JSON.parse(localStorage.getItem(KEY) || '{}');
const save = () => localStorage.setItem(KEY, JSON.stringify(store));

// 之前跑过的话，localStorage 里可能还留着研究生/待转接支部的数据，先清掉
{
  const dirty = Object.keys(store).filter(k => EXCLUDE.test(k));
  if (dirty.length) {
    dirty.forEach(k => delete store[k]);
    save();
    log(`已清掉旧数据里的 ${dirty.length} 个非学生支部：${dirty.join('、')}`);
  }
}

/* ---------------------------------------------------------------------------
 * 页面工具
 * -------------------------------------------------------------------------*/
const rowsOf = () => [...document.querySelectorAll('table tr')]
  .map(tr => ({ tr, cells: [...tr.cells].map(c => c.innerText.trim()) }))
  .filter(o => o.cells.length >= 3);

// 支部行。「团支部」有时被录成「团支书」（真的有人这么建），两种都认
const BRANCH_RE = /团(支部|支书)|级\d+班/;
const looksLikeBranch = n => BRANCH_RE.test(n) && !/学院团委$/.test(n);
const orgRows = () => rowsOf().filter(o => o.cells.some(c => looksLikeBranch(c)));

// 学院行（校级那一层）：名字是「XX学院团委」，不带「团支部」
const collegeRows = () => rowsOf().filter(o =>
  o.cells[1] && o.cells[1].includes('学院') && !o.cells[1].includes('团支部'));

// 当前页码：页面底部有个 [3] 这样的标记
const pageNo = () => {
  const m = document.body.innerText.match(/\[(\d+)\]/);
  return m ? m[1] : '';
};

// 表格首行内容，用来判断翻页有没有生效
const sig = () => (rowsOf()[0]?.cells.slice(1, 3).join('|') || '').slice(0, 40);

const btn = t => [...document.querySelectorAll('a,button,span')]
  .find(e => e.innerText.trim() === t);

const waitFor = async (fn, ms = 8000) => {
  const t = Date.now();
  while (Date.now() - t < ms) { if (fn()) return true; await sleep(200); }
  return false;
};

// 回到第 1 页。
// 注意：支部列表页的分页往往只有「下一页 末页」，没有「首页」，
// 所以不能只点首页——没有就一直点「上一页」退回去。
const toFirstPage = async () => {
  for (let i = 0; i < 40; i++) {
    if (pageNo() === '1') return true;
    const b = btn('首页') || btn('上一页');
    if (!b) return pageNo() === '1';
    const before = pageNo();
    b.click();
    if (!await waitFor(() => pageNo() !== before, 6000)) return false;
  }
  return pageNo() === '1';
};

// 翻页：页码变了 或 首行内容变了 都算成功
const PAGE = async (dir) => {
  const b = btn(dir);
  if (!b) return false;
  const p0 = pageNo(), s0 = sig();
  b.click();
  return await waitFor(() => pageNo() !== p0 || sig() !== s0, 8000);
};

// 团员表：有 11 位手机号的行才算
const phoneRows = () => [...document.querySelectorAll('table tr')]
  .map(tr => [...tr.cells].map(c => c.innerText.trim()))
  .filter(cs => cs.some(c => /^1\d{10}$/.test(c)))
  .map(cs => {
    const i = cs.findIndex(c => /^1\d{10}$/.test(c));
    return { name: cs[i - 1], phone: cs[i], duty: cs[i + 2] || '' };
  });

// 点「眼睛」进下一层。那个图标是 <img>，所以选择器里必须有 img
const clickEye = row => {
  const cell = row.tr.cells[row.tr.cells.length - 1] || row.tr.cells[0];
  const cand = [...cell.querySelectorAll('img,svg,i,a,button,span')];
  // 优先点带 onclick 的（那是站点自己绑的处理器），其次 img，最后才是 <a>
  const el = cand.find(e => e.getAttribute('onclick'))
          || cand.find(e => e.tagName === 'IMG')
          || cand.find(e => e.tagName === 'A')
          || cand[0] || cell;

  // 关键：拦截 <a> 的默认跳转，否则会整页导航到「组织首页」，
  // 之后的每个学院都找不到行了。站点自己的 onclick 仍然会执行。
  const blocker = e => {
    const a = e.target && e.target.closest ? e.target.closest('a') : null;
    if (a && !a.getAttribute('onclick')) e.preventDefault();
  };
  document.addEventListener('click', blocker, true);
  try {
    el.click();                       // 先用原生 click
    if (!el.getAttribute('onclick')) {
      ['mousedown', 'mouseup', 'click'].forEach(t =>
        el.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window })));
    }
  } finally {
    setTimeout(() => document.removeEventListener('click', blocker, true), 50);
  }
};

// 录制：把它调用的接口、参数、返回都打出来。
// 想彻底摆脱"点来点去"就靠这个。
window.录制 = () => {
  if (window.__rec) { warn('已经在录制了'); return; }
  window.__rec = [];

  const dumpBody = b => {
    if (!b) return '';
    if (typeof FormData !== 'undefined' && b instanceof FormData) {
      return [...b.entries()].map(([k, v]) => `${k}=${v}`).join('&');
    }
    if (typeof URLSearchParams !== 'undefined' && b instanceof URLSearchParams) return b.toString();
    return String(b).slice(0, 400);
  };

  const show = (m, u, b, r) => {
    const line = `${m} ${u}\n        参数: ${dumpBody(b)}\n        返回: ${String(r || '').slice(0, 400)}`;
    window.__rec.push(line);
    console.log('[录制]', line);
  };

  // fetch
  const of = window.fetch;
  window.fetch = function (input, init) {
    const u = typeof input === 'string' ? input : input.url;
    const m = (init && init.method) || 'GET';
    return of.apply(this, arguments).then(async res => {
      if (/center/.test(u)) {
        try { show(m, u, init && init.body, await res.clone().text()); } catch (e) {}
      }
      return res;
    });
  };

  // XHR
  const ox = XMLHttpRequest.prototype.open;
  const os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__m = m; this.__u = u; return ox.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) {
    this.addEventListener('load', () => {
      try { if (/center/.test(this.__u)) show(this.__m, this.__u, b, this.responseText); } catch (e) {}
    });
    return os.apply(this, arguments);
  };

  log('开始录制。现在手动点进一个学院、再点进一个支部，然后把控制台里的 [录制] 行复制给我。');
  log('录完敲： 停止录制()');
};
window.停止录制 = () => {
  log(`共录到 ${(window.__rec || []).length} 条`);
  window.__rec = null;
};

// 页面还在不在「团员列表」那张表上
const stillOnList = () => rowsOf().length > 0;

// 排错用：把表格前几行的 HTML 打出来
window.看看行 = () => {
  const rows = rowsOf().slice(0, 3);
  if (!rows.length) { warn('当前页没有表格。先回到「团员管理 → 团员列表」再跑。'); return; }
  rows.forEach((o, i) => {
    log(`--- 第 ${i + 1} 行，共 ${o.tr.cells.length} 格 ---`);
    [...o.tr.cells].forEach((c, j) => {
      log(`  格子${j}: ${c.innerHTML.replace(/\s+/g, ' ').slice(0, 260)}`);
    });
  });
  log('把上面这些复制下来发给写脚本的人，就能对症修改');
};

const back = async () => {
  btn('返回上一级')?.click();
  await sleep(1200);
};

// 在表格里找一行：先回第 1 页，再往后翻；还找不到就往前翻
async function findRow(rowsFn, match) {
  await toFirstPage();
  await sleep(400);

  let row = rowsFn().find(match);
  if (row) return row;

  for (let p = 0; p < 30; p++) {
    if (!await PAGE('下一页')) break;
    await sleep(250);
    row = rowsFn().find(match);
    if (row) return row;
  }

  // 也许目标在第 1 页之前（有些列表会停在中途），往回翻一遍
  for (let p = 0; p < 30; p++) {
    if (!await PAGE('上一页')) break;
    await sleep(250);
    row = rowsFn().find(match);
    if (row) return row;
  }
  return null;
}

const totalPeople = () =>
  Object.values(store).reduce((s, o) => s + Object.keys(o).length, 0);

// 现在在哪一层：表格里有「团支部」= 学院层；有「XX学院」= 校级
const atOrgLevel = () => orgRows().length > 0;
const atCollegeLevel = () => !atOrgLevel() && collegeRows().length > 0;

/* ---------------------------------------------------------------------------
 * 抓当前学院的支部（阶段一 + 阶段二）
 * -------------------------------------------------------------------------*/
async function scrapeCurrentCollege() {
  log('阶段一：收集团支部清单…');
  await toFirstPage();
  await sleep(500);

  const names = new Set(), seen = new Set(), excluded = new Set();
  for (let p = 0; p < 30; p++) {
    orgRows().forEach(o => {
      const n = o.cells[1].replace(/\s+/g, '');
      if (!FILTER.test(n)) return;
      if (EXCLUDE.test(n)) { excluded.add(n); return; }
      names.add(n);
    });
    const s = pageNo() || sig();
    if (seen.has(s)) break;
    seen.add(s);
    if (!await PAGE('下一页')) break;
  }

  const targets = [...names];
  log(`符合条件的团支部 ${targets.length} 个`);
  if (excluded.size) {
    log(`已排除 ${excluded.size} 个非学生支部：`);
    [...excluded].forEach(n => log('   ×', n));
  }
  if (!targets.length) return 0;

  // 阶段二：逐个钻进去
  for (let i = 0; i < targets.length; i++) {
    const name = targets[i];
    if (store[name] && Object.keys(store[name]).length) {
      log(`跳过（已有）${name}`);
      continue;
    }

    const row = await findRow(orgRows, o => o.cells[1].replace(/\s+/g, '') === name);
    if (!row) { log(`✗ 找不到 ${name}（翻完所有页都没有）`); continue; }

    log(`(${i + 1}/${targets.length}) 进入 ${name}`);
    clickEye(row);
    if (!await waitFor(() => phoneRows().length > 0, 12000)) {
      log('  ✗ 没等到团员列表');
      await back();
      continue;
    }

    store[name] = {};
    for (let p = 0; p < 40; p++) {
      const rs = phoneRows();
      rs.forEach(r => { if (r.name) store[name][r.phone || r.name] = { ...r }; });
      log(`  ${name} 第${p + 1}页 +${rs.length} → ${Object.keys(store[name]).length}`);
      const before = rs[0]?.name;
      const nb = btn('下一页');
      if (!nb) break;
      nb.click();
      if (!await waitFor(() => phoneRows()[0]?.name !== before, 8000)) break;
    }

    save();
    await back();
    await waitFor(() => orgRows().length > 0, 10000);
    await sleep(500);
  }
  return targets.length;
}

/* ---------------------------------------------------------------------------
 * 列出校级那一层的所有学院（会翻完所有页）
 * -------------------------------------------------------------------------*/
async function listColleges() {
  await toFirstPage();
  await sleep(800);

  const found = [], seenRow = new Set(), seenPage = new Set();
  for (let p = 0; p < 30; p++) {
    collegeRows().forEach(o => {
      const n = o.cells[1].replace(/\s+/g, '');
      if (!n.includes('学院')) return;
      if (COLLEGE_EXCLUDE.test(n)) return;          // 成教、继续教育这些不要
      if (ONLY && !ONLY.some(k => n.includes(k))) return;
      if (!seenRow.has(n)) { seenRow.add(n); found.push(n); }
    });

    const pg = pageNo() || `sig:${sig()}`;
    if (seenPage.has(pg)) break;
    seenPage.add(pg);
    if (!await PAGE('下一页')) break;
  }

  // 没翻到第 2 页？多半是翻页按钮没点中，提示一下
  if (found.length && found.length <= 10 && pageNo() === '2') {
    warn('只翻到第 1 页就停了，学院可能没收全。先确认页面能翻页再重跑。');
  }
  return found;
}

async function openCollege(name) {
  for (let attempt = 0; attempt < 2; attempt++) {
    await toFirstPage();
    await sleep(500);

    const row = await findRow(collegeRows, o => o.cells[1].replace(/\s+/g, '') === name);
    if (!row) {
      if (!stillOnList()) {
        warn('页面已经不在「团员列表」了（可能被点到了别的链接）。');
        warn('刷新页面、重新进「团员管理 → 团员列表」，再跑一次。');
        throw new Error('left-list-page');
      }
      warn(`  找不到「${name}」这一行`);
      return false;
    }

    clickEye(row);
    if (await waitFor(() => atOrgLevel(), 15000)) return true;   // 等到支部列表出现

    warn(`  点了「${name}」但没进到支部列表，重试…`);
    await back();
    await waitFor(() => atCollegeLevel(), 6000);
  }
  return false;
}

/* ---------------------------------------------------------------------------
 * 对外的两个入口
 * -------------------------------------------------------------------------*/
window.抓当前学院 = async () => {
  log(`范围：${YEARS.length ? YEARS.join(' / ') + ' 级' : '所有年级'}｜排除：${EXCLUDE}`);
  const n = await scrapeCurrentCollege();
  if (!n) {
    warn('这个学院没抓到支部。确认右边显示的是支部列表、并且年级设置对得上。');
    return;
  }
  log(`✅ 本次 ${n} 个团支部，累计 ${Object.keys(store).length} 个支部 / ${totalPeople()} 人`);
  log('💡 接下来在控制台敲两个字：导出');
};

window.抓全部学院 = async () => {
  log(`范围：${YEARS.length ? YEARS.join(' / ') + ' 级' : '所有年级'}｜排除：${EXCLUDE}`);
  const colleges = await listColleges();
  if (!colleges.length) {
    warn('没找到学院列表。先停在校级（左边选校团委）再跑。');
    return;
  }

  log(`共 ${colleges.length} 个学院：${colleges.join('、')}`);
  log('中途别动页面，也别切标签页（切走浏览器会降频，会很慢）');

  const failed = [];
  for (let i = 0; i < colleges.length; i++) {
    const name = colleges[i];
    log(`\n===== (${i + 1}/${colleges.length}) ${name} =====`);
    let opened = false;
    try {
      opened = await openCollege(name);
    } catch (e) {
      if (String(e.message).includes('left-list-page')) {
        warn('已经离开团员列表，后面的学院没法继续了。停止。');
        failed.push(...colleges.slice(i));
        break;
      }
      throw e;
    }
    if (!opened) {
      warn(`✗ 进不去 ${name}，跳过`);
      failed.push(name);
      continue;
    }
    await sleep(600);
    const n = await scrapeCurrentCollege();
    if (!n) {
      warn(`✗ ${name} 里没有符合条件的支部`);
      failed.push(name);
    }
    await back();
    await waitFor(() => atCollegeLevel(), 10000);
    await sleep(800);
  }

  log(`\n✅ 全部完成：${Object.keys(store).length} 个团支部，${totalPeople()} 人`);
  if (failed.length) {
    warn(`以下学院没抓成：${failed.join('、')}`);
    warn('建议改用接口版：敲  接口版()   （不点页面，稳得多）');
  }
  log('💡 接下来在控制台敲两个字：导出');
};

window.抓取当前支部 = async () => {
  const m = document.body.innerText.match(/(\S{2,60}?团支部)\s*共有团员\s*(\d+)\s*人/);
  if (!m) {
    warn('没认出当前是哪个支部。先点进那个支部，让它显示名单。');
    return;
  }

  const name = m[1].replace(/\s+/g, '');
  store[name] = {};
  for (let p = 0; p < 40; p++) {
    const rs = phoneRows();
    rs.forEach(r => { if (r.name) store[name][r.phone || r.name] = { ...r }; });
    log(`  ${name} 第${p + 1}页 +${rs.length} → ${Object.keys(store[name]).length}`);
    const before = rs[0]?.name;
    const nb = btn('下一页');
    if (!nb) break;
    nb.click();
    if (!await waitFor(() => phoneRows()[0]?.name !== before, 8000)) break;
    await sleep(300);
  }
  save();
  log(`✅ 已记录 ${name}：${Object.keys(store[name]).length} 人`);
};

/* ---------------------------------------------------------------------------
 * 导出
 *
 *   导出            ← 推荐，只有两个字，不用敲括号
 *   导出团员()      ← 括号必须是英文半角 ()
 * -------------------------------------------------------------------------*/
window.导出团员 = () => {
  const s = JSON.parse(localStorage.getItem(KEY) || '{}');
  const lines = ['团支部,姓名,手机号,职务'];
  let n = 0;
  for (const org in s) {
    for (const k in s[org]) {
      const r = s[org][k];
      lines.push([org, r.name, r.phone, r.duty].join(','));
      n++;
    }
  }
  if (!n) {
    warn('还没有抓到任何数据，先跑一遍抓取。');
    return;
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(
    new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
  a.download = '智慧团建-团员名单.csv';
  a.click();
  log(`导出 ${n} 条`);
};

/* ---------------------------------------------------------------------------
 * 接口版：不点页面，直接调站点的接口
 *
 * 实测确认的接口（POST + FormData，靠浏览器登录态）：
 *
 *   /v1/center/getorgtree
 *       不传参        → 校级：results.leagueList = 各学院
 *       queryLeagueId → 该学院的子组织：results.leagueList = 各团支部
 *       每条字段：leagueId / leagueName / leagueTypeId / hasChildLeague
 *
 *   /v1/center/tuanyuantw/list
 *       queryLeagueId     支部 id
 *       queryLeagueTypeId 01TZB
 *       sectionName=first
 *       page=1,2,3...
 *       → results.userList = [{name, mobile, ...}]，results.totalNumber
 *
 * 用法：停在校级页面，粘脚本（会自动走这里），或者手动敲  接口版()
 * -------------------------------------------------------------------------*/
window.接口版 = async () => {
  const post = async (url, params) => {
    const body = new FormData();
    Object.entries(params || {}).forEach(([k, v]) => body.append(k, v === undefined ? '' : v));
    const res = await fetch(url, { method: 'POST', body, credentials: 'include' });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch (e) { /* 没登录或者路径不对 */ }
    return { status: res.status, text, json };
  };

  const strip = n => String(n || '').replace(/\s+/g, '');
  const save2 = () => localStorage.setItem(KEY, JSON.stringify(store));

  // 取某个组织的下一级；不传 id 就是校级的那一层
  const getChildren = async id => {
    const params = id ? { queryLeagueId: id, queryLeagueTypeId: '03TW' } : {};
    const r = await post('/v1/center/getorgtree', params);
    const res = r.json && r.json.results;
    if (!res) {
      warn(`取下级失败（HTTP ${r.status}）：${r.text.slice(0, 200)}`);
      return [];
    }
    const arr = res.leagueList || [];
    return arr.map(x => ({
      id: x.leagueId,
      name: strip(x.leagueName),
      typeId: x.leagueTypeId,
      hasChild: x.hasChildLeague,
    }));
  };

  // ---------- ① 各学院 ----------
  log('① 取学院列表…');
  const all = await getChildren('');
  if (!all.length) {
    warn('一个组织都没取到。确认已登录、停在团员列表页。');
    return;
  }
  const colleges = all.filter(c =>
    c.name.includes('学院') &&
    !COLLEGE_EXCLUDE.test(c.name) &&
    (!ONLY || ONLY.some(k => c.name.includes(k))));

  log(`   共 ${all.length} 个组织，其中学院 ${colleges.length} 个：`);
  log('   ' + colleges.map(c => c.name).join('、'));
  if (!colleges.length) { warn('没筛出学院，检查 COLLEGE_EXCLUDE / 只抓这些学院'); return; }

  // ---------- ② 逐个学院 ----------
  const failed = [];
  for (let ci = 0; ci < colleges.length; ci++) {
    const col = colleges[ci];
    log(`\n===== (${ci + 1}/${colleges.length}) ${col.name} =====`);

    let kids = await getChildren(col.id);
    // 有的层级不给子组织列表，退回用 list 接口试一次
    if (!kids.length) {
      const r = await post('/v1/center/tuanyuantw/list',
        { queryLeagueId: col.id, queryLeagueTypeId: '03TW', sectionName: 'first', page: 1 });
      const arr = r.json?.results?.userList || [];
      kids = arr.map(x => ({ id: x.leagueId, name: strip(x.leagueName), hasChild: 1 }));
      if (kids.length) log(`   （用 list 接口取到 ${kids.length} 条）`);
    }

    const branches = kids.filter(b =>
      looksLikeBranch(b.name) && !EXCLUDE.test(b.name) && FILTER.test(b.name));
    log(`   符合年级的支部 ${branches.length} 个`);
    if (!branches.length) {
      if (kids.length) log(`   该学院有 ${kids.length} 个子组织，但都筛掉了。示例：${kids.slice(0, 3).map(k => k.name).join('、')}`);
      failed.push(col.name);
      continue;
    }

    // ---------- ③ 逐个支部取名单 ----------
    for (const br of branches) {
      if (store[br.name] && Object.keys(store[br.name]).length) {
        log(`   跳过（已有）${br.name}`);
        continue;
      }
      store[br.name] = {};
      let total = 0, got = 0;
      for (let page = 1; page <= 100; page++) {
        const r = await post('/v1/center/tuanyuantw/list', {
          queryLeagueId: br.id, queryLeagueTypeId: '01TZB', sectionName: 'first', page,
        });
        const res = r.json && r.json.results;
        if (!res) { warn(`   ${br.name} 第${page}页失败：${r.text.slice(0, 120)}`); break; }
        const arr = res.userList || [];
        total = res.totalNumber || total;
        arr.forEach(u => {
          if (u.name) store[br.name][u.mobile || u.name] = { name: u.name, phone: u.mobile || '', duty: '' };
        });
        got = Object.keys(store[br.name]).length;
        if (!arr.length || got >= total) break;
      }
      save2();
      const flag = total && got < total ? `⚠ 只取到 ${got}/${total}` : '✓';
      log(`   ${flag} ${br.name} → ${got} 人`);
      if (total && got < total) failed.push(`${br.name}（${got}/${total}）`);
    }
  }

  log(`\n✅ 完成：${Object.keys(store).length} 个支部，${totalPeople()} 人`);
  if (failed.length) {
    warn(`这些没抓全，可以重跑（已抓到的会跳过）：${failed.join('；')}`);
  }
  log('💡 接下来敲：导出');
};

// 「括号-free」别名：只敲 `导出` 两个字回车就会触发
Object.defineProperty(window, '导出', {
  configurable: true,
  get() {
    window.导出团员();
    return '（已触发导出，看下载栏）';
  },
});

/* ---------------------------------------------------------------------------
 * 自动执行：判断当前在哪一层，然后干活
 * -------------------------------------------------------------------------*/
(async () => {
  if (atOrgLevel()) {
    await window.抓当前学院();          // 已经在某个学院里，只抓这一个
  } else if (atCollegeLevel()) {
    // 在校级：优先走接口（稳、快）；不行再退回点页面
    log('走接口版（不点页面）');
    await window.接口版();
  } else {
    warn('没看到表格。确认已登录、并停在「团员管理 → 团员列表」页面。');
  }
})();

})();
