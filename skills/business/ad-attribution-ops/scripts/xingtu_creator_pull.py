#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""星图达人侧「我的任务 → 任务详情」逐条取数（浏览器自动化，不用 API）。

背景：星图的开放 API（star_id 1858094343342475 / api.oceanengine.com .../star/mcn/）
里 **没有我方两个号**，按 nick 过滤结果为 0——要拿我方作品数据只能走达人后台页面。

两个号各自的登录态（都在 Mac ~/publish-worker/profiles/ 下，别混）：
  蜡笔新小漫  xingtu author_id 7687937527700783147  douyin 24320990815  → profiles/douyin-webkit（Playwright WebKit）
  漫半拍      xingtu author_id 7687921205772288063  douyin 65813934386  → profiles/douyin（Chrome，CDP 127.0.0.1:9224）

用法（在 Mac 上、用 ~/publish-worker/.venv/bin/python 跑）：
  xingtu_creator_pull.py --mode webkit   # → /tmp/xt_pull_webkit.json
  xingtu_creator_pull.py --mode chrome   # → /tmp/xt_pull_chrome.json（连 CDP，不新起浏览器）
  xingtu_creator_pull.py --build --wk /tmp/xt_pull_webkit.json --ch /tmp/xt_pull_chrome.json \
      --outjson /tmp/xingtu_task_items.json --outcsv /tmp/xingtu_task_items.csv

