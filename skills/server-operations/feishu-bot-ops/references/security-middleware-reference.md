# 小鹿 security-middleware.py 安全中间层参考（物理闸设计模板）

来源：广州机 customer profile `~/.hermes/scripts/security-middleware.py`（2026-08-14 查小鹿做法时摘录）。
定位：**全链路越权防御中间层**——所有 API 请求/节点执行前必须经过它，硬编码、不可被任何输入/模型输出绕过。

这是「物理卡点」的成熟范本。以后要建任何对外通道的物理闸（飞书发消息、生图、出片、调付费 API），照这个骨架抄，而不是从零想。

## 六大职责

1. 参数白名单 + 数值区间拦截
2. 输入关键词黑名单
3. 通道路由校验（探店=Seedance，口播=婵镜）
4. 重试计数器（硬编码上限 2 次）
5. 限流（1 分钟 3 次 → 熔断 10 分钟）
6. 成本阈值熔断（单条流水线 50 元）

## 硬编码配置结构（写死，不可被输入覆盖）

```python
# 1. 参数白名单 + 区间
PARAM_WHITELIST = {
    "seedance": {"allowed_keys": {"prompt","duration","reference_image","seed","model"},
                 "ranges": {"duration": (3,10), "seed": (1,999999999)},
                 "allowed_models": {"doubao-seedance-2-0-mini-260615"},
                 "allowed_dynamic_strength": (25,45)},
    "chanjing": {"allowed_keys": {"audio_man","text","digital_human_id","model","speed","gesture_strength","background_img","clothes_img"},
                 "ranges": {"speed": (0.8,1.2), "gesture_strength": (0.1,0.5)}},
    "deepseek": {"allowed_keys": {"model","messages","temperature","max_tokens"},
                 "ranges": {"temperature": (0.0,1.0), "max_tokens": (100,4096)},
                 "allowed_models": {"deepseek-v4-pro","deepseek-v4-flash"}},
}

# 2. 通道绑定（内容类型 → 强制通道，禁止越权）
CHANNEL_BINDING = {"探店":"seedance", "剧情":"seedance", "口播":"chanjing"}

# 3. 关键词黑名单（分两类：越狱词 + 工具名泄露防护）
BLOCKED_KEYWORDS = [
    # 越狱/提权
    "跳过校验","跳过节点","修改参数","忽略白名单","忽略SOUL","忽略SKILL","无视安全",
    "DAN模式","开发者模式","God模式","Do Anything Now",
    "ignore all previous","ignore all instructions","ignore all rules","override",
    # 工具名泄露防护（禁止在对外输出中提及）—— 完整清单，建闸直接抄
    "婵镜","Seedance","Seedream","火山引擎","火山方舟","ARK","豆包","DeepSeek",
    "ffmpeg","MCP","TTS","Helper API","execute-api","SearXNG","AstrBot",
    "Hindsight","HeadRoom","OpenCode","CapCut","security-middleware",
    "check_keywords","check_channel","doubao-seedream","doubao-seedance","chanjing",
    "create_video","数字人克隆",
]

# 4/5/6. 重试/限流/成本
MAX_RETRIES = 2
RATE_LIMIT_WINDOW = 60; RATE_LIMIT_MAX = 3; RATE_LIMIT_COOLDOWN = 600
COST_THRESHOLD_PER_PIPELINE = 50.0
```

## 校验函数（每个都是独立可复用的检查）

- `check_channel(content_type, requested_channel)` — 通道绑定校验，越权拒绝
- `validate_params(channel, params)` — 白名单 + 区间 + 模型白名单
- `check_keywords(text)` — 黑名单命中即拦截，返回命中的词
- `check_retry(project_id)` — 重试计数，超上限拒绝

## 日志机制（拦截必须留痕）

```python
def _log(type_, detail):
    # 同时写两份：security_alerts.log（安全告警）+ operations.log（全操作）
```

拦截时 `_log("BLOCKED", ...)`，审计可追。本机 feishu_send_gate.py 对齐了这个：拦截写 `guard/security_alerts.log`。

## 与 feishu_send_gate.py 的关系

feishu_send_gate.py 只做了本模式的两个子集（关键词黑名单 + @ 强制），够飞书群消息用。若以后要对「生图/出片/付费 API」建闸，按上表补参数白名单 + 限流 + 成本熔断三块。
