/* ============================================================================
 * 全局搜索核对：用系统自带的全员检索，复核「系统里没有」的名单
 * ----------------------------------------------------------------------------
 * 为什么需要这一步：
 *   抓取脚本只能看到「有权限展开的团支部」。如果某个学生在系统里的位置很偏
 *   （挂在待转接、别的学院、往届支部），抓取会报「缺失」，但其实他有账号。
 *   全局搜索是系统级的，不受支部范围限制，正好补这个盲区。
 *
 * 它做不到什么（写清楚，免得误用）：
 *   搜到 2 条时，脚本无法判断是「一人两号」还是「两个同名的人」。
 *   那必须找到本人确认——这一环脚本永远做不到。
 *
 * 用法：
 *   1. 登录智慧团建，点右上角「全局搜索」，确认页面能打开
 *   2. F12 → Console，把本文件整段粘进去
 *   3. 先跑【自检】：确认接口通、结果对得上
 *   4. 把待核对的姓名贴进 RAW（一行一个），再跑【批量核对】
 *   5. 自动下载 CSV，每行一个人、每次命中一行
 * ==========================================================================*/

/* ---------------------------------------------------------------------------
 * 【自检】先跑这个：验证接口是否可用、结果是不是这次的
 * -------------------------------------------------------------------------*/
window.全局搜索自检 = async (name = '张三') => {
  const r = await 单个搜索(name);
  console.log('查询：', name);
  console.log('结果里的 searchName：', r.searchName);
  console.log('命中：', r.users.length, '条');
  r.users.forEach(u => console.log('  ', u.name, '|', u.leagueFullName, '|', u.mobile));
  if (r.searchName && r.searchName !== name) {
    console.warn('⚠ 拿到的不是这次搜索的结果，接口可能没更新');
  } else {
    console.log('✅ 接口正常');
  }
};

/* ---------------------------------------------------------------------------
 * 内部：查一个人
 *   fullSearchUser     —— 执行搜索（带参数）
 *   getFullSearchResult—— 取结果（无参数，返回「上一次搜索」的结果）
 * 这两个必须配合用，单用后一个会一直拿到上一条结果。
 * -------------------------------------------------------------------------*/
async function 单个搜索(name) {
  const csrf = (document.cookie.match(/_csrf=([^;]+)/) || [])[1] || '';
  const H = { 'X-Csrf-Token': csrf };

  const fd = new FormData();
  fd.append('queryUserName', name);
  fd.append('queryLeagueName', '');
  fd.append('queryProvinceId', '');

  await fetch('/v1/center/fullSearchUser',
    { method: 'POST', body: fd, headers: H, credentials: 'include' });

  const r2 = await fetch('/v1/center/getFullSearchResult',
    { method: 'POST', body: new FormData(), headers: H, credentials: 'include' });
  const j = await r2.json();
  const res = j.results || {};
  return {
    searchName: res.searchName || '',
    users: res.userList || [],
  };
}

/* ---------------------------------------------------------------------------
 * 【批量核对】
 * -------------------------------------------------------------------------*/
window.全局搜索批量 = async () => {
  // ① 把名字贴这里，一行一个（从「缺失名单.txt」直接复制）
  const RAW = `
张三
李四
`;
  const NAMES = [...new Set(RAW.split(/[\s,，]+/).filter(Boolean))];
  if (!NAMES.length) { console.warn('先把名字贴进 RAW'); return; }

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const out = [];

  for (let i = 0; i < NAMES.length; i++) {
    const name = NAMES[i];
    try {
      const r = await 单个搜索(name);
      out.push({ name, users: r.users, stale: r.searchName && r.searchName !== name });
      console.log(`${i + 1}/${NAMES.length} ${name}: ${r.users.length} 条`,
        r.users.map(u => u.leagueFullName).join(' | '));
    } catch (e) {
      out.push({ name, users: [], error: String(e) });
      console.warn(`${name} 查询失败`, e);
    }
    await sleep(400);            // 别把服务器打爆
  }

  const none = out.filter(o => !o.users.length).map(o => o.name);
  const multi = out.filter(o => o.users.length > 1);
  console.log('---- 汇总 ----');
  console.log('查无此人：', none.length, none.join(' '));
  console.log('命中多个：', multi.length);
  multi.forEach(o => console.log('  ', o.name, o.users.length, '个 —— 需人工确认是重名还是一人两号'));
  if (out.some(o => o.stale)) console.warn('⚠ 有结果对不上查询名，建议重跑');
  window.__搜索结果 = out;

  // ② 导出 CSV
  const lines = ['姓名,命中数,所在团支部,手机号'];
  for (const o of out) {
    if (!o.users.length) lines.push(`${o.name},0,,`);
    else o.users.forEach(u => lines.push([o.name, o.users.length, u.leagueFullName, u.mobile].join(',')));
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['\uFEFF' + lines.join('\r\n')],
    { type: 'text/csv;charset=utf-8' }));
  a.download = '全局搜索结果.csv';
  a.click();
};
