# 国内平台（抖音/小红书等）代理访问方案

## 背景

海外服务器（腾讯云广州等）直连国内平台时，会遇到：
1. 抖音 `byted_acrawler` JS反爬 + 滑块验证码
2. 小红书登录/风控拦截
3. 百度系反爬
4. 部分CDN/API被墙

## 推荐方案：Kuaidaili 私密代理（SOCKS5 白名单模式）

### 代理类型
- **产品类型**：私密代理（按IP付费）
- **协议**：SOCKS5（非HTTP代理）
- **鉴权方式**：白名单 / 用户名密码

### 白名单模式配置（推荐）

IP白名单加好后，Chrome启动时不需要账密：

```bash
# 提取代理IP（先加白API白名单 + 代理白名单）
PROXY_RAW=$(curl -sL "https://dps.kdlapi.com/api/getdps/?secret_id=YOUR_SECRET_ID&signature=YOUR_SECRET_KEY&num=1&format=text&sep=1")
# 输出: IP:PORT

# Chrome启动走SOCKS5代理（白名单模式）
chromium --headless --no-sandbox \
  --disable-dev-shm-usage --disable-gpu \
  --proxy-server="socks5://$PROXY_RAW" \
  --remote-debugging-port=9226 \
  --user-data-dir=/tmp/chrome-proxy-data
```

### API提取说明

```bash
# 提取链接格式
https://dps.kdlapi.com/api/getdps/?secret_id=xxx&signature=xxx&num=1&format=text&sep=1

# 参数
# secret_id: 订单SecretId
# signature: 开启「密钥明文验证」后直接传SecretKey
# num: 提取IP数量
# format: text（纯文本）或 json
# sep: 分隔符
```

### 白名单设置（坑点）

**快代理的白名单分为两种，缺一不可：**

| 白名单类型 | 作用 | 设置位置 |
|:-----------|:-----|:---------|
| **API白名单** | 允许调用 `dps.kdlapi.com/api/getdps` 提取接口 | 账户中心 → API管理 |
| **代理白名单** | 允许使用提取出来的代理IP | 订单详情页 → IP白名单 |

错误码 `-108` = IP白名单不匹配。如果加了还报错，检查加的是哪种白名单。

### 代理IP生命周期

- 私密代理 IP 有效时长：1~5分钟
- 到期后需重新提取
- 每次提取前必须 `unset http_proxy https_proxy`（环境变量会污染API调用）

### 测试代理是否工作

```bash
# 测试SOCKS5代理（推荐socks5h，DNS走代理解析）
curl -s --max-time 10 -x "socks5h://IP:PORT" https://httpbin.org/ip

# 有用户名密码时
curl -s --max-time 10 -x "socks5h://username:password@IP:PORT" https://httpbin.org/ip
```

## 抖音访问的特殊注意事项

### 反爬链

```
curl/直连 → byted_acrawler JS挑战 → 生成__ac_nonce + __ac_signature → 页面重载 → 滑块验证码 → 正常页面
```

### Chrome CDP + 代理访问

- SOCKS5 白名单模式（不带账密）可通过Chrome访问抖音
- 页面加载后会遇到 **验证码中间页**（"验证码中间页"标题）
- 滑块验证码无法自动通过（headless 环境无法交互）
- 已有的 `__ac_signature` cookie 不足以绕过验证

### 可获取的内容

| 内容类型 | 可获取性 | 方式 |
|:---------|:---------|:-----|
| 视频页面元数据（标题/作者/标签/章节） | ✅ 可获取 | Chrome CDP + 代理 |
| 视频画面截图 | ✅ 可获取 | Page.captureScreenshot |
| 视频评论 | ❌ 需登录 | — |
| AI生成视频的原prompt | ❌ 无法获取 | — |

### 实用技巧

1. 短链接 `v.douyin.com/xxx` 会自动跳转到 `douyin.com/video/xxx`
2. 页面拉到后要等几秒等JS渲染完成再提取DOM
3. 代理IP过期后Chrome连接断开，需重新提取+重启Chrome
4. 推荐代理提取和Chrome启动做在一个脚本里，减少窗口期

## 替代方案

1. **手机UA + 旧版API**：部分抖音接口对手机UA限制较少
2. **微信小程序抓包**：抖音小程序接口常比主站松
3. **第三方数据服务**：如新榜、蝉妈妈（需付费）
4. **用户手动发链接**：最简洁，让用户发几条爆款链接，直接拆解结构