三条硬知识（踩过，别省）：
 1) 后台任意 /sup/creator/* 冷开会被 SPA 弹回营销首页（URL 变 /?redirect_uri=...）。
    可靠姿势 = 先 goto https://www.xingtu.cn/sup/creator 等 8s（把 app 引导起来），
    再 goto https://www.xingtu.cn/sup/creator/star-ad-unite → 落到 /sup/creator/user/overview，
    然后点侧栏 a[href="/sup/user/task"]（= 我的任务）。
 2) 列表「查看详情」在 WebKit 是**本页跳转**，在 Chrome/CDP 是**新开标签页** → 必须用
    ctx.expect_page() 兜底，两种都要能取。
 3) 卡片里 **值是排在标签前面**的（DOM: <div class=indicator-value>V</div>...<div class=indicator-label>L</div>），
    innerText 也是「值在前、标签在后」；解析要按「取值=标签上方最近的非空行」。
    另：操作列有 is-hidden class，innerText 为空 → 定位按钮必须用 textContent，且按钮在 tr.el-table__row 内。
"""
import re, json, csv, gzip, argparse, pathlib

PROF_WK = '/Users/<MAC_USER>/publish-worker/profiles/douyin-webkit'
CDP_CH = 'http://127.0.0.1:9224'
NAV_JS = """() => { const a = document.querySelector('a[href="/sup/user/task"]'); if (a) { a.click(); return 'anchor_tap'; } return 'none'; }"""
CLICK_JS = """(name) => {
  const rows = [...document.querySelectorAll('tr.el-table__row')];
  for (const r of rows) {
    if ((r.textContent || '').indexOf(name) >= 0) {
      const b = [...r.querySelectorAll('button')].find(x => (x.textContent || '').indexOf('查看详情') >= 0);
      if (!b) return 'no_btn_in_row'; b.click(); return 'ok';
    }
  } return 'no_row';
}"""
PAGER_JS = """(n) => {
  const lis = [...document.querySelectorAll('.el-pager li')];
  const t = lis.find(x => (x.innerText||'').trim() === String(n));
  if (!t) return 'no_pager_' + n;
  if (t.className && t.className.indexOf('disabled') >= 0) return 'disabled_' + n;
  t.click(); return 'clicked_' + n;
}"""
PMAX_JS = """() => {
  const ls = [...document.querySelectorAll('.el-pager li')].map(x => parseInt((x.innerText||'').trim())).filter(x => !isNaN(x));
  return ls.length ? Math.max.apply(null, ls) : 1;
}"""
KEYS = ['火龙漫剧', '星广', '优矩', '新码', '激励', '免费']
UPLOAD = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} 上传$')
PUB = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} 发布$')
LABELS = ['视频评估', '有效播放量', '自然转化量', '预估自然流量收益', '投放流量收益', '已结算收益']
COLS = ['account', 'account_id', 'task_id', 'task_name', 'video_title', 'upload_time', 'publish_time',
        'status', 'video_eval', 'valid_play_cnt', 'natural_convert_cnt', 'est_natural_revenue_yuan',
        'ad_traffic_revenue_yuan', 'settled_revenue_yuan', 'inferred_ad_cost_yuan',
        'source_profile', 'source_url', 'page_no']


def scrape(mode, out_path):
    from playwright.sync_api import sync_playwright
    res = {'mode': mode, 'detail': {}}
    with sync_playwright() as pw:
        if mode == 'webkit':
            ctx = pw.webkit.launch_persistent_context(PROF_WK, headless=True)
            close_ctx = True
        else:
            # 注意：别用 launch_persistent_context——Mac 上没装 ms-playwright 的 chromium 可执行文件，会报
            # Executable doesn't exist。Chrome 是已登录的自动化实例，直接挂 CDP。
            br = pw.chromium.connect_over_cdp(CDP_CH)
            ctx = br.contexts[0]
            close_ctx = False
            for p in list(ctx.pages):
                try:
                    if 'star-ad-unite/detail' in p.url:
                        p.close()
                except Exception:
                    pass
        pg = ctx.new_page()
        pg.goto('https://www.xingtu.cn/sup/creator', wait_until='domcontentloaded', timeout=60000)
        pg.wait_for_timeout(8000)
        pg.goto('https://www.xingtu.cn/sup/creator/star-ad-unite', wait_until='domcontentloaded', timeout=60000)
        pg.wait_for_timeout(12000)
        print('BOOT', pg.url)
        print('NAV', pg.evaluate(NAV_JS))
        pg.wait_for_timeout(9000)
        lt = pg.evaluate('() => document.body.innerText')
        if '我的任务' not in lt:
            print('BLOCKED 未登录或后台结构变了，退出'); print(lt[:400]); return res
        names = []
        for nm in re.findall(r'(火龙漫剧[^\n]{0,60})', lt):
            nm = nm.strip()
            if nm and nm not in names and any(k in nm for k in KEYS):
                names.append(nm)
        print('TASKS', len(names))
        for name in names:
            try:
                with ctx.expect_page(timeout=20000) as pinfo:
                    rr = pg.evaluate(CLICK_JS, name)
                work = pinfo.value
            except Exception:
                work = pg          # WebKit：同页跳转，不新开标签
                rr = 'samepage'
            print('CLICK', name[:30], rr, work.url[:90])
            try:
                work.wait_for_load_state('domcontentloaded', timeout=30000)
            except Exception:
                pass
            work.wait_for_timeout(10000)
            url = work.url
            m = url.split('/detail/')
            tid = m[1].split('?')[0] if len(m) > 1 else name
            try:
                pmax = int(work.evaluate(PMAX_JS))
            except Exception:
                pmax = 1
            pages, n = [], 1
            while True:
                try:
                    pages.append(work.evaluate('() => document.body.innerText'))
                except Exception:
                    pages.append('')
                try:
                    gzip.open(out_path + '.' + tid + '_p' + str(n) + '.html.gz', 'wb').write(work.content().encode('utf-8'))
                except Exception:
                    pass
                n += 1
                if n > pmax or n > 40:
                    break
                rq = work.evaluate(PAGER_JS, n)
                print('  pager', n, rq)
                if str(rq).startswith('no_pager') or str(rq).startswith('disabled'):
                    break
                work.wait_for_timeout(6000)
            res['detail'][tid] = {'task_id': tid, 'demand_name': name, 'url': url, 'pager_max': pmax, 'pages_text': pages}
            json.dump(res, open(out_path, 'w'), ensure_ascii=False)
            if work is not pg:
                try:
                    work.close()
                except Exception:
                    pass
            else:
                pg.goto('https://www.xingtu.cn/sup/creator/star-ad-unite', wait_until='domcontentloaded', timeout=60000)
                pg.wait_for_timeout(9000)
                pg.evaluate(NAV_JS)
                pg.wait_for_timeout(7000)
        try:
            pg.close()
        except Exception:
            pass
        if close_ctx:
            ctx.close()
    return res


def money(s):
    s = str(s or '').replace('￥', '').replace(',', '').strip()
    try:
        return round(float(s), 4)
    except Exception:
        return ''


def intval(s):
    s = str(s or '').strip()
    if s in ('', '--'):
        return ''
    try:
        return int(s)
    except Exception:
        return ''


def parse_detail(detail, account, account_id, profile):
    rows = []
    for tid, v in detail.items():
        for pi, ptxt in enumerate(v.get('pages_text', [])):
            lines = [l.strip() for l in ptxt.split('\n')]
            idxs = [i for i, l in enumerate(lines) if UPLOAD.match(l)]
            for j, i in enumerate(idxs):
                title = lines[i - 1] if i > 0 else ''
                stop = idxs[j + 1] - 1 if j + 1 < len(idxs) else len(lines)
                block = lines[i + 1:stop]
                ne = [x for x in block if x]
                pub, k = '', 0
                if ne and PUB.match(ne[0]):
                    pub = ne[0][:-3].strip(); k = 1
                status = ne[k] if k < len(ne) else ''
                vals = {lab: '' for lab in LABELS}
                for idx in range(len(block)):
                    if block[idx] in LABELS:
                        for b in range(idx - 1, -1, -1):      # 值在上方最近的非空行
                            if block[b]:
                                vals[block[idx]] = block[b]; break
                ad = money(vals['投放流量收益'])
                rows.append({'account': account, 'account_id': account_id, 'task_id': tid,
                             'task_name': v.get('demand_name', ''), 'video_title': title,
                             'upload_time': lines[i][:-3].strip(), 'publish_time': pub, 'status': status,
                             'video_eval': vals['视频评估'], 'valid_play_cnt': intval(vals['有效播放量']),
                             'natural_convert_cnt': intval(vals['自然转化量']),
                             'est_natural_revenue_yuan': money(vals['预估自然流量收益']),
                             'ad_traffic_revenue_yuan': ad,
                             'settled_revenue_yuan': money(vals['已结算收益']),
                             'inferred_ad_cost_yuan': (round(ad / 0.025, 2) if ad != '' else ''),
                             'source_profile': profile, 'source_url': v.get('url', ''), 'page_no': pi + 1})
    return rows


def build(args):
    rows = parse_detail(json.load(open(args.wk))['detail'], '蜡笔新小漫', '7687937527700783147',
                        'profiles/douyin-webkit (Playwright WebKit)')
    if args.ch and pathlib.Path(args.ch).exists():
        rows += parse_detail(json.load(open(args.ch))['detail'], '漫半拍', '7687921205772288063',
                             'profiles/douyin (Chrome via CDP 9224)')
    rows.sort(key=lambda r: (r['account'], r['task_id'],
                             -(r['valid_play_cnt'] if isinstance(r['valid_play_cnt'], int) else -1)))
    agg = {}
    for r in rows:
        t = agg.setdefault((r['account'], r['task_id'], r['task_name']),
                           {'account': r['account'], 'task_id': r['task_id'], 'task_name': r['task_name'],
                            'items': 0, 'valid_play_cnt': 0, 'ad_traffic_revenue_yuan': 0.0, 'settled_revenue_yuan': 0.0})
        t['items'] += 1
        for c in ('valid_play_cnt', 'ad_traffic_revenue_yuan', 'settled_revenue_yuan'):
            if isinstance(r[c], (int, float)):
                t[c] += r[c]
    json.dump({'row_count': len(rows), 'tasks': list(agg.values()), 'items': rows},
              open(args.outjson, 'w'), ensure_ascii=False, indent=1)
    with open(args.outcsv, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in COLS})
    print('ROWS', len(rows))
    for t in agg.values():
        print('TASK %s %s items=%d play=%d adrev=%.2f settled=%.2f' %
              (t['account'], t['task_name'], t['items'], t['valid_play_cnt'],
               t['ad_traffic_revenue_yuan'], t['settled_revenue_yuan']))
    print('OUTJSON', args.outjson, 'OUTCSV', args.outcsv)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['webkit', 'chrome'])
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--wk', default='/tmp/xt_pull_webkit.json')
    ap.add_argument('--ch', default='/tmp/xt_pull_chrome.json')
    ap.add_argument('--outjson', default='/tmp/xingtu_task_items.json')
    ap.add_argument('--outcsv', default='/tmp/xingtu_task_items.csv')
    a = ap.parse_args()
    if a.build:
        build(a)
    else:
        scrape(a.mode, '/tmp/xt_pull_%s.json' % a.mode)
