#!/usr/bin/env python3
"""
头条文章展现量/阅读量/评论/收藏/点赞/分享数据抓取工具
用法:
  python3 toutiao_metrics_v2.py <文章URL或group_id>
  python3 toutiao_metrics_v2.py https://www.toutiao.com/article/7661524195775463970/
  python3 toutiao_metrics_v2.py 7661524195775463970
  python3 toutiao_metrics_v2.py url1 url2 url3  (批量)
"""

import asyncio, re, json, sys, urllib.parse
from playwright.async_api import async_playwright

async def get_article_metrics(page, article_url, title_hint=""):
    """打开文章页，提取showCount/readCount/repinCount等"""
    try:
        if article_url.startswith("http"):
            url = article_url
        else:
            url = f"https://www.toutiao.com/article/{article_url}"

        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        html = await page.content()

        metrics = {}
        for field in ['readCount', 'showCount', 'commentCount', 'diggCount', 'shareCount', 'repinCount', 'forwardCount']:
            pattern = rf'"({field})"\s*:\s*(\d+)'
            matches = re.findall(pattern, html)
            if matches:
                metrics[field] = matches[0] if len(matches) == 1 else matches[0]

        for field in ['readCount', 'showCount', 'commentCount', 'diggCount', 'shareCount', 'repinCount', 'forwardCount']:
            if field not in metrics:
                encoded_field = urllib.parse.quote(f'"{field}"')
                pattern2 = rf'{re.escape(encoded_field)}%3A(\d+)'
                matches2 = re.findall(pattern2, html)
                if matches2:
                    metrics[field] = matches2[0]

        page_title = await page.title()

        return {
            'url': url,
            'title': page_title,
            'metrics': metrics
        }
    except Exception as e:
        return {
            'url': article_url,
            'title': title_hint,
            'error': str(e)
        }

async def main(urls):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await context.new_page()

        results = []
        for u in urls:
            r = await get_article_metrics(page, u)
            results.append(r)
            print(f"\n{'='*60}")
            print(f"标题: {r.get('title', 'N/A')}")
            print(f"URL: {r.get('url', u)}")
            if 'metrics' in r:
                m = r['metrics']
                print(f"  展现量(showCount): {m.get('showCount', 'N/A')}")
                print(f"  阅读量(readCount): {m.get('readCount', 'N/A')}")
                print(f"  评论数(commentCount): {m.get('commentCount', 'N/A')}")
                print(f"  点赞数(diggCount): {m.get('diggCount', 'N/A')}")
                print(f"  收藏数(repinCount): {m.get('repinCount', 'N/A')}")
                print(f"  分享数(shareCount): {m.get('shareCount', 'N/A')}")
            if 'error' in r:
                print(f"  错误: {r['error']}")

        # 汇总排序
        print(f"\n{'='*60}")
        print("=== 按展现量排序 ===")
        valid = [r for r in results if 'metrics' in r and 'showCount' in r['metrics']]
        valid.sort(key=lambda x: int(x['metrics']['showCount']), reverse=True)
        for i, r in enumerate(valid, 1):
            m = r['metrics']
            print(f"\n{i}. {r.get('title', 'N/A')[:50]}")
            print(f"   展现={m.get('showCount','?')} 阅读={m.get('readCount','?')} 收藏={m.get('repinCount','?')} 评论={m.get('commentCount','?')} 点赞={m.get('diggCount','?')}")

        # JSON输出
        print(f"\n=== JSON ===")
        print(json.dumps(results, ensure_ascii=False, indent=2))

        await browser.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python3 toutiao_metrics_v2.py <文章URL或group_id> [url2] [url3] ...")
        sys.exit(1)
    asyncio.run(main(sys.argv[1:]))
