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
 *     脚本抓不到，需要手动点进去跑文件末尾的【单个支部抓取】。
 *   · 默认只抓 2026 级；换年级见文件开头「抓哪几届」的说明。
 * ==========================================================================*/

/* ---------------------------------------------------------------------------
 * 抓哪几届、排除哪些
 * -------------------------------------------------------------------------*/
// 粘本脚本之前可以先在控制台敲一行来改：
//     要抓的年级 = ['2027']            只抓 2027 级
//     要抓的年级 = 'all'               所有年级
//     排除支部   = /研究生|待转接|教师/
(() => {

const _want = (typeof window.要抓的年级 !== 'undefined') ? window.要抓的年级 : ['2026'];
const YEARS = (_want === 'all')
  ? []
  : (Array.isArray(_want) ? _want.map(String) : [String(_want)]);

// 年级有两种写法：2026级（大部分）和 26级（有的支部建的时候省了「20」）
const yearPat = YEARS.length
  ? YEARS.map(y => (String(y).length === 4 ? `${y}|${String(y).slice(2)}` : `(?:20)?${y}`)).join('|')
  : '20\\d{2}|\\d{2}';
const FILTER = new RegExp(`(?:${yearPat})级`);

const EXCLUDE = (typeof window.排除支部 !== 'undefined')
  ? new RegExp(window.排除支部)
  : /研究生|待转接/;

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

// 支部行：名字里带「团支部」
const orgRows = () => rowsOf().filter(o => o.cells.some(c => c.includes('团支部')));

// 学院行（校级那一层）：名字是「XX学院团委」，不带「团支部」
const collegeRows = () => rowsOf().filter(o =>
  o.cells[1] && o.cells[1].includes('学院') && !o.cells[1].includes('团支部'));

const sig = () => (rowsOf()[0]?.cells[1] || '').slice(0, 20);

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

const clickEye = row =>
  (row.tr.querySelector('i,svg,a,button,[class*="icon"]') || row.tr.cells[row.tr.cells.length - 1]).click();

const back = async () => {
  btn('返回上一级')?.click();
  await sleep(1200);
};

const totalPeople = () =>
  Object.values(store).reduce((s, o) => s + Object.keys(o).length, 0);

/* ---------------------------------------------------------------------------
 * 抓当前学院的支部（阶段一 + 阶段二）
 * -------------------------------------------------------------------------*/
async function scrapeCurrentCollege() {
  log('阶段一：收集团支部清单…');
  await PAGE('首页');
  await sleep(500);

  const names = new Set(), seen = new Set(), excluded = new Set();
  for (let p = 0; p < 20; p++) {
    orgRows().forEach(o => {
      const n = o.cells[1].replace(/\s+/g, '');
      if (!FILTER.test(n)) return;
      if (EXCLUDE.test(n)) { excluded.add(n); return; }
      names.add(n);
    });
    if (seen.has(sig())) break;
    seen.add(sig());
    if (!await PAGE('下一页')) break;
  }

  const targets = [...names];
  log(`符合条件的团支部 ${targets.length} 个`);
  if (excluded.size) {
    log(`已排除 ${excluded.size} 个非学生支部：`);
    [...excluded].forEach(n => log('   ×', n));
  }
  if (!targets.length) return 0;

  // 阶段二
  for (let i = 0; i < targets.length; i++) {
    const name = targets[i];
    if (store[name] && Object.keys(store[name]).length) {
      log(`跳过（已有）${name}`);
      continue;
    }

    await PAGE('首页');
    await sleep(400);
    let row = null;
    for (let p = 0; p < 20; p++) {
      row = orgRows().find(o => o.cells[1].replace(/\s+/g, '') === name);
      if (row) break;
      if (!await PAGE('下一页')) break;
    }
    if (!row) { login_fail_warn(); log(`✗ 找不到 ${name}`); continue; }

    log(`(${i + 1}/${targets.length}) 进入 ${name}`);
    clickEye(row);
    if (!await waitFor(() => phoneRows().length > 0, 10000)) {
      log('  ✗ 没等到团员列表');
      await back();
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

    save();
    await back();
    await waitFor(() => orgRows().length > 0, 8000);
    await sleep(500);
  }
  return targets.length;
}

function login_fail_warn() {
  if (!document.body.innerText.includes('团员')) {
    warn('页面看起来不像团员列表，可能掉登录了。刷新重新登录后再跑。');
  }
}

/* ---------------------------------------------------------------------------
 * 列出校级那一层的所有学院
 * -------------------------------------------------------------------------*/
async function listColleges() {
  await PAGE('首页');
  await sleep(600);
  const found = new Set(), seen = new Set();
  for (let p = 0; p < 20; p++) {
    collegeRows().forEach(o => {
      const n = o.cells[1].replace(/\s+/g, '');
      if (!n.includes('学院')) return;          // 直属团总支、生活园区团工委之类不要
      if (EXCLUDE.test(n)) return;              // 待转接、研究生这些也不要
      found.add(n);
    });
    if (seen.has(sig())) break;
    seen.add(sig());
    if (!await PAGE('下一页')) break;
  }
  return [...found];
}

async function openCollege(name) {
  await PAGE('首页');
  await sleep(500);
  let row = null;
  for (let p = 0; p < 20; p++) {
    row = collegeRows().find(o => o.cells[1].replace(/\s+/g, '') === name);
    if (row) break;
    if (!await PAGE('下一页')) break;
  }
  if (!row) return false;
  clickEye(row);
  // 等到右边变成支部列表
  return await waitFor(() => orgRows().length > 0 && orgRows()[0].cells[1].includes('团支部'), 10000);
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
    warn('没找到学院列表。先停在校级（左边选校团委），再跑。');
    return;
  }

  log(`共 ${colleges.length} 个学院：${colleges.join('、')}`);
  log('中途别动页面，也别切标签页（切走浏览器会降频，会很慢）');

  const failed = [];
  for (let i = 0; i < colleges.length; i++) {
    const name = colleges[i];
    log(`\n===== (${i + 1}/${colleges.length}) ${name} =====`);
    if (!await openCollege(name)) {
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
    await waitFor(() => collegeRows().length > 0, 10000);
    await sleep(800);
  }

  log(`\n✅ 全部完成：${Object.keys(store).length} 个团支部，${totalPeople()} 人`);
  if (failed.length) {
    warn(`以下学院没抓成，需要手动补：${failed.join('、')}`);
  }
  log('💡 接下来在控制台敲两个字：导出');
};

window.抓取当前支部 = async () => {
  const sleep2 = ms => new Promise(r => setTimeout(r, ms));
  const m = document.body.innerText.match(/(\S{2,60}?团支部)\s*共有团员\s*(\d+)\s*人/);
  if (!m) {
    warn('没认出当前是哪个支部。先点进那个支部，让它显示名单。');
    return;
  }

  const name = m[1].replace(/\s+/g, '');
  store[name] = {};
  for (let p = 0; p < 30; p++) {
    const rs = phoneRows();
    rs.forEach(r => { if (r.name) store[name][r.phone || r.name] = { ...r }; });
    console.log('[抓取]', `  ${name} 第${p + 1}页 +${rs.length} → ${Object.keys(store[name]).length}`);
    const before = rs[0]?.name;
    const nb = btn('下一页');
    if (!nb) break;
    nb.click();
    if (!await waitFor(() => phoneRows()[0]?.name !== before, 6000)) break;
    await sleep2(300);
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
  const hasOrg = orgRows().length > 0;
  const hasCollege = collegeRows().length > 0;

  if (hasOrg) {
    // 已经在某个学院里了，只抓当前学院
    await window.抓当前学院();
  } else if (hasCollege) {
    await window.抓全部学院();
  } else {
    warn('没看到表格。确认已登录、并停在「团员管理 → 团员列表」页面。');
  }
})();

})();
