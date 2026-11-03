#!/usr/bin/env python3
"""
Playwright浏览器工具 - 替代agent-browser
支持：导航、截图、提取文本
"""
import sys, json, time, os
from playwright.sync_api import sync_playwright

CHROME_PATH = "/snap/chromium/3477/usr/lib/chromium-browser/chrome"

def navigate(url, timeout=30000, wait_for=5):
    """打开页面，返回页面信息"""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=CHROME_PATH,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        page = browser.new_page(viewport={'width': 1280, 'height': 720})
        
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            time.sleep(wait_for)
            
            result = {
                'success': True,
                'url': page.url,
                'title': page.title(),
                'content': page.eval_on_selector('body', 'el => el.innerText') or '',
                'links_count': page.eval_on_selector_all('a', 'els => els.length'),
            }
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            browser.close()

def snapshot(url=None, timeout=30000):
    """获取页面快照（文本）"""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=CHROME_PATH,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        page = browser.new_page(viewport={'width': 1280, 'height': 720})
        try:
            if url:
                page.goto(url, wait_until='domcontentloaded', timeout=timeout)
                time.sleep(5)
            
            # 提取所有可见文本
            texts = page.evaluate('''() => {
                const walker = document.createTreeWalker(document.body, 4);
                const result = [];
                while (walker.nextNode() && result.length < 500) {
                    const t = walker.currentNode.textContent.trim();
                    if (t.length > 2) result.push(t);
                }
                return result;
            }''')
            
            # 提取所有链接
            links = page.eval_on_selector_all('a[href]', 
                'els => els.map(el => ({text: el.textContent.trim().substring(0, 80), href: el.href})).filter(x => x.text && x.href)')
            
            return {
                'success': True,
                'title': page.title(),
                'url': page.url,
                'texts': texts,
                'text_count': len(texts),
                'links': links[:50],
                'link_count': len(links),
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            browser.close()

def screenshot(url, output_path=None):
    """截图"""
    if not output_path:
        output_path = f'/tmp/playwright_ss_{int(time.time())}.png'
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=CHROME_PATH,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        page = browser.new_page(viewport={'width': 1280, 'height': 720})
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            time.sleep(5)
            page.screenshot(path=output_path, full_page=False)
            return {'success': True, 'path': output_path, 'size': os.path.getsize(output_path)}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            browser.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'error': '用法: browser_playwright.py <命令> [参数]'}))
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'open':
        url = sys.argv[2] if len(sys.argv) > 2 else 'https://www.baidu.com'
        result = navigate(url)
    elif command == 'snapshot':
        url = sys.argv[2] if len(sys.argv) > 2 else None
        result = snapshot(url)
    elif command == 'screenshot':
        url = sys.argv[2] if len(sys.argv) > 2 else 'https://www.baidu.com'
        result = screenshot(url)
    else:
        result = {'error': f'未知命令: {command}'}
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
