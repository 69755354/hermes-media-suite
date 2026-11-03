# Playwright 直接抓取方案

## 背景

agent-browser 自身启动 Chrome 的路径有 bug（v0.20.0–v0.31.1 全部超时），根因见 GitHub Issue #1036：agent-browser 的 `enable_domains()` 向所有标签页发送 `Page.enable`，遇到休眠/冻结标签页时永久卡死。

**但 `--cdp` 模式连接已手动启动的 Chrome 完全正常。** 通过端口号（`--cdp 9222`）而非完整 WebSocket URL 连接即可绕过该 bug。Playwright 也可作为备用方案。

## agent-browser CDP 修复方案（2026-07-06 已验证 ✅）

### 修复方案：CDP 直连模式

#### 1. 手动启动 Chrome（带 CDP 端口）

**⚠️ 必须加 `--remote-allow-origins=*`，否则 WebSocket 连接被 CORS 拦截（实测 2026-07-18）。**

```bash
~/.cache/agent-browser/chrome-linux64/chrome \
  --headless=new \
  --no-sandbox \
  --disable-dev-shm-usage \
  --remote-debugging-port=9222 \
  --remote-allow-origins=* \
  --user-data-dir=/tmp/chrome-cdp-data \
  --disable-gpu \
  --disable-software-rasterizer
```

#### 2. 验证 CDP 可用

```bash
curl -s http://127.0.0.1:9222/json/version
# → {"Browser": "Chrome/150.0.7871.46", ...}
```

#### 3. 用 agent-browser --cdp 连接

**关键：只用端口号（`--cdp 9222`），不用完整 WS URL。**

```bash
# ✅ 正常工作
agent-browser --cdp 9222 open "https://www.baidu.com"
agent-browser --cdp 9222 snapshot
agent-browser --cdp 9222 open "https://www.douyin.com/video/7658627786227201506"

# ❌ 会超时（不要用这个格式）
agent-browser --cdp ws://127.0.0.1:9222/devtools/browser/uuid snapshot
```

#### 4. 配置为系统服务（开机自启）

```ini
# ~/.config/systemd/user/chrome-cdp.service
[Unit]
Description=Chrome Headless with CDP for Hermes agent-browser
After=network.target

[Service]
Type=simple
ExecStart=/home/ubuntu/.cache/agent-browser/chrome-linux64/chrome \
    --headless=new --no-sandbox --disable-dev-shm-usage \
    --remote-debugging-port=9222 \
    --user-data-dir=/tmp/chrome-cdp-data \
    --disable-gpu --disable-software-rasterizer
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable chrome-cdp.service
systemctl --user start chrome-cdp.service
sudo loginctl enable-linger ubuntu   # 防止SSH断开后服务挂掉
```

#### 5. 配置 Hermes 使用 CDP

```yaml
# ~/.hermes/config.yaml
browser:
  inactivity_timeout: 120
  cdp_url: ws://127.0.0.1:9222
```

```bash
hermes config set browser.cdp_url "ws://127.0.0.1:9222"
```

### 故障特征 vs 修复对照

| 问题 | 旧结论 | 正确方案 |
|:---|:---|:---|
| `agent-browser open` 超时 | 认为是 Rust 二进制 bug，无法修复 | 换成 `--cdp 9222` 模式 |
| `--cdp ws://full-url` 超时 | 认定 CDP 模式也坏 | 换成 `--cdp 9222`（只用端口号） |
| Chrome 版本不兼容 | 试了 149+150 均超时 | 根因不是版本，是启动模式 |
| 所有 browser 工具不可用 | 永久降级到 Playwright | CDP 模式已验证可用 |

### 本机当前状态

| 组件 | 状态 |
|:---|:---:|
| Chrome 150 CDP 服务 | ✅ systemd 开机自启，`chrome-cdp.service` |
| agent-browser CLI | ✅ `/usr/local/bin/agent-browser` |
| Hermes `browser.cdp_url` | ✅ `ws://127.0.0.1:9222` |
| `agent-browser --cdp 9222` | ✅ 百度、抖音导航+快照均通过 |
| Playwright 备用 | ✅ 仍可用，`scripts/browser_playwright.py` |

---

## 环境检查

```bash
# 检查 Playwright 是否可用
python3 -c "from playwright.sync_api import sync_playwright; print('OK')"

# 检查 Chromium 是否可用
timeout 10 /snap/chromium/3477/usr/lib/chromium-browser/chrome --headless=new --no-sandbox --disable-dev-shm-usage --dump-dom https://www.baidu.com 2>/dev/null | head -5
```

## 通用抓取模板

