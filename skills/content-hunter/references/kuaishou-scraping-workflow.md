# 快手数据抓取完整工作流

## 架构

```
快手热榜页（brilliant） → CDP模式（agent-browser --cdp 9222）
快手单视频详情页 → Python requests + Cookie + 手机UA

两者组合覆盖快手全平台数据。
```

## 热榜页抓取（CDP模式）

```bash
agent-browser --cdp 9222 open "https://www.kuaishou.com/brilliant"
sleep 3
agent-browser --cdp 9222 snapshot
```

返回accessibility tree，含热榜标题、排名、热度数据。

## 单视频详情页抓取（Cookie + 手机UA）

### 前置条件
- 已执行快手登录（QR扫码或密码），cookie存入 `references/kuaishou_cookies.json`
- Chrome user-data-dir: `/tmp/chrome-cdp-data`（持久化）

### 完整代码

```python
import requests, json, re

# 读cookie
with open('/path/to/kuaishou_cookies.json') as f:
    cookies_list = json.load(f)
cookies = {c['name']: c['value'] for c in cookies_list}

headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36',
    'Referer': 'https://www.kuaishou.com/',
}

def extract_kuaishou_video(photo_id):
    """从快手视频页面提取完整数据"""
    resp = requests.get(
        f"https://www.kuaishou.com/short-video/{photo_id}",
        headers=headers, cookies=cookies, timeout=15
    )
    html = resp.text
    
    result = {}
    
    m = re.search(r'<span class="text txt"[^>]*>([^<]+)</span>', html)
    if m: result['title'] = m.group(1)
    
    result['topics'] = re.findall(r'<span class="topic txt"[^>]*>([^<]+)</span>', html)
    
    for field, pattern in [
        ('user_id', r'"userId":"([^"]*)"'),
        ('user_name', r'"userName":"([^"]*)"'),
        ('like_count', r'"likeCount"[^:]*:"([^"]*)"'),
        ('comment_count', r'"commentCount"[^:]*:"([^"]*)"'),
        ('fans_count', r'"fansCount":"([^"]*)"'),
    ]:
        m = re.search(pattern, html)
        if m: result[field] = m.group(1)
    
    result['video_urls'] = re.findall(
        r'https?://[^"\']*\.(?:mp4|m3u8)[^"\']*', html
    )[:3]
    
    return result

# 用法
data = extract_kuaishou_video("3xtp7yw6ne57ivq")
print(data)
```

### 提取字段

| 字段 | 来源 |
|:---|:---|
| 标题 | `<span class="text txt">` |
| 话题标签 | `<span class="topic txt">` |
| 作者名 | `"userName"` |
| 作者ID | `"userId"` |
| 点赞 | `"likeCount"` |
| 评论 | `"commentCount"` |
| 视频URL | `\.mp4` 或 `\.m3u8` 链接 |

## 登录策略

- **QR码登录**：CDP模式打开 passport.kuaishou.com/pc/account/login/ → snapshot找"扫码登录"的ref → click → screenshot → 发给用户扫码
- **密码登录**：页面默认是密码模式（有手机号+密码输入框），fill → click登录按钮
- Cookie保存路径：`references/kuaishou_cookies.json`

## 已知限制

- 视频详情页在headless浏览器（CDP/Playwright）中被反爬封，必须用requests直调
- Cookie有效期：QR登录session持久化在Chrome user-data-dir，重启不丢。cookie文件供API调用使用
- 热榜brilliant页是SSR，CDP模式能正常读取
