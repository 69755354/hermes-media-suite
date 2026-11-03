# 快代理私密代理 (Kuaidaili Private Proxy) 接入指南

> 适用于需要通过中国代理服务器访问抖音/快手/小红书等国内平台的内容抓取场景。

---

## 一、概念区分

私密代理有两个独立的白名单系统：

| 白名单类型 | 作用 | 设置位置 |
|:---|:---|:---|
| **API白名单** | 控制哪些 IP 可以调用 `dps.kdlapi.com/api/getdps` 提取接口 | 账户中心 → API管理 |
| **代理白名单** | 控制哪些 IP 可以使用提取出来的代理IP上网 | 订单详情页 |

**铁律：** 两个白名单都要加服务器IP，漏一个都不通。

---

## 二、提取代理IP

### API地址
```
https://dps.kdlapi.com/api/getdps/?secret_id=xxx&signature=xxx&num=1&format=text&sep=1
```

### 参数说明
| 参数 | 说明 |
|:---|:---|
| `secret_id` | 订单的 SecretId |
| `signature` | 开启"密钥明文验证"后直接用 SecretKey 当签名 |
| `num` | 提取数量 |
| `format` | `text`(纯文本) / `json`(JSON) |
| `sep` | 分隔符 `1`=换行 |

### 实测命令
```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
PROXY_RAW=$(curl -sL --max-time 10 "https://dps.kdlapi.com/api/getdps/?secret_id=YOUR_SECRET_ID&signature=YOUR_SECRET_KEY&num=1&format=text&sep=1")
echo "代理: $PROXY_RAW"
```
返回格式：`IP:PORT`（如 `42.81.14.86:20447`）

### 出错码
| 错误码 | 含义 | 解决 |
|:---|:---|:---|
| `-108` | IP白名单不匹配 | 确认API白名单加了服务器IP |
| `-130` | 缺少参数 | 检查参数名是否正确 |
| `-102` | 订单无效或已过期 | 检查订单状态 |

---

## 三、代理协议：SOCKS5（重要）

**私密代理使用 SOCKS5 协议，不是 HTTP！**

```bash
# ✅ 正确：SOCKS5h（DNS解析走代理）
curl -x "socks5h://IP:PORT" https://httpbin.org/ip

# ✅ 白名单模式（不带账密）
curl -x "socks5h://IP:PORT" https://httpbin.org/ip

# ❌ 错误：HTTP代理格式不通
curl -x "http://IP:PORT" https://httpbin.org/ip  # 不通
```

### Chrome 兼容性
| 模式 | Chrome 效果 |
|:---|:---:|
| `--proxy-server="socks5://user:pass@IP:PORT"` | ❌ `ERR_NO_SUPPORTED_PROXIES` |
| `--proxy-server="socks5://IP:PORT"`（白名单模式，无账密） | ✅ 正常连接 |

**结论：** 用 Chrome 走私密代理必须用白名单模式（不带账密）。

---

## 四、Python SDK 方式

```bash
pip install kdl --break-system-packages
```

```python
from kdl import Auth, Client

auth = Auth('secret_id', 'secret_key')
client = Client(auth)

# 提取代理IP
proxy_list = client.get_dps(num=1, sign_type='token', format='json', sep=1)

# 查白名单
whitelist = client.get_ip_whitelist()

# 设置白名单
client.set_ip_whitelist(iplist=['<GZ_HOST>'])
```

注意：SDK 调 API 也会走 `-108` IP白名单检查，SDK 调用前同样需要 API白名单。

---

## 五、代理IP有效期

- **按IP付费**：有效期 1~5 分钟
- 过期后的IP需要重新提取
- 每个请求建议重新提取一个新IP

---

## 六、Chrome + 代理完整启动流程

