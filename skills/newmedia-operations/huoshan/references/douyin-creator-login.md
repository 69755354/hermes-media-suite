# 抖音创作者中心登录指南 (数据复盘用)

## 为什么需要登录

节点15(数据复盘)需要查看抖音创作者中心的数据。**登录一次Cookie管几天到几周**，之后说「复盘」直接自动抓数据。

## 🚨 二维码格式是SVG不是PNG（关键发现）

抖音creator.douyin.com的登录二维码是 **SVG格式**（`data:image/svg+xml;base64,...`），不是PNG。

**为什么这个很重要：**
- PIL无法直接打开SVG → `UnidentifiedImageError`
- MEDIA发送SVG图片到微信 → 用户可能看不到（微信不渲染SVG）
- canvas重绘SVG → 跨域污染，无法导出

**修复方法——用ImageMagick convert转JPG后再发：**

```python
import base64, subprocess

# data_url是从CDP提取的base64（格式: data:image/svg+xml;base64,...）
b64 = data_url.split(',')[1]
with open('/tmp/qr.svg', 'wb') as f:
    f.write(base64.b64decode(b64))
subprocess.run(['convert', '/tmp/qr.svg', '-resize', '300x300', '/tmp/qr.jpg'], check=True)
# 发送 /tmp/qr.jpg
```

## 三种登录方式及坑

| 方式 | 问题 | 状态 |
|:----|:-----|:----|
| **二维码扫码** | 有效期2-3分钟，生成→发送→用户扫流程长易过期。且二维码是SVG格式需转JPG | ⚠️ 需快速操作+格式转换 |
| **手机验证码** | 部分号段收不到短信（被限流/拦截） | ❌ 不稳定 |
| **密码登录** | 登录后还需刷脸验证 | ❌ 流程复杂 |

## 常驻CDP二维码服务

脚本: `/home/ubuntu/.hermes/scripts/qr_daemon.py`

原理：保持CDP长连接(省40秒重连) → 每90秒自刷新二维码 → SVG格式base64存 `/tmp/qr_ready`

启动方式：
```bash
python3 /home/ubuntu/.hermes/scripts/qr_daemon.py &
```

使用流程：
1. 检查 `/tmp/qr_status` 是否 "ok XKB"
2. 读 `/tmp/qr_ready` → 用convert转JPG → MEDIA发送
3. 用户扫码→手机点确认→登录成功

（总结2026-07-16实验：二维码登录是本服务器Chrome和数据复盘的桥梁。SVG格式问题是MEDIA发送用户收不到的根因。一次登录成功后Cookie持久化，后续排查少折腾。）

## CDP端口

- Chrome实际运行在 **9222**
- config.yaml配置cdp_url为 `ws://127.0.0.1:9226`（与Chrome端口不一致）
- browser_cdp工具走配置端口(9226)，连不上时用curl直调9222：
  ```bash
  curl -s http://127.0.0.1:9222/json
  ```
- WebSocket地址: `ws://127.0.0.1:9222/devtools/page/{TAB_ID}`
