# Profile Path Mapping

> 2026-09-02 踩坑沉淀：soul-md-update-protocol 的所有路径硬编码 customer profile，
> 在新加坡机（默认 profile）上全部指向不存在的文件，静默失败。

## 两种 Profile 布局

### Customer Profile（广州机，小鹿）

所有文件在 `/home/ubuntu/.hermes/profiles/customer/` 下：

```
profiles/customer/
├── gateway.pid
├── gateway_state.json
├── state.db          # sessions + gateway_routing + messages
├── SOUL.md           # 可能有也可能没有
├── .env
├── skills/           # 独立副本，改主目录后必须 cp 同步
├── cache/
├── logs/
└── wiki/
```

### Default Profile（新加坡机 / 单机部署）

所有文件在 `/home/ubuntu/.hermes/` 顶层：

```
.hermes/
├── gateway.pid
├── gateway_state.json
├── state.db
├── SOUL.md
├── config.yaml
├── skills/           # 主目录即生效，无独立副本
└── ...
```

## 检测脚本

### Bash

```bash
if [ -f /home/ubuntu/.hermes/profiles/customer/gateway.pid ]; then
  PROFILE_DIR=/home/ubuntu/.hermes/profiles/customer
  PROFILE_TYPE=customer
elif [ -f /home/ubuntu/.hermes/gateway.pid ]; then
  PROFILE_DIR=/home/ubuntu/.hermes
  PROFILE_TYPE=default
else
  echo "ERROR: 找不到 gateway.pid"; exit 1
fi
echo "PROFILE_DIR=$PROFILE_DIR TYPE=$PROFILE_TYPE"
```

### Python

```python
import os

def detect_profile_dir():
    """返回当前活跃的profile根目录"""
    candidates = [
        '/home/ubuntu/.hermes/profiles/customer',
        '/home/ubuntu/.hermes',
    ]
    for p in candidates:
        if os.path.exists(os.path.join(p, 'gateway.pid')):
            return p
    raise RuntimeError("找不到gateway.pid，无法确定profile目录")

PROFILE_DIR = detect_profile_dir()
```

## 差异汇总

| 操作 | customer profile | default profile |
|:-----|:----------------|:---------------|
| 清DB | `state.db` 在 `profiles/customer/` | `state.db` 在顶层 |
| 杀网关 | `profiles/customer/gateway.pid` | `gateway.pid` |
| 验连接状态 | `profiles/customer/gateway_state.json` | `gateway_state.json` |
| 同步skills | 必须cp到 `profiles/customer/skills/` | 不需要（主目录即生效） |
| SOUL.md位置 | `profiles/customer/SOUL.md` 或顶层 | 顶层 `SOUL.md` |
| 哈希更新 | `guard/hashes/` 下有两套（SOUL.md + customer_SOUL.md） | 只更新 `guard/hashes/SOUL.md.md5` |

## 踩坑经过

1. 用户（天行者）说「你把SOUL和广州的搞混了」
2. 查磁盘文件：`/home/ubuntu/.hermes/SOUL.md` 已经是框架层版本（22:22刚改回来）
3. 但当前会话 system_prompt 还是旧版（会话创建时加载的旧版本）
4. 按 soul-md-update-protocol 流程清DB时，skill 里所有路径指向 `profiles/customer/`，但这台机器没有 customer profile
5. 实际 `gateway.pid`、`state.db`、`gateway_state.json` 都在 `/home/ubuntu/.hermes/` 顶层
6. 用顶层路径清DB成功，但 skill 的路径假设是错的

## 教训

**任何操作 SOUL.md / state.db / gateway 的流程都不能硬编码 profile 路径，必须先检测再拼路径。**

## 相关
- `soul-md-update-protocol`（user-owned，curator 无权改，路径硬编码问题记录在此供参考）
- `hermes-profile-independence`（多 profile 独立性边界）
- `server-migration`（先确认本机身份）