```bash
# 1. 提取新代理
unset http_proxy https_proxy
PROXY_RAW=$(curl -sL --max-time 10 "https://dps.kdlapi.com/api/getdps/?secret_id=xxx&signature=xxx&num=1&format=text&sep=1")

# 2. 启动Chrome走SOCKS5（不带账密的白名单模式）
/snap/chromium/3483/usr/lib/chromium-browser/chrome \
  --headless=new --no-sandbox \
  --disable-dev-shm-usage --disable-gpu \
  --proxy-server="socks5://$PROXY_RAW" \
  --remote-debugging-port=9225 \
  --user-data-dir=/tmp/chrome-proxy-data
```

---

## 七、注意事项

1. **环境变量污染：** `http_proxy` / `https_proxy` 环境变量会影响提取API的调用（提取API走代理后会从代理IP检测白名单）。提取前务必 `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY`。
2. **IP变化检测：** 快代理的API提取接口会检测调用方的IP，如果服务器IP未在API白名单内则返回 `-108`。
3. **代理IP时效：** 提取后的代理IP有存活时间限制，Chrome启动需要时间，代理可能在此期间过期。尽量缩短提取→启动→导航的时间窗口。

---

## 八、抖音视频访问工作流

SOCKS5白名单模式 + Chrome 可成功加载抖音 **单视频页**（v.douyin.com 短链跳转），获取完整元数据。

### 前置条件
- API白名单已加服务器IP（调 `getdps` 接口）
- 代理白名单已加服务器IP（用代理上网）
- 开启「密钥明文验证」（SecretKey 直接当 signature）

### 完整流程

```bash
# 1. 提取代理IP（⚠️ 先清环境变量）
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
PROXY_RAW=$(curl -sL --max-time 10 \
  "https://dps.kdlapi.com/api/getdps/?secret_id=YOUR_SID&signature=YOUR_SKEY&num=1&format=text&sep=1")

# 2. 启动 Chrome 走 SOCKS5（白名单模式，不带账密）
/snap/chromium/3483/usr/lib/chromium-browser/chrome \
  --headless=new --no-sandbox \
  --disable-dev-shm-usage --disable-gpu \
  --proxy-server="socks5://$PROXY_RAW" \
  --remote-debugging-port=9226 \
  --user-data-dir=/tmp/chrome-dy-data 2>&1 &
sleep 5

# 3. 导航到抖音视频短链（会自动跳转到 www.douyin.com/video/XXX）
# 通过 Hermes browser_navigate 或 CDP Target.createTarget + Page.navigate

# 4. 用 browser_snapshot 提取元数据
# 可提取：标题、作者、发布时间、标签、点赞数、章节要点（如有）
# 视频页面加载成功时，snapshot 中可见完整导航栏和视频信息区
```

### 已知限制

| 场景 | 结果 | 原因 |
|:---|:---:|:---|
| **单视频URL**（v.douyin.com/XXX） | ✅ 成功加载 | 直接跳转视频页，byted_acrawler 可过 |
| **搜索页**（douyin.com/search/关键词） | ❌ 验证码中间页 | 搜索触发滑块验证码 |
| **首页**（douyin.com） | ❌ 验证码中间页 | 首页也触发验证码 |
| **SOCKS5+账密** | ❌ ERR_NO_SUPPORTED_PROXIES | Chrome不支持SOCKS5带账密 |
| **SOCKS5白名单模式**（无账密） | ✅ 正常 | IP在白名单内即可 |

### ⚠️ 注意事项

1. **环境变量污染陷阱：** `http_proxy` / `https_proxy` 环境变量会导致提取API从代理IP检测白名单。提取前**必须** `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY`。
2. **代理IP时效：** 1~5分钟过期。Snap Chromium 启动慢（~15秒），提取→启动→导航窗口期紧张，过期需重提重开Chrome。
3. **代理IP出口变化：** 每次提取IP不同，出口IP也会变，不影响使用。
4. **CDP URL变化：** Chrome重启后 WebSocket URL 的 UUID 会变。需要 `hermes config set browser.cdp_url ws://127.0.0.1:9226`。
5. **白名单两套：** API白名单（调getdps）+ 代理白名单（用代理），缺一不可。