```python
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path='/snap/chromium/3477/usr/lib/chromium-browser/chrome',
        args=['--no-sandbox', '--disable-dev-shm-usage']
    )
    page = browser.new_page(viewport={'width': 1280, 'height': 720})
    page.goto('URL_HERE', wait_until='domcontentloaded', timeout=30000)
    time.sleep(8)
    
    # 用 JS evaluate 提取数据（比 Python 解析稳定，免转义问题）
    data = page.evaluate('''() => {
        // DOM 操作
        return JSON.stringify(result);
    }''')
    
    browser.close()
```

## 快手 (Kuaishou) — 已验证 ✅

### 页面结构要点
- 热榜页面：`https://www.kuaishou.com/brilliant`
- 每个视频卡片用 `[class*="video-card"]` 包裹
- 标题在内部 `img[alt]` 属性中
- 热度在父容器的文本中（如 `1330.6万热度`）
- JS SPA，需 `time.sleep(8–10)` 等待渲染
- 无需登录即可获取热榜

### 最终验证可用的抓取代码

```python
"""快手热榜抓取 — 已验证 2026-07-06"""
from playwright.sync_api import sync_playwright
import time, json
from datetime import datetime

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path='/snap/chromium/3477/usr/lib/chromium-browser/chrome',
        args=['--no-sandbox', '--disable-dev-shm-usage']
    )
    page = browser.new_page(viewport={'width': 1280, 'height': 720})
    page.goto('https://www.kuaishou.com/brilliant', wait_until='domcontentloaded', timeout=30000)
    time.sleep(10)

    # 全 JS 解析 — 在浏览器中执行，避免 Python 端转义/解析问题
    data = json.loads(page.evaluate('''() => {
        const cards = document.querySelectorAll('[class*="video-card"]');
        const items = [];
        cards.forEach(card => {
            const img = card.querySelector('img');
            const title = img ? img.alt : '';
            if (!title) return;
            const parent = card.closest('[class*="card"]') || card.parentElement;
            const allText = parent ? parent.textContent : card.textContent;
            const heatMatch = allText.match(/([\\d.]+万?热度)/);
            const likeMatch = allText.match(/([\\d.]+万?喜欢)/);
            const link = card.querySelector('a') || card.closest('a');
            const href = link ? link.href : '';
            if (heatMatch) items.push({type:'hot', title, heat: heatMatch[1], href});
            else if (likeMatch) items.push({type:'video', title, likes: likeMatch[1], href});
        });
        return JSON.stringify(items);
    }'''))

    hot_list = [d for d in data if d['type'] == 'hot']
    video_list = [d for d in data if d['type'] == 'video']
    print(f"热榜 {len(hot_list)} 条, 短视频 {len(video_list)} 条")

    # 保存到 task 文件夹
    task_dir = '~/.openclaw/workspace/content-hunter/task-$(date +%Y-%m-%d-%H%M)'
    os.makedirs(task_dir, exist_ok=True)
    with open(f'{task_dir}/kuaishou.md', 'w') as f:
        f.write(f'# 快手热门内容\\n抓取时间: {datetime.now()}\\n\\n')
        for h in hot_list[:30]:
            f.write(f'### {h["title"]}\\n- 热度: {h["heat"]}\\n- 链接: {h["href"]}\\n\\n')
        for v in video_list[:20]:
            f.write(f'### {v["title"]}\\n- 点赞: {v["likes"]}\\n- 链接: {v["href"]}\\n\\n')

    browser.close()
```

### 已知限制

| 数据源 | 状态 | 原因 |
|:---|:---:|:---|
| 热榜（30–49条） | ✅ 稳定可抓 | 公开页面，无登录需求 |
| 精彩短视频 feed | ⚠️ 不稳定 | 快手 JS 懒加载 + 反爬，有时渲染为空白页脚。建议每次新建 browser context |
| 单条视频详情页（`v.kuaishou.com/xxx`） | ❌ 需登录 | **未登录时返回 JSON `{"result":2}`**（result:2 = 未登录/受限） |
| 快手登录二维码 | ❌ 无法渲染 | 登录页 QR 码用 canvas 绘制，headless Chrome + Xvfb 均无法渲染出有效二维码。需物理显示器 + 真人扫码 |

### 关于 QR 码登录的技术细节
- 登录页 URL: `https://passport.kuaishou.com/pc/account/login`
- 默认显示"扫码登录"标签
- QR 码由 JS 模块 `account-qrcode.e97411da.js` 通过 canvas 生成并转 base64 data URL
- 即使使用 Xvfb 虚拟显示器（`headless=False, DISPLAY=:99`）也无法渲染
- API 端点 `/rest/infra/id/card/qrToken/url/gen` 需要特定 cookies + CORS 头，直接 curl 返回 404

### 是否尝试 Xvfb
```bash
# 已尝试的方案（均失败）
Xvfb :99 -screen 0 1280x720x24 &
DISPLAY=:99 playwright launch(headless=False)
# 结果：页面正常加载，但 QR 码区域始终为空白
```
