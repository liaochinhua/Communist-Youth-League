/* ============================================================================
 * 智慧团建 · 团员名单提取（接口版）
 * ----------------------------------------------------------------------------
 * 只调接口，不点页面。翻页、返回上一级这些操作全都不要了。
 *
 * 用法：
 *   1. 浏览器登录智慧团建（停在哪个页面都行，只要有登录态）
 *   2. F12 → Console/控制台，把本文件整段粘进去，回车
 *   3. 跑完敲两个字：导出
 *
 * 想抓全校（9 个学院）、还是只抓一个学院，靠下面这几个变量控制，
 * 粘脚本之前先在控制台敲一行即可：
 *
 *   只抓这些学院 = ['机械学院']      只抓机械学院
 *   要抓的年级   = ['2027']          换年级（默认 2026）
 *   排除支部     = /研究生|待转接|教师/
 *
 * 数据有更新、想重新抓某个学院：
 *
 *   重抓('机械')                     ← 清掉含"机械"的旧数据，再抓一遍
 *   清空('机械')                     ← 只清不抓
 *   清空全部()                       ← 全部清掉
 * ==========================================================================*/

(() => {

const KEY = 'zhtj_members_v1';

const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log('[抓取]', ...a);
const warn = (...a) => console.warn('[抓取]', ...a);

/* ---------------------------------------------------------------------------
 * 配置：每次调用时现读，这样可以在控制台随时改
 * -------------------------------------------------------------------------*/
function cfg() {
  const want = (typeof window.要抓的年级 !== 'undefined') ? window.要抓的年级 : ['2026'];
  const years = (want === 'all') ? [] : (Array.isArray(want) ? want.map(String) : [String(want)]);

  // 年级有两种写法：2026级（大部分）和 26级（有的支部建库时省了「20」）
  const yearPat = years.length
    ? years.map(y => (String(y).length === 4 ? `${y}|${String(y).slice(2)}` : `(?:20)?${y}`)).join('|')
    : '20\\d{2}|\\d{2}';

  return {
    years,
    filter: new RegExp(`(?:${yearPat})级`),
    exclude: (typeof window.排除支部 !== 'undefined') ? new RegExp(window.排除支部) : /研究生|待转接/,
    only: (typeof window.只抓这些学院 !== 'undefined') ? window.只抓这些学院 : null,
  };
}

// 学院层要排除的：成教、继续教育之类
const COLLEGE_EXCLUDE = /研究生|待转接|成教|继续教育|函授|夜大/;

// 「团支部」偶尔被录成「团支书」，两种都认
const BRANCH_RE = /团(支部|支书)|级\d+班/;
const looksLikeBranch = n => BRANCH_RE.test(n) && !/学院团委$/.test(n);

const strip = n => String(n || '').replace(/\s+/g, '');

/* ---------------------------------------------------------------------------
 * 数据：存在 localStorage，跨次累加
 * -------------------------------------------------------------------------*/
const store = JSON.parse(localStorage.getItem(KEY) || '{}');
const save = () => localStorage.setItem(KEY, JSON.stringify(store));
const totalPeople = () => Object.values(store).reduce((s, o) => s + Object.keys(o).length, 0);

/* ---------------------------------------------------------------------------
 * 接口
 * -------------------------------------------------------------------------*/
async function post(url, params) {
  const body = new FormData();
  Object.entries(params || {}).forEach(([k, v]) => body.append(k, v === undefined ? '' : v));
  const res = await fetch(url, { method: 'POST', body, credentials: 'include' });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch (e) { /* 没登录，或者接口变了 */ }
  return { status: res.status, text, json };
}

// 某个组织的下一级；不传 id 就是校级那一层
async function children(id) {
  const params = id ? { queryLeagueId: id, queryLeagueTypeId: '03TW' } : {};
  const r = await post('/v1/center/getorgtree', params);
  const res = r.json && r.json.results;
  if (!res) {
    warn(`取下级失败（HTTP ${r.status}）：${r.text.slice(0, 200)}`);
    return [];
  }
  return (res.leagueList || []).map(x => ({
    id: x.leagueId,
    name: strip(x.leagueName),
    typeId: x.leagueTypeId,
  }));
}

// 一个支部的全部团员（自动翻页）
async function members(branchId) {
  const out = {};
  let total = 0;
  for (let page = 1; page <= 200; page++) {
    const r = await post('/v1/center/tuanyuantw/list', {
      queryLeagueId: branchId, queryLeagueTypeId: '01TZB', sectionName: 'first', page,
    });
    const res = r.json && r.json.results;
    if (!res) { warn(`  第${page}页失败：${r.text.slice(0, 120)}`); break; }
    const arr = res.userList || [];
    total = res.totalNumber || total;
    arr.forEach(u => {
      if (u.name) out[u.mobile || u.name] = { name: u.name, phone: u.mobile || '', duty: '' };
    });
    if (!arr.length || Object.keys(out).length >= total) break;
  }
  return { people: out, total };
}

/* ---------------------------------------------------------------------------
 * 主流程
 * -------------------------------------------------------------------------*/
window.接口版 = async () => {
  const c = cfg();
  log(`范围：${c.years.length ? c.years.join(' / ') + ' 级' : '所有年级'}｜排除：${c.exclude}`
    + (c.only ? `｜只抓：${c.only.join('、')}` : ''));

  // ① 学院
  const all = await children('');
  if (!all.length) {
    warn('一个组织都没取到。确认已登录智慧团建。');
    return;
  }
  const colleges = all.filter(x =>
    x.name.includes('学院') &&
    !COLLEGE_EXCLUDE.test(x.name) &&
    (!c.only || c.only.some(k => x.name.includes(k))));

  log(`① 组织 ${all.length} 个，其中学院 ${colleges.length} 个：${colleges.map(x => x.name).join('、')}`);
  if (!colleges.length) { warn('没筛出学院。检查「只抓这些学院」写对没有。'); return; }

  let doneBranch = 0, skipBranch = 0;
  const failed = [];

  for (let i = 0; i < colleges.length; i++) {
    const col = colleges[i];
    log(`\n===== (${i + 1}/${colleges.length}) ${col.name} =====`);

    const kids = await children(col.id);
    const branches = kids.filter(b =>
      looksLikeBranch(b.name) && !c.exclude.test(b.name) && c.filter.test(b.name));

    log(`   符合年级的支部 ${branches.length} 个`);
    if (!branches.length) {
      if (kids.length) log(`   该学院有 ${kids.length} 个子组织，但都筛掉了。例子：${kids.slice(0, 3).map(k => k.name).join('、')}`);
      failed.push(col.name);
      continue;
    }

    for (const br of branches) {
      if (store[br.name] && Object.keys(store[br.name]).length) { skipBranch++; continue; }

      const { people, total } = await members(br.id);
      const got = Object.keys(people).length;
      if (got) store[br.name] = people;
      save();
      doneBranch++;

      const flag = (total && got < total) ? '⚠' : '✓';
      log(`   ${flag} ${br.name} → ${got} 人${total && got < total ? `（该支部共 ${total}）` : ''}`);
      if (total && got < total) failed.push(`${br.name}（${got}/${total}）`);
      await sleep(80);                      // 别把服务器打太狠
    }
  }

  log(`\n✅ 本次抓了 ${doneBranch} 个支部，跳过 ${skipBranch} 个（已有）`);
  log(`   累计：${Object.keys(store).length} 个支部 / ${totalPeople()} 人`);
  if (failed.length) {
    warn(`这些没抓全，可以重跑（已抓到的会跳过）：${failed.join('；')}`);
  }
  log('💡 接下来敲两个字：导出');
};

/* ---------------------------------------------------------------------------
 * 清数据：名单更新后必须清，否则会被「跳过（已有）」
 * -------------------------------------------------------------------------*/
window.清空 = (kw) => {
  const keys = Object.keys(store).filter(k => !kw || k.includes(kw));
  if (!keys.length) { log(`没有匹配「${kw}」的数据`); return 0; }
  keys.forEach(k => delete store[k]);
  save();
  log(`已清掉 ${keys.length} 个支部的数据${kw ? `（含「${kw}」的）` : ''}`);
  return keys.length;
};

window.清空全部 = () => {
  const n = Object.keys(store).length;
  if (!n) { log('本来就是空的'); return; }
  if (!confirm(`要清掉全部 ${n} 个支部、${totalPeople()} 人的抓取结果吗？`)) return;
  Object.keys(store).forEach(k => delete store[k]);
  save();
  log(`已清空（原 ${n} 个支部）`);
};

/* ---------------------------------------------------------------------------
 * 重抓：清掉旧数据，再抓一遍
 *   重抓('机械')      只抓名字含"机械"的学院，先清后抓
 *   重抓()            全部重抓（先清空）
 * -------------------------------------------------------------------------*/
window.重抓 = async (kw) => {
  if (kw) {
    window.只抓这些学院 = [kw];
    const n = window.清空(kw);
    log(`将重抓含「${kw}」的数据（清掉 ${n} 个支部）`);
  } else {
    window.只抓这些学院 = null;
    Object.keys(store).forEach(k => delete store[k]);
    save();
    log('将全部重抓');
  }
  await window.接口版();
};

/* ---------------------------------------------------------------------------
 * 导出
 *
 *   导出            ← 推荐，两个字，不用敲括号
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
  if (!n) { warn('还没有数据，先跑 接口版()'); return; }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(
    new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
  a.download = '智慧团建-团员名单.csv';
  a.click();
  log(`导出 ${n} 条`);
};

Object.defineProperty(window, '导出', {
  configurable: true,
  get() {
    window.导出团员();
    return '（已触发导出，看下载栏）';
  },
});

/* ---------------------------------------------------------------------------
 * 粘进来就跑
 * -------------------------------------------------------------------------*/
log('接口版已就绪，开始抓取…');
log('  只抓一个学院：先敲  只抓这些学院 = ["机械学院"]  再跑 接口版()');
log('  数据有更新：  敲  重抓("机械")');
window.接口版();

})();
